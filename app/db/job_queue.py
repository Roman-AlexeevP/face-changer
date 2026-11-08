"""Очередь заданий: статусы, claim, finish и служебные переходы."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models


class JobStatus(StrEnum):
    """Статусы задания, которыми оперирует воркер."""

    NEW = "new"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class JobRequest:
    """Данные для постановки задания в очередь."""

    order_id: int
    engine: str
    idempotency_key: str
    attempt: int = 1


@dataclass(frozen=True)
class ClaimedJob:
    """Снимок задания, взятого воркером через SKIP LOCKED."""

    id: int
    order_id: int
    engine: str
    idempotency_key: str
    attempt: int
    request_id: str | None = None


@dataclass(frozen=True)
class JobOutcome:
    """Терминальный статус задания."""

    job_id: int
    status: JobStatus
    finished_at: datetime
    error_code: str | None = None


async def create_job(session: AsyncSession, request: JobRequest) -> None:
    session.add(
        models.Job(
            order_id=request.order_id,
            attempt=request.attempt,
            engine=request.engine,
            status=JobStatus.NEW.value,
            idempotency_key=request.idempotency_key,
        )
    )
    await session.flush()


async def claim_job(session: AsyncSession, now: datetime) -> ClaimedJob | None:
    statement = (
        select(models.Job)
        .where(
            models.Job.status == JobStatus.NEW.value,
            models.Job.next_attempt_at <= now,
        )
        .order_by(models.Job.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    row = (await session.execute(statement)).scalar_one_or_none()
    if row is None:
        return None
    row.status = JobStatus.RUNNING.value
    row.submitted_at = now
    await session.flush()
    return ClaimedJob(
        row.id,
        row.order_id,
        row.engine,
        row.idempotency_key,
        row.attempt,
        row.request_id,
    )


async def finish_job(session: AsyncSession, outcome: JobOutcome) -> None:
    row = await session.get(models.Job, outcome.job_id)
    if row is None:
        return
    row.status = outcome.status.value
    row.finished_at = outcome.finished_at
    row.error_code = outcome.error_code
    await session.flush()


async def mark_submitted(session: AsyncSession, job_id: int, request_id: str) -> None:
    """Сохраняет request_id сразу после submit, чтобы пережить рестарт."""
    row = await session.get(models.Job, job_id)
    if row is None:
        return
    row.request_id = request_id
    await session.flush()


async def reschedule_job(
    session: AsyncSession,
    job_id: int,
    *,
    attempt: int,
    idempotency_key: str,
    next_attempt_at: datetime,
) -> None:
    """Возвращает задание в new с новой попыткой и ключом."""
    row = await session.get(models.Job, job_id)
    if row is None:
        return
    row.status = JobStatus.NEW.value
    row.attempt = attempt
    row.idempotency_key = idempotency_key
    row.next_attempt_at = next_attempt_at
    row.submitted_at = None
    row.finished_at = None
    row.error_code = None
    await session.flush()


async def list_stale_jobs(session: AsyncSession, cutoff: datetime) -> list[models.Job]:
    """Задания, висящие в running дольше порога."""
    statement = select(models.Job).where(
        models.Job.status == JobStatus.RUNNING.value,
        models.Job.submitted_at < cutoff,
    )
    return list((await session.execute(statement)).scalars())
