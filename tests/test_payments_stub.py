"""Тесты платёжной заглушки: мгновенное событие оплаты и пустой возврат."""

from datetime import UTC, datetime

from app.domain.order_service import Order, OrderStatus
from app.payments.base import PaymentStatus
from app.payments.stub import StubPaymentProvider, build_stub_payment_id


def make_order(order_id: int = 7) -> Order:
    return Order(
        id=order_id,
        user_id=1,
        template_id=1,
        status=OrderStatus.CREATED,
        price_kopecks=29900,
        credits_cost=1,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def test_stub_invoice_contains_success_event() -> None:
    provider = StubPaymentProvider()
    order = make_order()
    invoice = await provider.create_invoice(order)

    assert invoice.payment_id == build_stub_payment_id(order)
    assert invoice.amount_kopecks == order.price_kopecks
    assert invoice.event is not None
    assert invoice.event.order_id == order.id
    assert invoice.event.status is PaymentStatus.SUCCEEDED


async def test_stub_refund_does_not_raise() -> None:
    provider = StubPaymentProvider()
    assert await provider.refund(build_stub_payment_id(make_order())) is None
