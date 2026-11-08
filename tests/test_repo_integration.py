"""Интеграционные тесты слоя данных на реальном PostgreSQL."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import job_queue, models, repo
from app.domain import ledger, order_service
from app.domain.result import Ok

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 6, tzinfo=UTC)
# claim_job сравнивает next_attempt_at с переданным временем, а колонка
# заполняется серверным now(): берём заведомо будущий момент, иначе тест
# зависит от календарной даты запуска.
CLAIM_AT = datetime.now(UTC) + timedelta(minutes=1)


def build_template() -> models.Template:
    return models.Template(
        key="integration",
        title="Интеграционный шаблон",
        source_path="templates/integration/source.mp4",
        prompt="Заменить лицо в видео.",
        duration_sec=5,
        resolution="720p",
        credits_cost=1,
        price_kopecks=29900,
        is_active=True,
    )


async def add_template(session: AsyncSession) -> models.Template:
    template = build_template()
    session.add(template)
    await session.flush()
    return template


async def test_order_is_not_active_before_payment(session: AsyncSession) -> None:
    user = await repo.get_or_create_user(session, 900001)
    template = await add_template(session)

    order = await repo.create_order(session, repo.NewOrder(user.id, template))

    assert order.status.value == "created"
    assert await repo.get_active_order(session, user.id) is None


async def test_order_becomes_active_after_payment(session: AsyncSession) -> None:
    user = await repo.get_or_create_user(session, 900002)
    template = await add_template(session)
    order = await repo.create_order(session, repo.NewOrder(user.id, template))

    paid = order_service.pay(order, NOW)
    assert isinstance(paid, Ok)
    await repo.save_order(session, paid.value)

    active = await repo.get_active_order(session, user.id)
    assert active is not None
    assert active.id == order.id
    assert active.paid_at == NOW


async def test_claim_job_takes_job_only_once(session: AsyncSession) -> None:
    user = await repo.get_or_create_user(session, 900003)
    template = await add_template(session)
    order = await repo.create_order(session, repo.NewOrder(user.id, template))
    await job_queue.create_job(session, job_queue.JobRequest(order.id, "mock", f"{order.id}:1"))

    claimed = await job_queue.claim_job(session, CLAIM_AT)

    assert claimed is not None
    assert claimed.order_id == order.id
    assert await job_queue.claim_job(session, CLAIM_AT) is None


async def test_ledger_entries_sum_to_zero_after_charge(session: AsyncSession) -> None:
    user = await repo.get_or_create_user(session, 900004)
    template = await add_template(session)
    order = await repo.create_order(session, repo.NewOrder(user.id, template))

    top_up = ledger.top_up(order)
    charge = ledger.debit(order, [])
    assert isinstance(top_up, Ok)
    assert isinstance(charge, Ok)
    await repo.add_ledger_entry(session, top_up.value)
    await repo.add_ledger_entry(session, charge.value)

    entries = await repo.load_ledger(session, user.id)

    assert sum(entry.delta for entry in entries) == 0
