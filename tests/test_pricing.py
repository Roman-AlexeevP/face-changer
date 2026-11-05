"""Тесты цены: расчёт из тарифа и фиксация в заказе."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.domain.order_service import Order, OrderStatus, pay
from app.domain.pricing import (
    InvalidTariff,
    OrderDraft,
    Price,
    Tariff,
    build_order,
    order_price,
    quote,
)
from app.domain.result import Err, Ok

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def make_tariff() -> Tariff:
    return Tariff(template_id=7, price_kopecks=9900, credits_cost=2)


def make_draft() -> OrderDraft:
    return OrderDraft(order_id=42, user_id=10, created_at=NOW)


def test_quote_turns_tariff_into_price() -> None:
    assert quote(make_tariff()) == Ok(Price(price_kopecks=9900, credits_cost=2))


@pytest.mark.parametrize(
    ("field", "tariff"),
    [
        ("price_kopecks", Tariff(template_id=7, price_kopecks=0, credits_cost=2)),
        ("price_kopecks", Tariff(template_id=7, price_kopecks=-1, credits_cost=2)),
        ("credits_cost", Tariff(template_id=7, price_kopecks=9900, credits_cost=0)),
        ("credits_cost", Tariff(template_id=7, price_kopecks=9900, credits_cost=-3)),
    ],
)
def test_quote_rejects_invalid_tariff(field: str, tariff: Tariff) -> None:
    assert quote(tariff) == Err(InvalidTariff(field, getattr(tariff, field)))


def test_build_order_fixes_price_at_creation() -> None:
    assert build_order(make_tariff(), make_draft()) == Ok(
        Order(
            id=42,
            user_id=10,
            template_id=7,
            status=OrderStatus.CREATED,
            price_kopecks=9900,
            credits_cost=2,
            created_at=NOW,
        )
    )


def test_build_order_rejects_invalid_tariff() -> None:
    tariff = replace(make_tariff(), price_kopecks=0)
    assert build_order(tariff, make_draft()) == Err(InvalidTariff("price_kopecks", 0))


def test_price_does_not_change_after_tariff_update() -> None:
    tariff = make_tariff()
    order = build_order(tariff, make_draft())
    assert isinstance(order, Ok)

    new_tariff = replace(tariff, price_kopecks=19900, credits_cost=5)
    assert order_price(order.value) == Price(9900, 2)
    assert new_tariff.price_kopecks == 19900
    assert new_tariff.credits_cost == 5


def test_new_order_uses_new_tariff() -> None:
    old_order = build_order(make_tariff(), make_draft())
    new_tariff = replace(make_tariff(), price_kopecks=19900, credits_cost=5)
    new_order = build_order(new_tariff, replace(make_draft(), order_id=43))
    assert isinstance(old_order, Ok)
    assert isinstance(new_order, Ok)
    assert order_price(old_order.value) == Price(9900, 2)
    assert order_price(new_order.value) == Price(19900, 5)


def test_price_survives_payment_transition() -> None:
    order = build_order(make_tariff(), make_draft())
    assert isinstance(order, Ok)
    paid = pay(order.value, NOW)
    assert isinstance(paid, Ok)
    assert order_price(paid.value) == Price(9900, 2)
