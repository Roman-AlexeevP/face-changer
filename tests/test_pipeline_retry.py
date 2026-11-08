"""Повторы и отказы пайплайна на фейковом движке и реальной PostgreSQL."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import job_queue, models, repo
from app.domain import ledger, order_service, sales
from app.domain.order_service import OrderStatus
from app.domain.result import Ok
from app.engines.base import (
    EngineFailed,
    EngineNoCredits,
    EngineResult,
    EngineStatus,
)
from app.storage.local import LocalStorage
from app.worker.pipeline import process_job
from app.worker.services import WorkerServices

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5433/facechanger_test"


@dataclass
class FakeBot:
    messages: list[tuple[int, str]] = field(default_factory=list)

    async def send_message(self, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))


@dataclass
class ScriptedEngine:
    outcomes: list[object]
    calls: list[object] = field(default_factory=list)

    async def generate(self, spec: object, *, on_submit: object = None) -> EngineResult:
        self.calls.append(spec)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def build_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=DATABASE_URL,
        engine="mock",
        payment_provider="stub",
        storage_dir=tmp_path,
        job_stale_minutes=12,
    )


def build_template() -> models.Template:
    return models.Template(
        key="retry",
        title="Retry",
        source_path="templates/retry/source.mp4",
        prompt="replace face",
        duration_sec=5,
        resolution="720p",
        credits_cost=1,
        price_kopecks=100,
        is_active=True,
    )


async def build_order(session: AsyncSession) -> int:
    user = await repo.get_or_create_user(session, 7001)
    template = build_template()
    session.add(template)
    await session.flush()
    order = await repo.create_order(session, repo.NewOrder(user.id, template))
    paid = order_service.pay(order, NOW)
    assert isinstance(paid, Ok)
    queued = order_service.enqueue(paid.value, NOW)
    assert isinstance(queued, Ok)
    await repo.save_order(session, queued.value)
    topup = ledger.top_up(queued.value)
    charge = ledger.debit(queued.value, [])
    assert isinstance(topup, Ok)
    assert isinstance(charge, Ok)
    await repo.add_ledger_entry(session, topup.value)
    await repo.add_ledger_entry(session, charge.value)
    await job_queue.create_job(
        session, job_queue.JobRequest(queued.value.id, "mock", f"{queued.value.id}:1")
    )
    return queued.value.id


async def build_services(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    outcomes: list[object],
) -> tuple[WorkerServices, ScriptedEngine, int]:
    order_id = await build_order(session)
    engine = ScriptedEngine(outcomes)
    services = WorkerServices(
        settings=build_settings(tmp_path),
        session_factory=session_factory,
        bot=FakeBot(),
        engine=engine,
        storage=LocalStorage(tmp_path),
        now=lambda: NOW,
    )
    return services, engine, order_id


async def claim(session: AsyncSession) -> job_queue.ClaimedJob:
    claimed = await job_queue.claim_job(session, datetime.now(UTC) + timedelta(minutes=1))
    assert claimed is not None
    return claimed


def reasons(entries: list[ledger.LedgerEntry]) -> list[ledger.LedgerReason]:
    return [entry.reason for entry in entries]


@pytest.mark.integration
async def test_retryable_error_reschedules_job(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    services, engine, order_id = await build_services(
        session, session_factory, tmp_path, [EngineFailed("boom", code="engine_5xx")]
    )

    claimed = await claim(session)
    await process_job(services, claimed)

    order = await repo.load_order(session, order_id)
    assert order is not None
    assert order.status is OrderStatus.QUEUED
    job = await session.get(models.Job, claimed.id)
    assert job is not None
    assert job.status == job_queue.JobStatus.NEW.value
    assert job.attempt == 2
    assert job.idempotency_key == f"{order_id}:2"
    assert job.error_code is None
    assert len(engine.calls) == 1
    assert reasons(await repo.load_order_ledger(session, order_id)) == [
        ledger.LedgerReason.TOPUP,
        ledger.LedgerReason.ORDER_PAID,
    ]


@pytest.mark.integration
async def test_exhausted_retries_fail_and_refund_once(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    outcomes: list[object] = [EngineFailed("boom", code="engine_5xx") for _ in range(4)]
    services, engine, order_id = await build_services(session, session_factory, tmp_path, outcomes)

    for _ in range(4):
        claimed = await claim(session)
        await process_job(services, claimed)

    order = await repo.load_order(session, order_id)
    assert order is not None
    assert order.status is OrderStatus.REFUNDED
    job = await session.get(models.Job, claimed.id)
    assert job is not None
    assert job.status == job_queue.JobStatus.FAILED.value
    assert job.attempt == 4
    assert job.error_code == "engine_5xx"
    assert len(engine.calls) == 4

    entries = await repo.load_order_ledger(session, order_id)
    assert reasons(entries) == [
        ledger.LedgerReason.TOPUP,
        ledger.LedgerReason.ORDER_PAID,
        ledger.LedgerReason.REFUND,
    ]
    assert sum(entry.delta for entry in entries) == 1

    events = (
        (await session.execute(select(models.Event).where(models.Event.name == "refund_issued")))
        .scalars()
        .all()
    )
    assert len(events) == 1


@pytest.mark.integration
async def test_unknown_provider_code_is_sanitized(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    raw = {
        "error": {"code": "face_not_found"},
        "video": {"url": "https://signed.example/secret"},
    }
    services, engine, order_id = await build_services(
        session,
        session_factory,
        tmp_path,
        [EngineResult(EngineStatus.FAILED, error_code="face_not_found", raw=raw)],
    )

    claimed = await claim(session)
    await process_job(services, claimed)

    order = await repo.load_order(session, order_id)
    assert order is not None
    assert order.status is OrderStatus.REFUNDED
    job = await session.get(models.Job, claimed.id)
    assert job is not None
    assert job.error_code == "unknown"
    assert len(engine.calls) == 1
    events = (
        (await session.execute(select(models.Event).where(models.Event.name == "engine_unknown")))
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].props["raw"]["video"]["url"] == "[redacted]"
    assert events[0].props["raw"]["error"]["code"] == "face_not_found"


@pytest.mark.integration
async def test_no_credits_is_not_retried(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    services, engine, order_id = await build_services(
        session, session_factory, tmp_path, [EngineNoCredits("no credits")]
    )

    await process_job(services, await claim(session))

    order = await repo.load_order(session, order_id)
    assert order is not None
    assert order.status is OrderStatus.REFUNDED
    assert len(engine.calls) == 1
    flag = await repo.read_flag(session, sales.SALES_BLOCK_FLAG)
    assert flag is not None


@pytest.mark.integration
async def test_moderated_is_not_retried(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    services, engine, order_id = await build_services(
        session,
        session_factory,
        tmp_path,
        [EngineResult(EngineStatus.REJECTED, error_code="moderated")],
    )

    await process_job(services, await claim(session))

    order = await repo.load_order(session, order_id)
    assert order is not None
    assert order.status is OrderStatus.REFUNDED
    assert len(engine.calls) == 1
