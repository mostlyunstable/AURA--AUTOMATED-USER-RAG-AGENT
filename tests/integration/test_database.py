import os

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.application.mission_service import MissionService
from core.domain.missions.enums import MissionStatus
from core.infrastructure.database.models import Base
from core.infrastructure.database.repositories import SQLAlchemyUnitOfWork

DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://aura:aura@localhost:5432/aura"
)
if "sqlite" in DB_URL:
    raise RuntimeError(
        "Integration tests MUST run against PostgreSQL. SQLite fallback is disabled."
    )


@pytest_asyncio.fixture
async def uow():
    engine = create_async_engine(DB_URL, echo=False, poolclass=pool.NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    uow = SQLAlchemyUnitOfWork(session_factory)
    yield uow

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_and_retrieve_mission(uow):
    service = MissionService(uow)
    mission = await service.create_mission(
        title="Test DB", description="Test Desc", repository_id="repo1", source="test"
    )
    fetched = await service.get_mission(mission.id)
    assert fetched is not None
    assert fetched.title == "Test DB"
    assert fetched.status == MissionStatus.CREATED


@pytest.mark.asyncio
async def test_mission_state_transition_persists(uow):
    service = MissionService(uow)
    mission = await service.create_mission(
        title="Test Transition",
        description="Test Desc",
        repository_id="repo1",
        source="test",
    )

    updated = await service.update_mission_status(mission.id, MissionStatus.PLANNING)
    assert updated.status == MissionStatus.PLANNING

    async with uow:
        events = await uow.session.execute(sa.text("SELECT * FROM events"))
        rows = events.fetchall()
        assert len(rows) == 2


@pytest.mark.asyncio
async def test_transaction_rollback(uow, monkeypatch):
    service = MissionService(uow)
    mission = await service.create_mission(
        title="Rollback Test", description="Desc", repository_id="repo1", source="test"
    )

    async def failing_append(*args, **kwargs):
        raise Exception("DB Failure")

    from core.infrastructure.database.repositories import SQLAlchemyEventRepository

    monkeypatch.setattr(SQLAlchemyEventRepository, "append", failing_append)

    try:
        await service.update_mission_status(mission.id, MissionStatus.PLANNING)
    except Exception:
        pass

    fetched = await service.get_mission(mission.id)
    assert fetched.status == MissionStatus.CREATED
