"""Тесты стейт-машины заказа: легальные и нелегальные переходы."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.domain.order_service import (
    ACTIVE_STATUSES,
    TRANSITIONS,
    AlreadyPaid,
    IllegalTransition,
    Order,
    OrderStatus,
    PaymentRef,
    attach_payment,
    deliver,
    enqueue,
    fail,
    is_active,
    is_awaiting_photo,
    mark_refunded,
    pay,
    purge,
    reject,
    start,
    transition,
)
from app.domain.result import Err, Ok

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
CREATED_AT = datetime(2026, 1, 15, 11, 0, tzinfo=UTC)


def make_order(status: OrderStatus = OrderStatus.CREATED) -> Order:
    return Order(
        id=1,
        user_id=10,
        template_id=20,
        status=status,
        price_kopecks=9900,
        credits_cost=2,
        created_at=CREATED_AT,
    )


def expected_order(order: Order, target: OrderStatus) -> Order:
    if target is OrderStatus.PAID:
        return replace(order, status=target, paid_at=NOW)
    if target is OrderStatus.DELIVERED:
        return replace(order, status=target, delivered_at=NOW)
    return replace(order, status=target)


def legal_pairs() -> list[tuple[OrderStatus, OrderStatus]]:
    return [(source, target) for source in OrderStatus for target in TRANSITIONS[source]]


def illegal_pairs() -> list[tuple[OrderStatus, OrderStatus]]:
    return [
        (source, target)
        for source in OrderStatus
        for target in OrderStatus
        if target not in TRANSITIONS[source]
    ]


def test_transitions_cover_every_status() -> None:
    assert set(TRANSITIONS) == set(OrderStatus)


@pytest.mark.parametrize(("source", "target"), legal_pairs())
def test_legal_transition_returns_updated_order(source: OrderStatus, target: OrderStatus) -> None:
    order = make_order(source)
    result = transition(order, target, NOW)
    assert result == Ok(expected_order(order, target))
    assert order.status is source


@pytest.mark.parametrize(("source", "target"), illegal_pairs())
def test_illegal_transition_returns_error(source: OrderStatus, target: OrderStatus) -> None:
    order = make_order(source)
    result = transition(order, target, NOW)
    assert result == Err(IllegalTransition(order.id, source, target))


def test_transition_to_same_status_is_illegal() -> None:
    order = make_order(OrderStatus.RUNNING)
    assert transition(order, OrderStatus.RUNNING, NOW) == Err(
        IllegalTransition(1, OrderStatus.RUNNING, OrderStatus.RUNNING)
    )


def test_pay_sets_paid_at() -> None:
    order = make_order()
    assert pay(order, NOW) == Ok(replace(order, status=OrderStatus.PAID, paid_at=NOW))


def test_pay_twice_returns_already_paid() -> None:
    order = make_order(OrderStatus.PAID)
    assert pay(order, NOW) == Err(AlreadyPaid(1))


def test_pay_after_failure_is_illegal_not_already_paid() -> None:
    order = make_order(OrderStatus.FAILED)
    assert pay(order, NOW) == Err(IllegalTransition(1, OrderStatus.FAILED, OrderStatus.PAID))


def test_enqueue_moves_paid_to_queued() -> None:
    assert enqueue(make_order(OrderStatus.PAID), NOW) == Ok(make_order(OrderStatus.QUEUED))


def test_start_moves_queued_to_running() -> None:
    assert start(make_order(OrderStatus.QUEUED), NOW) == Ok(make_order(OrderStatus.RUNNING))


def test_deliver_sets_delivered_at() -> None:
    order = make_order(OrderStatus.RUNNING)
    result = deliver(order, NOW)
    assert result == Ok(replace(order, status=OrderStatus.DELIVERED, delivered_at=NOW))


def test_fail_keeps_error_code() -> None:
    result = fail(make_order(OrderStatus.RUNNING), NOW, "timeout")
    match result:
        case Ok(order):
            assert order.status is OrderStatus.FAILED
            assert order.error_code == "timeout"
        case Err(error):
            pytest.fail(f"неожиданная ошибка: {error}")


def test_fail_before_payment_is_illegal() -> None:
    assert fail(make_order(), NOW, "cancelled") == Err(
        IllegalTransition(1, OrderStatus.CREATED, OrderStatus.FAILED)
    )


def test_reject_keeps_error_code() -> None:
    result = reject(make_order(OrderStatus.QUEUED), NOW, "moderated")
    match result:
        case Ok(order):
            assert order.status is OrderStatus.REJECTED
            assert order.error_code == "moderated"
        case Err(error):
            pytest.fail(f"неожиданная ошибка: {error}")


def test_mark_refunded_closes_failed_order() -> None:
    assert mark_refunded(make_order(OrderStatus.FAILED), NOW) == Ok(
        make_order(OrderStatus.REFUNDED)
    )


def test_mark_refunded_is_illegal_for_paid_order() -> None:
    assert mark_refunded(make_order(OrderStatus.PAID), NOW) == Err(
        IllegalTransition(1, OrderStatus.PAID, OrderStatus.REFUNDED)
    )


def test_purge_removes_delivered_order() -> None:
    assert purge(make_order(OrderStatus.DELIVERED), NOW) == Ok(make_order(OrderStatus.PURGED))


@pytest.mark.parametrize("status", list(OrderStatus))
def test_is_active_only_for_paid_queue_running(status: OrderStatus) -> None:
    assert is_active(make_order(status)) is (status in ACTIVE_STATUSES)


def test_photo_is_accepted_only_for_paid_order() -> None:
    assert is_awaiting_photo(make_order(OrderStatus.PAID)) is True
    assert is_awaiting_photo(make_order(OrderStatus.QUEUED)) is False


def test_attach_payment_records_provider_and_id() -> None:
    paid = make_order(OrderStatus.PAID)
    attached = attach_payment(paid, PaymentRef("stub", "stub-1"))
    assert attached.payment_provider == "stub"
    assert attached.payment_id == "stub-1"


def test_active_statuses_match_specification() -> None:
    expected = {OrderStatus.PAID, OrderStatus.QUEUED, OrderStatus.RUNNING}
    assert set(ACTIVE_STATUSES) == expected
