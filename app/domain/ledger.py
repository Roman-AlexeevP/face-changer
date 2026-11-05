"""Ledger: баланс меняется только записями, записи — значения."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.domain.order_service import Order, OrderStatus
from app.domain.result import Err, Ok, Result


class LedgerReason(StrEnum):
    """Причины записей ledger из спецификации billing."""

    TOPUP = "topup"
    ORDER_PAID = "order_paid"
    REFUND = "refund"


@dataclass(frozen=True)
class LedgerEntry:
    """Одна запись ledger: изменение баланса пользователя."""

    user_id: int
    delta: int
    reason: LedgerReason
    order_id: int


@dataclass(frozen=True)
class InvalidAmount:
    """Стоимость заказа в кредитах должна быть положительной."""

    amount: int


@dataclass(frozen=True)
class AlreadyCharged:
    """По заказу уже есть списание: повторная оплата не списывает дважды."""

    order_id: int


@dataclass(frozen=True)
class AlreadyRefunded:
    """По заказу уже есть возврат: второй возврат невозможен."""

    order_id: int


@dataclass(frozen=True)
class OrderNotRefundable:
    """Возврат допустим только для failed/rejected."""

    order_id: int
    status: OrderStatus


type LedgerError = InvalidAmount | AlreadyCharged | AlreadyRefunded | OrderNotRefundable

REFUNDABLE_STATUSES: frozenset[OrderStatus] = frozenset({OrderStatus.FAILED, OrderStatus.REJECTED})


def top_up(order: Order) -> Result[LedgerEntry, LedgerError]:
    """Возвращает запись пополнения кредитов на стоимость оплаченного заказа."""
    if order.credits_cost <= 0:
        return Err(InvalidAmount(order.credits_cost))
    return Ok(
        LedgerEntry(
            user_id=order.user_id,
            delta=order.credits_cost,
            reason=LedgerReason.TOPUP,
            order_id=order.id,
        )
    )


def debit(order: Order, entries: Sequence[LedgerEntry]) -> Result[LedgerEntry, LedgerError]:
    """Возвращает запись списания за заказ, не выполняя I/O."""
    if order.credits_cost <= 0:
        return Err(InvalidAmount(order.credits_cost))
    if _has_reason(entries, LedgerReason.ORDER_PAID, order.id):
        return Err(AlreadyCharged(order.id))
    return Ok(
        LedgerEntry(
            user_id=order.user_id,
            delta=-order.credits_cost,
            reason=LedgerReason.ORDER_PAID,
            order_id=order.id,
        )
    )


def refund(order: Order, entries: Sequence[LedgerEntry]) -> Result[LedgerEntry, LedgerError]:
    """Возвращает запись возврата за заказ; второй возврат отклоняется."""
    if _has_reason(entries, LedgerReason.REFUND, order.id):
        return Err(AlreadyRefunded(order.id))
    if order.status not in REFUNDABLE_STATUSES:
        return Err(OrderNotRefundable(order.id, order.status))
    if order.credits_cost <= 0:
        return Err(InvalidAmount(order.credits_cost))
    return Ok(
        LedgerEntry(
            user_id=order.user_id,
            delta=order.credits_cost,
            reason=LedgerReason.REFUND,
            order_id=order.id,
        )
    )


def calculate_balance(user_id: int, entries: Sequence[LedgerEntry]) -> int:
    """Сумма записей пользователя; самый дешёвый способ узнать баланс."""
    return sum(entry.delta for entry in entries if entry.user_id == user_id)


def _has_reason(entries: Sequence[LedgerEntry], reason: LedgerReason, order_id: int) -> bool:
    return any(entry.reason == reason and entry.order_id == order_id for entry in entries)
