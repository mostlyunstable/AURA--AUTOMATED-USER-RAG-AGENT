"""Integration test configuration using Alembic migrations."""

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from alembic import command
from alembic.config import Config
from core.infrastructure.database.repositories import SQLAlchemyUnitOfWork

DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://aura:aura@localhost:5432/aura"
)
if "sqlite" in DB_URL:
    raise RuntimeError(
        "Integration tests MUST run against PostgreSQL. SQLite fallback is disabled."
    )


def run_alembic_migrations(database_url: str, direction: str = "upgrade") -> None:
    """Run alembic migrations programmatically."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    if direction == "upgrade":
        command.upgrade(alembic_cfg, "head")
    elif direction == "downgrade":
        command.downgrade(alembic_cfg, "base")


@pytest_asyncio.fixture(scope="function")
async def migrated_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create engine and run alembic migrations for each test function."""
    engine = create_async_engine(DB_URL, echo=False, poolclass=pool.NullPool)

    # Run alembic migrations
    run_alembic_migrations(DB_URL, "upgrade")

    yield engine

    # Cleanup - drop all tables via alembic downgrade
    run_alembic_migrations(DB_URL, "downgrade")
    await engine.dispose()


@pytest_asyncio.fixture
async def uow(migrated_engine: AsyncEngine):
    """UnitOfWork with alembic-migrated schema."""
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    uow = SQLAlchemyUnitOfWork(session_factory)
    yield uow
