"""Тесты ledger: записи как значения, двойное списание и двойной возврат."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from app.domain.ledger import (
    AlreadyCharged,
    AlreadyRefunded,
    InvalidAmount,
    LedgerEntry,
    LedgerReason,
    OrderNotRefundable,
    calculate_balance,
    debit,
    refund,
    top_up,
)
from app.domain.order_service import Order, OrderStatus
from app.domain.result import Err, Ok

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def make_order(status: OrderStatus = OrderStatus.PAID, credits_cost: int = 2) -> Order:
    return Order(
        id=1,
        user_id=10,
        template_id=20,
        status=status,
        price_kopecks=9900,
        credits_cost=credits_cost,
        created_at=NOW,
    )


def make_entry(
    order_id: int = 1,
    user_id: int = 10,
    delta: int = -2,
    reason: LedgerReason = LedgerReason.ORDER_PAID,
) -> LedgerEntry:
    return LedgerEntry(user_id=user_id, delta=delta, reason=reason, order_id=order_id)


def test_debit_returns_charge_entry() -> None:
    assert debit(make_order(), []) == Ok(
        LedgerEntry(user_id=10, delta=-2, reason=LedgerReason.ORDER_PAID, order_id=1)
    )


def test_top_up_returns_positive_entry() -> None:
    assert top_up(make_order()) == Ok(
        LedgerEntry(user_id=10, delta=2, reason=LedgerReason.TOPUP, order_id=1)
    )


def test_top_up_rejects_non_positive_credits() -> None:
    assert top_up(make_order(credits_cost=0)) == Err(InvalidAmount(0))


def test_debit_is_not_an_io_operation() -> None:
    order = make_order()
    entries: list[LedgerEntry] = []
    assert isinstance(debit(order, entries), Ok)
    assert entries == []


def test_second_debit_for_same_order_is_rejected() -> None:
    assert debit(make_order(), [make_entry(delta=-2)]) == Err(AlreadyCharged(1))


def test_debit_for_another_order_is_allowed() -> None:
    assert debit(make_order(), [make_entry(order_id=99)]) == Ok(
        LedgerEntry(user_id=10, delta=-2, reason=LedgerReason.ORDER_PAID, order_id=1)
    )


def test_debit_rejects_non_positive_credits() -> None:
    assert debit(make_order(credits_cost=0), []) == Err(InvalidAmount(0))


def test_refund_failed_order_returns_credits() -> None:
    assert refund(make_order(OrderStatus.FAILED), [make_entry()]) == Ok(
        make_entry(delta=2, reason=LedgerReason.REFUND)
    )


def test_refund_rejected_order_returns_credits() -> None:
    assert refund(make_order(OrderStatus.REJECTED), []) == Ok(
        make_entry(delta=2, reason=LedgerReason.REFUND)
    )


def test_second_refund_for_same_order_is_rejected() -> None:
    entries = [make_entry(), make_entry(delta=2, reason=LedgerReason.REFUND)]
    assert refund(make_order(OrderStatus.FAILED), entries) == Err(AlreadyRefunded(1))


def test_refund_after_already_refunded_order_is_rejected() -> None:
    order = make_order(OrderStatus.REFUNDED)
    entries = [make_entry(), make_entry(delta=2, reason=LedgerReason.REFUND)]
    assert refund(order, entries) == Err(AlreadyRefunded(1))


def test_refund_for_delivered_order_is_rejected() -> None:
    assert refund(make_order(OrderStatus.DELIVERED), [make_entry()]) == Err(
        OrderNotRefundable(1, OrderStatus.DELIVERED)
    )


def test_refund_rejects_non_positive_credits() -> None:
    assert refund(make_order(OrderStatus.FAILED, credits_cost=0), []) == Err(InvalidAmount(0))


def test_balance_sums_entries_of_one_user() -> None:
    entries = [
        make_entry(user_id=10, delta=-2),
        make_entry(order_id=2, user_id=10, delta=5),
        make_entry(user_id=11, delta=100),
    ]
    assert calculate_balance(10, entries) == 3
    assert calculate_balance(11, entries) == 100
    assert calculate_balance(12, entries) == 0


def test_balance_after_charge_and_refund_is_zero() -> None:
    order = make_order(OrderStatus.FAILED)
    charge = debit(replace(order, status=OrderStatus.PAID), [])
    assert isinstance(charge, Ok)
    refunded = refund(order, [charge.value])
    assert isinstance(refunded, Ok)
    assert calculate_balance(order.user_id, [charge.value, refunded.value]) == 0


def test_ledger_entry_is_immutable() -> None:
    entry = make_entry()
    with pytest.raises(FrozenInstanceError):
        entry.delta = 0
