import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.main import app, get_mission_service
from core.application.mission_service import MissionService
from core.infrastructure.database.models import Base
from core.infrastructure.database.repositories import SQLAlchemyUnitOfWork

DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://aura:aura@localhost:5432/aura"
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(autouse=True)
async def async_client():
    engine = create_async_engine(DB_URL, echo=False, poolclass=pool.NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_mission_service():
        uow = SQLAlchemyUnitOfWork(session_factory)
        return MissionService(uow)

    app.dependency_overrides[get_mission_service] = override_get_mission_service

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_health(async_client):
    response = await async_client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_mission(async_client):
    payload = {
        "title": "API Test",
        "description": "Desc",
        "repository_id": "repo1",
        "source": "api",
    }
    response = await async_client.post("/missions", json=payload)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_mission_flow(async_client):
    payload = {
        "title": "API Test 2",
        "description": "Desc 2",
        "repository_id": "repo2",
        "source": "api",
    }
    response = await async_client.post("/missions", json=payload)
    mission_id = response.json()["id"]

    response = await async_client.get(f"/missions/{mission_id}")
    assert response.status_code == 200

    response = await async_client.post(
        f"/missions/{mission_id}/transition", json={"target_state": "PLANNING"}
    )
    assert response.status_code == 200
