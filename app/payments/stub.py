"""Платёжная заглушка: мгновенный успех без внешних вызовов."""

from dataclasses import dataclass

from app.domain.order_service import Order
from app.payments.base import Invoice, PaymentEvent, PaymentStatus


@dataclass(frozen=True)
class StubPaymentProvider:
    """MVP-провайдер: каждый счёт сразу считается оплаченным."""

    name: str = "stub"

    async def create_invoice(self, order: Order) -> Invoice:
        payment_id = build_stub_payment_id(order)
        event = PaymentEvent(
            order_id=order.id,
            payment_id=payment_id,
            amount_kopecks=order.price_kopecks,
            status=PaymentStatus.SUCCEEDED,
        )
        return Invoice(payment_id, order.price_kopecks, event)

    async def refund(self, payment_id: str) -> None:
        """Заглушка не двигает деньги: возврат фиксируется только в ledger."""


def build_stub_payment_id(order: Order) -> str:
    """Детерминированный id платежа: повторный инвойс не создаёт новый платёж."""
    return f"stub-{order.id}"
