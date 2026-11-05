"""Контракт платёжного провайдера: инвойс, событие оплаты и возврат."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.domain.order_service import Order


class PaymentStatus(StrEnum):
    """Итог платежа, который провайдер сообщает боту."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class PaymentEvent:
    """Событие платежа: оплата прошла или отклонена."""

    order_id: int
    payment_id: str
    amount_kopecks: int
    status: PaymentStatus = PaymentStatus.SUCCEEDED


@dataclass(frozen=True)
class Invoice:
    """Счёт на оплату; ``event`` заполнен, если провайдер отвечает сразу."""

    payment_id: str
    amount_kopecks: int
    event: PaymentEvent | None = None


class PaymentFailed(RuntimeError):
    """Провайдер не подтвердил оплату; текст пригоден для лога."""


class PaymentProvider(Protocol):
    """Порт оплаты: реализация подставляется в точке сборки."""

    name: str

    async def create_invoice(self, order: Order) -> Invoice:
        """Создаёт счёт; для мгновенных провайдеров сразу содержит событие."""
        ...

    async def refund(self, payment_id: str) -> None:
        """Возвращает деньги по платежу, если провайдер это умеет."""
        ...
