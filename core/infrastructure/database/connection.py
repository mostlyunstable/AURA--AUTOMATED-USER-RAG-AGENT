from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def get_engine(database_url: str):
    return create_async_engine(database_url, echo=False, poolclass=pool.NullPool)


def get_session_maker(engine):
    return async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
