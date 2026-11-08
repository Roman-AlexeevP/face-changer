"""Сторож возвращает зависшие running-задания в очередь."""

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import job_queue, models, repo
from app.domain import order_service
from app.domain.order_service import OrderStatus
from app.domain.result import Ok
from app.engines.mock import MockVideoEngine
from app.storage.local import LocalStorage
from app.worker.services import WorkerServices
from app.worker.watchdog import cleanup_old_photos, requeue_stale

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5433/facechanger_test"


@dataclass
class FakeBot:
    messages: list[tuple[int, str]] = field(default_factory=list)

    async def send_message(self, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))


def build_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=DATABASE_URL,
        engine="mock",
        payment_provider="stub",
        storage_dir=tmp_path,
        job_stale_minutes=12,
    )


async def build_order(session: AsyncSession) -> int:
    user = await repo.get_or_create_user(session, 7101)
    template = models.Template(
        key="watchdog",
        title="Watchdog",
        source_path="templates/watchdog/source.mp4",
        prompt="replace face",
        duration_sec=5,
        resolution="720p",
        credits_cost=1,
        price_kopecks=100,
        is_active=True,
    )
    session.add(template)
    await session.flush()
    order = await repo.create_order(session, repo.NewOrder(user.id, template))
    paid = order_service.pay(order, NOW)
    assert isinstance(paid, Ok)
    queued = order_service.enqueue(paid.value, NOW)
    assert isinstance(queued, Ok)
    await repo.save_order(session, queued.value)
    await job_queue.create_job(
        session, job_queue.JobRequest(queued.value.id, "mock", f"{queued.value.id}:1")
    )
    return queued.value.id


async def build_services(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> WorkerServices:
    await build_order(session)
    return WorkerServices(
        settings=build_settings(tmp_path),
        session_factory=session_factory,
        bot=FakeBot(),
        engine=MockVideoEngine(tmp_path),
        storage=LocalStorage(tmp_path),
        now=lambda: NOW,
    )


async def mark_running(session: AsyncSession, submitted_at: datetime) -> job_queue.ClaimedJob:
    claimed = await job_queue.claim_job(session, datetime.now(UTC) + timedelta(minutes=1))
    assert claimed is not None
    order = await repo.load_order(session, claimed.order_id, for_update=True)
    assert order is not None
    started = order_service.start(order, NOW)
    assert isinstance(started, Ok)
    await repo.save_order(session, started.value)
    row = await session.get(models.Job, claimed.id)
    assert row is not None
    row.submitted_at = submitted_at
    await session.flush()
    return claimed


@pytest.mark.integration
async def test_stale_running_is_requeued(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    services = await build_services(session, session_factory, tmp_path)
    claimed = await mark_running(session, NOW - timedelta(minutes=20))

    count = await requeue_stale(services)

    assert count == 1
    order = await repo.load_order(session, claimed.order_id)
    assert order is not None
    assert order.status is OrderStatus.QUEUED
    job = await session.get(models.Job, claimed.id)
    assert job is not None
    assert job.status == job_queue.JobStatus.NEW.value
    assert job.attempt == 2
    assert job.idempotency_key == f"{claimed.order_id}:2"
    events = (
        (await session.execute(select(models.Event).where(models.Event.name == "job_stale")))
        .scalars()
        .all()
    )
    assert len(events) == 1


@pytest.mark.integration
async def test_young_running_is_not_requeued(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    services = await build_services(session, session_factory, tmp_path)
    claimed = await mark_running(session, NOW - timedelta(minutes=1))

    count = await requeue_stale(services)

    assert count == 0
    order = await repo.load_order(session, claimed.order_id)
    assert order is not None
    assert order.status is OrderStatus.RUNNING
    job = await session.get(models.Job, claimed.id)
    assert job is not None
    assert job.status == job_queue.JobStatus.RUNNING.value


def test_cleanup_old_photos_removes_only_expired(tmp_path: Path) -> None:
    old = tmp_path / "photo-old.jpg"
    old.write_bytes(b"old")
    os.utime(old, (NOW.timestamp() - 3600, NOW.timestamp() - 3600))
    fresh = tmp_path / "photo-fresh.jpg"
    fresh.write_bytes(b"fresh")
    os.utime(fresh, (NOW.timestamp(), NOW.timestamp()))

    removed = cleanup_old_photos(tmp_path, NOW, ttl_min=15)

    assert removed == 1
    assert not old.exists()
    assert fresh.exists()
