"""Стейт-машина заказа: переходы только через чистые функции."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from app.domain.result import Err, Ok, Result


class OrderStatus(StrEnum):
    """Статусы заказа из docs/architecture.md §5."""

    CREATED = "created"
    PAID = "paid"
    QUEUED = "queued"
    RUNNING = "running"
    DELIVERED = "delivered"
    PURGED = "purged"
    FAILED = "failed"
    REJECTED = "rejected"
    REFUNDED = "refunded"


@dataclass(frozen=True)
class Order:
    """Заказ с ценой и кредитами, зафиксированными на момент создания."""

    id: int
    user_id: int
    template_id: int
    status: OrderStatus
    price_kopecks: int
    credits_cost: int
    created_at: datetime
    paid_at: datetime | None = None
    delivered_at: datetime | None = None
    payment_provider: str | None = None
    payment_id: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class AlreadyPaid:
    """Заказ уже оплачен: второе списание не создаётся."""

    order_id: int


@dataclass(frozen=True)
class PaymentRef:
    """Идентификаторы платежа, привязанного к заказу."""

    provider: str
    payment_id: str


@dataclass(frozen=True)
class IllegalTransition:
    """Переход не разрешён таблицей TRANSITIONS."""

    order_id: int
    current: OrderStatus
    target: OrderStatus


type OrderError = AlreadyPaid | IllegalTransition

ACTIVE_STATUSES: frozenset[OrderStatus] = frozenset(
    {OrderStatus.PAID, OrderStatus.QUEUED, OrderStatus.RUNNING}
)

TRANSITIONS: Mapping[OrderStatus, frozenset[OrderStatus]] = MappingProxyType(
    {
        OrderStatus.CREATED: frozenset({OrderStatus.PAID}),
        OrderStatus.PAID: frozenset({OrderStatus.QUEUED, OrderStatus.FAILED, OrderStatus.REJECTED}),
        OrderStatus.QUEUED: frozenset(
            {OrderStatus.RUNNING, OrderStatus.FAILED, OrderStatus.REJECTED}
        ),
        OrderStatus.RUNNING: frozenset(
            {OrderStatus.DELIVERED, OrderStatus.FAILED, OrderStatus.REJECTED}
        ),
        OrderStatus.DELIVERED: frozenset({OrderStatus.PURGED}),
        OrderStatus.FAILED: frozenset({OrderStatus.REFUNDED}),
        OrderStatus.REJECTED: frozenset({OrderStatus.REFUNDED}),
        OrderStatus.REFUNDED: frozenset(),
        OrderStatus.PURGED: frozenset(),
    }
)


def transition(order: Order, target: OrderStatus, now: datetime) -> Result[Order, OrderError]:
    """Переводит заказ в target, если переход разрешён таблицей."""
    if target not in TRANSITIONS[order.status]:
        return Err(IllegalTransition(order.id, order.status, target))
    return Ok(_stamp(replace(order, status=target), target, now))


def pay(order: Order, now: datetime) -> Result[Order, OrderError]:
    """Оплата: created → paid; повторная оплата отклоняется как AlreadyPaid."""
    if order.status is OrderStatus.PAID:
        return Err(AlreadyPaid(order.id))
    return transition(order, OrderStatus.PAID, now)


def attach_payment(order: Order, payment: PaymentRef) -> Order:
    """Записывает в заказ провайдера и идентификатор платежа."""
    return replace(
        order,
        payment_provider=payment.provider,
        payment_id=payment.payment_id,
    )


def enqueue(order: Order, now: datetime) -> Result[Order, OrderError]:
    """Постановка в очередь после приёма фото: paid → queued."""
    return transition(order, OrderStatus.QUEUED, now)


def start(order: Order, now: datetime) -> Result[Order, OrderError]:
    """Начало работы воркера: queued → running."""
    return transition(order, OrderStatus.RUNNING, now)


def deliver(order: Order, now: datetime) -> Result[Order, OrderError]:
    """Успех: running → delivered с отметкой delivered_at."""
    return transition(order, OrderStatus.DELIVERED, now)


def fail(order: Order, now: datetime, error_code: str) -> Result[Order, OrderError]:
    """Провал: paid/queued/running → failed с кодом причины."""
    return transition(replace(order, error_code=error_code), OrderStatus.FAILED, now)


def reject(order: Order, now: datetime, error_code: str) -> Result[Order, OrderError]:
    """Отказ модерации движка: paid/queued/running → rejected."""
    return transition(replace(order, error_code=error_code), OrderStatus.REJECTED, now)


def mark_refunded(order: Order, now: datetime) -> Result[Order, OrderError]:
    """Фиксация возврата кредитов: failed/rejected → refunded."""
    return transition(order, OrderStatus.REFUNDED, now)


def purge(order: Order, now: datetime) -> Result[Order, OrderError]:
    """Удаление результата: delivered → purged."""
    return transition(order, OrderStatus.PURGED, now)


def is_active(order: Order) -> bool:
    """Заказ активен в paid/queued/running: второй заказ создавать нельзя."""
    return order.status in ACTIVE_STATUSES


def is_awaiting_photo(order: Order) -> bool:
    """Заказ оплачен и ждёт фото: только в этом состоянии фото принимается."""
    return order.status is OrderStatus.PAID


def _stamp(order: Order, target: OrderStatus, now: datetime) -> Order:
    if target is OrderStatus.PAID:
        return replace(order, paid_at=now)
    if target is OrderStatus.DELIVERED:
        return replace(order, delivered_at=now)
    return order
