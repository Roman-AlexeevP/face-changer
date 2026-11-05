"""Расчёт цены заказа из шаблона и фиксация её в заказе."""

from dataclasses import dataclass
from datetime import datetime

from app.domain.order_service import Order, OrderStatus
from app.domain.result import Err, Ok, Result


@dataclass(frozen=True)
class Tariff:
    """Снимок цен шаблона на момент создания заказа."""

    template_id: int
    price_kopecks: int
    credits_cost: int


@dataclass(frozen=True)
class OrderDraft:
    """Внешние данные заказа: идентификатор, владелец и время создания."""

    order_id: int
    user_id: int
    created_at: datetime


@dataclass(frozen=True)
class Price:
    """Цена генерации: рубли в копейках и кредиты пользователя."""

    price_kopecks: int
    credits_cost: int


@dataclass(frozen=True)
class InvalidTariff:
    """Тариф нарушает инвариант положительной цены."""

    field: str
    value: int


type PricingError = InvalidTariff


def quote(tariff: Tariff) -> Result[Price, PricingError]:
    """Проверяет тариф и превращает его в цену заказа."""
    if tariff.price_kopecks <= 0:
        return Err(InvalidTariff("price_kopecks", tariff.price_kopecks))
    if tariff.credits_cost <= 0:
        return Err(InvalidTariff("credits_cost", tariff.credits_cost))
    return Ok(Price(tariff.price_kopecks, tariff.credits_cost))


def build_order(tariff: Tariff, draft: OrderDraft) -> Result[Order, PricingError]:
    """Создаёт заказ, копируя цену и кредиты из тарифа в неизменяемое поле."""
    match quote(tariff):
        case Err(error):
            return Err(error)
        case Ok(price):
            return Ok(
                Order(
                    id=draft.order_id,
                    user_id=draft.user_id,
                    template_id=tariff.template_id,
                    status=OrderStatus.CREATED,
                    price_kopecks=price.price_kopecks,
                    credits_cost=price.credits_cost,
                    created_at=draft.created_at,
                )
            )


def order_price(order: Order) -> Price:
    """Возвращает цену из самого заказа, а не из текущего тарифа шаблона."""
    return Price(order.price_kopecks, order.credits_cost)
