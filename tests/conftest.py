"""Фикстуры интеграционных тестов: схема на воркера и откат транзакции.

Каждый воркер pytest-xdist получает свою схему в тестовой базе, поэтому
тесты не мешают друг другу. Внутри теста всё живёт в одной транзакции,
которая откатывается в конце: коммиты приложения превращаются в savepoint.
"""

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.models import Base

DEFAULT_TEST_URL = "postgresql+asyncpg://user:pass@localhost:5433/facechanger_test"
WORKER = os.getenv("PYTEST_XDIST_WORKER", "master")
SCHEMA = f"test_{WORKER}"


def test_database_url() -> str:
    return os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_URL)


def build_engine(schema: str) -> AsyncEngine:
    """Движок, у которого все таблицы живут в схеме конкретного воркера."""
    return create_async_engine(
        test_database_url(),
        connect_args={"server_settings": {"search_path": f"{schema},public"}},
    )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_schema() -> AsyncIterator[str]:
    """Создаёт схему воркера и таблицы; без PostgreSQL тесты пропускаются."""
    engine = build_engine(SCHEMA)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
            await connection.run_sync(Base.metadata.create_all)
    except (SQLAlchemyError, OSError) as error:
        await engine.dispose()
        pytest.skip(f"PostgreSQL недоступен: {error}")
    yield SCHEMA
    async with engine.begin() as connection:
        await connection.execute(text(f'DROP SCHEMA "{SCHEMA}" CASCADE'))
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="function")
async def session(db_schema: str) -> AsyncIterator[AsyncSession]:
    """Сессия в транзакции, которая откатывается после теста."""
    engine = build_engine(db_schema)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        db_session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield db_session
        finally:
            await db_session.close()
            await transaction.rollback()
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="function")
async def session_factory(session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    """Фабрика сессий поверх транзакции теста: коммиты становятся savepoint."""
    return async_sessionmaker(
        bind=session.bind,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
