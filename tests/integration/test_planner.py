import os
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.main import app, engine, session_factory
from core.domain.plans.enums import PlanStatus
from core.infrastructure.database.connection import get_engine, get_session_maker
from core.infrastructure.database.models import Base

DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://aura:aura@localhost:5432/aura"
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    test_engine = create_async_engine(DB_URL, echo=False, poolclass=pool.NullPool)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def async_client():
    from apps.api.main import get_mission_service
    from core.application.mission_service import MissionService
    from core.infrastructure.database.repositories import SQLAlchemyUnitOfWork

    engine = create_async_engine(DB_URL, echo=False, poolclass=pool.NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_mission_service():
        uow = SQLAlchemyUnitOfWork(session_factory)
        return MissionService(uow)

    app.dependency_overrides[get_mission_service] = override_get_mission_service

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_planner_generation_and_idempotency(async_client):
    # 1. Create Mission
    payload = {
        "title": "Planner Test",
        "description": "Desc",
        "repository_id": "r1",
        "source": "test",
    }
    resp = await async_client.post("/missions", json=payload)
    mission_id = resp.json()["id"]

    # 2. Transition to PLANNING
    await async_client.post(
        f"/missions/{mission_id}/transition", json={"target_state": "PLANNING"}
    )

    # 3. Generate Plan
    # (By default it uses FakeLLMProvider because NVIDIA_API_KEY is unset in test env usually, unless leaked, but we can set it to Fake)
    import os

    os.environ.pop("NVIDIA_API_KEY", None)

    resp = await async_client.post(f"/missions/{mission_id}/plan")
    assert resp.status_code == 200
    plan1 = resp.json()
    assert plan1["status"] == "VALIDATED"
    assert len(plan1["output"]["tasks"]) > 0

    # Mission should now be PLANNED
    resp = await async_client.get(f"/missions/{mission_id}")
    assert resp.json()["status"] == "PLANNED"

    # Transition back to PLANNING for idempotency check
    await async_client.post(
        f"/missions/{mission_id}/transition", json={"target_state": "PLANNING"}
    )

    # Generate again
    resp = await async_client.post(f"/missions/{mission_id}/plan")
    assert resp.status_code == 200
    plan2 = resp.json()

    assert plan1["id"] != plan2["id"]

    # Plan1 should be SUPERSEDED now
    resp = await async_client.get(f"/missions/{mission_id}/plans")
    plans = resp.json()
    assert len(plans) == 2

    p1 = next(p for p in plans if p["id"] == plan1["id"])
    p2 = next(p for p in plans if p["id"] == plan2["id"])
    assert p1["status"] == "SUPERSEDED"
    assert p2["status"] == "VALIDATED"
