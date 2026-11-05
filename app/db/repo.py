"""Тонкий слой хранения поверх SQLAlchemy: чтение, запись, никаких правил."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.domain.ledger import LedgerEntry, LedgerReason
from app.domain.order_service import ACTIVE_STATUSES, Order, OrderStatus
from app.domain.pricing import Tariff
from app.domain.pricing import quote as quote_price
from app.domain.result import Err


class JobStatus(StrEnum):
    """Статусы задания, которыми оперирует воркер."""

    NEW = "new"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class NewOrder:
    """Данные для создания заказа: владелец и выбранный шаблон."""

    user_id: int
    template: models.Template


@dataclass(frozen=True)
class ConsentRecord:
    """Зафиксированное согласие пользователя."""

    version: str
    at: datetime


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


@dataclass(frozen=True)
class JobOutcome:
    """Терминальный статус задания."""

    job_id: int
    status: JobStatus
    finished_at: datetime
    error_code: str | None = None


@dataclass(frozen=True)
class EventRecord:
    """Событие для таблицы events."""

    name: str
    user_id: int | None = None
    props: Mapping[str, Any] = field(default_factory=dict)


async def get_user_by_tg_id(session: AsyncSession, tg_id: int) -> models.User | None:
    statement = select(models.User).where(models.User.tg_id == tg_id)
    return (await session.execute(statement)).scalar_one_or_none()


async def get_or_create_user(session: AsyncSession, tg_id: int) -> models.User:
    user = await get_user_by_tg_id(session, tg_id)
    if user is not None:
        return user
    user = models.User(tg_id=tg_id)
    session.add(user)
    await session.flush()
    return user


async def load_user(session: AsyncSession, user_id: int) -> models.User | None:
    return await session.get(models.User, user_id)


async def record_consent(session: AsyncSession, user: models.User, consent: ConsentRecord) -> None:
    user.consent_version = consent.version
    user.consent_at = consent.at
    await session.flush()


async def get_default_template(session: AsyncSession) -> models.Template | None:
    statement = (
        select(models.Template)
        .where(models.Template.is_active.is_(True))
        .order_by(models.Template.id)
        .limit(1)
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def load_template(session: AsyncSession, template_id: int) -> models.Template | None:
    return await session.get(models.Template, template_id)


async def count_templates(session: AsyncSession) -> int:
    statement = select(func.count()).select_from(models.Template)
    return int((await session.execute(statement)).scalar_one())


async def create_order(session: AsyncSession, request: NewOrder) -> Order:
    template = request.template
    price = quote_price(Tariff(template.id, template.price_kopecks, template.credits_cost))
    if isinstance(price, Err):
        raise ValueError(f"Некорректный тариф шаблона: {price.error}")
    row = models.Order(
        user_id=request.user_id,
        template_id=template.id,
        status=OrderStatus.CREATED.value,
        price_kopecks=price.value.price_kopecks,
        credits_cost=price.value.credits_cost,
    )
    session.add(row)
    await session.flush()
    return to_order(row)


async def load_order(
    session: AsyncSession, order_id: int, *, for_update: bool = False
) -> Order | None:
    statement = select(models.Order).where(models.Order.id == order_id)
    if for_update:
        statement = statement.with_for_update()
    row = (await session.execute(statement)).scalar_one_or_none()
    return to_order(row) if row is not None else None


async def save_order(session: AsyncSession, order: Order) -> None:
    row = await session.get(models.Order, order.id)
    if row is None:
        raise LookupError(f"Заказ {order.id} не найден")
    row.status = order.status.value
    row.paid_at = order.paid_at
    row.delivered_at = order.delivered_at
    row.payment_provider = order.payment_provider
    row.payment_id = order.payment_id
    row.error_code = order.error_code
    await session.flush()


async def get_active_order(session: AsyncSession, user_id: int) -> Order | None:
    statuses = tuple(status.value for status in ACTIVE_STATUSES)
    statement = (
        select(models.Order)
        .where(models.Order.user_id == user_id, models.Order.status.in_(statuses))
        .order_by(models.Order.id.desc())
        .limit(1)
    )
    row = (await session.execute(statement)).scalar_one_or_none()
    return to_order(row) if row is not None else None


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
    return ClaimedJob(row.id, row.order_id, row.engine, row.idempotency_key, row.attempt)


async def finish_job(session: AsyncSession, outcome: JobOutcome) -> None:
    row = await session.get(models.Job, outcome.job_id)
    if row is None:
        return
    row.status = outcome.status.value
    row.finished_at = outcome.finished_at
    row.error_code = outcome.error_code
    await session.flush()


async def load_ledger(session: AsyncSession, user_id: int) -> list[LedgerEntry]:
    statement = select(models.LedgerEntry).where(models.LedgerEntry.user_id == user_id)
    rows = (await session.execute(statement)).scalars().all()
    return [to_ledger_entry(row) for row in rows]


async def load_order_ledger(session: AsyncSession, order_id: int) -> list[LedgerEntry]:
    statement = select(models.LedgerEntry).where(models.LedgerEntry.order_id == order_id)
    rows = (await session.execute(statement)).scalars().all()
    return [to_ledger_entry(row) for row in rows]


async def add_ledger_entry(session: AsyncSession, entry: LedgerEntry) -> None:
    session.add(
        models.LedgerEntry(
            user_id=entry.user_id,
            delta=entry.delta,
            reason=entry.reason.value,
            order_id=entry.order_id,
        )
    )
    await session.flush()


async def record_event(session: AsyncSession, event: EventRecord) -> None:
    session.add(
        models.Event(
            user_id=event.user_id,
            name=event.name,
            props=dict(event.props),
        )
    )
    await session.flush()


def to_order(row: models.Order) -> Order:
    """Превращает строку в неизменяемый доменный заказ."""
    return Order(
        id=row.id,
        user_id=row.user_id,
        template_id=row.template_id,
        status=OrderStatus(row.status),
        price_kopecks=row.price_kopecks,
        credits_cost=row.credits_cost,
        created_at=row.created_at,
        paid_at=row.paid_at,
        delivered_at=row.delivered_at,
        payment_provider=row.payment_provider,
        payment_id=row.payment_id,
        error_code=row.error_code,
    )


def to_ledger_entry(row: models.LedgerEntry) -> LedgerEntry:
    """Превращает строку ledger в доменную запись."""
    return LedgerEntry(
        user_id=row.user_id,
        delta=row.delta,
        reason=LedgerReason(row.reason),
        order_id=row.order_id,
    )
