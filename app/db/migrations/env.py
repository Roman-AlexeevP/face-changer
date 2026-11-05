"""Окружение Alembic: URL базы берётся из настроек, а не из ini."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import ConfigError, load_settings
from app.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def load_database_url() -> str:
    try:
        return load_settings().database_url
    except ConfigError as error:
        raise RuntimeError(f"Не удалось прочитать DATABASE_URL: {error}") from error


def run_migrations_offline() -> None:
    context.configure(
        url=load_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_async_engine(load_database_url(), poolclass=pool.NullPool)
    asyncio.run(apply_migrations(engine))


async def apply_migrations(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await connection.run_sync(run_sync_migrations)
    await engine.dispose()


def run_sync_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
