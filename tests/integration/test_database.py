import os

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from alembic.config import Config
from core.application.mission_service import MissionService
from core.domain.missions.enums import MissionStatus
from core.infrastructure.database.repositories import SQLAlchemyUnitOfWork

DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://aura:aura@localhost:5432/aura"
)
if "sqlite" in DB_URL:
    raise RuntimeError(
        "Integration tests MUST run against PostgreSQL. SQLite fallback is disabled."
    )


def run_alembic_migrations(database_url: str, direction: str = "upgrade"):
    """Run alembic migrations programmatically."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    if direction == "upgrade":
        command.upgrade(alembic_cfg, "head")
    elif direction == "downgrade":
        command.downgrade(alembic_cfg, "base")


@pytest_asyncio.fixture
async def migrated_engine():
    """Create engine and run alembic migrations."""
    engine = create_async_engine(DB_URL, echo=False, poolclass=pool.NullPool)

    # Run alembic migrations
    run_alembic_migrations(DB_URL, "upgrade")

    yield engine

    # Cleanup - drop all tables via alembic downgrade
    run_alembic_migrations(DB_URL, "downgrade")
    await engine.dispose()


@pytest_asyncio.fixture
async def uow(migrated_engine):
    """UnitOfWork with alembic-migrated schema."""
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    uow = SQLAlchemyUnitOfWork(session_factory)
    yield uow


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
