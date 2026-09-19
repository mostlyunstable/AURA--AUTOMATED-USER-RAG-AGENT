import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.main import app, get_mission_service
from core.application.mission_orchestrator import MissionOrchestrator
from core.application.mission_service import MissionService
from core.domain.tasks.entities import Task, TaskDependency
from core.domain.tasks.enums import TaskType
from core.infrastructure.database.models import Base
from core.infrastructure.database.repositories import SQLAlchemyUnitOfWork

DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://aura:aura@localhost:5432/aura"
)
if "sqlite" in DB_URL:
    raise RuntimeError("Integration tests MUST run against PostgreSQL.")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def async_client():
    engine = create_async_engine(DB_URL, echo=False, poolclass=pool.NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_mission_service():
        uow = SQLAlchemyUnitOfWork(
            async_sessionmaker(
                create_async_engine(DB_URL, poolclass=pool.NullPool),
                expire_on_commit=False,
            )
        )
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

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_execution_approval_flow(async_client):
    payload = {
        "title": "Approval Test",
        "description": "Desc",
        "repository_id": "r1",
        "source": "test",
    }
    resp = await async_client.post("/missions", json=payload)
    mission_id = resp.json()["id"]

    await async_client.post(
        f"/missions/{mission_id}/transition", json={"target_state": "PLANNING"}
    )
    await async_client.post(
        f"/missions/{mission_id}/transition", json={"target_state": "PLANNED"}
    )

    resp = await async_client.post(
        f"/missions/{mission_id}/transition", json={"target_state": "EXECUTING"}
    )
    assert resp.status_code == 409

    resp = await async_client.post(
        f"/missions/{mission_id}/approve", json={"approval_type": "EXECUTION"}
    )
    assert resp.status_code == 200

    resp = await async_client.get(f"/missions/{mission_id}")
    assert resp.json()["status"] == "APPROVED_FOR_EXECUTION"

    resp = await async_client.post(
        f"/missions/{mission_id}/transition", json={"target_state": "EXECUTING"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "EXECUTING"


@pytest.mark.asyncio
async def test_dag_cycle_detection():
    engine = create_async_engine(DB_URL, poolclass=pool.NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    uow = SQLAlchemyUnitOfWork(
        async_sessionmaker(
            create_async_engine(DB_URL, poolclass=pool.NullPool), expire_on_commit=False
        )
    )
    orchestrator = MissionOrchestrator(uow)
    service = MissionService(uow)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    mission = await service.create_mission("DAG", "desc", "repo", "test")

    t1 = Task(
        mission_id=mission.id, title="T1", description="D1", task_type=TaskType.ANALYSIS
    )
    t2 = Task(
        mission_id=mission.id, title="T2", description="D2", task_type=TaskType.ANALYSIS
    )
    t3 = Task(
        mission_id=mission.id, title="T3", description="D3", task_type=TaskType.ANALYSIS
    )

    await orchestrator.add_task(t1)
    await orchestrator.add_task(t2)
    await orchestrator.add_task(t3)

    await orchestrator.add_dependency(
        mission.id, TaskDependency(task_id=t2.id, depends_on_task_id=t1.id)
    )
    await orchestrator.add_dependency(
        mission.id, TaskDependency(task_id=t3.id, depends_on_task_id=t2.id)
    )

    with pytest.raises(ValueError, match="Cycle detected"):
        try:
            await orchestrator.add_dependency(
                mission.id, TaskDependency(task_id=t1.id, depends_on_task_id=t3.id)
            )
        except Exception as e:
            raise ValueError(str(e))

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
