"""Оплата заглушкой: заказ, кредиты в ledger, списание и запрос фото."""

from dataclasses import dataclass
from datetime import datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, texts
from app.bot.services import BotServices
from app.db import models, repo
from app.domain import ledger, order_service, sales
from app.domain.order_service import Order
from app.domain.result import Err, Ok
from app.payments.base import Invoice, PaymentFailed, PaymentStatus


def build_router() -> Router:
    """Создаёт роутер заново, чтобы тесты могли строить несколько диспетчеров."""
    router = Router(name="checkout")
    router.callback_query.register(handle_checkout, F.data == keyboards.CHECKOUT_CALLBACK)
    return router


@dataclass(frozen=True)
class Checkout:
    """Всё, что нужно для создания и оплаты заказа в одном запросе."""

    session: AsyncSession
    user: models.User
    template: models.Template
    target: Message
    services: BotServices


async def handle_checkout(callback: CallbackQuery, services: BotServices) -> None:
    target = callback.message
    if callback.from_user is None or not isinstance(target, Message):
        return
    await callback.answer()
    if not services.settings.sales_enabled:
        await target.answer(texts.TECH_WORKS)
        return
    async with services.session_factory() as session:
        if await is_sales_blocked(session, services.now()):
            await target.answer(texts.TECH_WORKS)
            return
        await start_checkout(session, callback.from_user.id, target, services=services)


async def is_sales_blocked(session: AsyncSession, now: datetime) -> bool:
    """Читает флаг паузы продаж; решение принимает домен."""
    flag = await repo.read_flag(session, sales.SALES_BLOCK_FLAG)
    return not sales.is_sales_open(flag, now)


async def start_checkout(
    session: AsyncSession, tg_id: int, target: Message, *, services: BotServices
) -> None:
    user = await repo.get_or_create_user(session, tg_id)
    if user.consent_version is None:
        await target.answer(texts.CONSENT_REQUIRED, reply_markup=keyboards.consent_keyboard())
        return
    if await repo.get_active_order(session, user.id) is not None:
        await target.answer(texts.ACTIVE_ORDER)
        return
    template = await repo.get_default_template(session)
    if template is None:
        await target.answer(texts.NO_TEMPLATE)
        return
    checkout = Checkout(session, user, template, target, services)
    await open_order(checkout)


async def open_order(checkout: Checkout) -> None:
    order = await repo.create_order(
        checkout.session,
        repo.NewOrder(checkout.user.id, checkout.template),
    )
    await repo.record_event(checkout.session, order_event("order_created", order))
    try:
        await charge_order(checkout, order)
    except PaymentFailed:
        await checkout.session.rollback()
        await checkout.target.answer(texts.PAYMENT_FAILED)
        return
    await checkout.session.commit()
    await checkout.target.answer(texts.PHOTO_REQUEST)


async def charge_order(checkout: Checkout, order: Order) -> None:
    invoice = await checkout.services.payments.create_invoice(order)
    ensure_paid(invoice)
    result = order_service.pay(order, checkout.services.now())
    if isinstance(result, Err):
        raise PaymentFailed(f"Заказ {order.id} нельзя оплатить")
    payment = order_service.PaymentRef(checkout.services.payments.name, invoice.payment_id)
    paid = order_service.attach_payment(result.value, payment)
    await repo.save_order(checkout.session, paid)
    await write_ledger(checkout.session, paid)
    await repo.record_event(checkout.session, order_event("order_paid", paid))


async def write_ledger(session: AsyncSession, order: Order) -> None:
    topup = ledger.top_up(order)
    charge = ledger.debit(order, [])
    if not isinstance(topup, Ok) or not isinstance(charge, Ok):
        raise PaymentFailed("Не удалось построить записи ledger")
    await repo.add_ledger_entry(session, topup.value)
    await repo.add_ledger_entry(session, charge.value)


def ensure_paid(invoice: Invoice) -> None:
    event = invoice.event
    if event is None or event.status is not PaymentStatus.SUCCEEDED:
        raise PaymentFailed(f"Платёж {invoice.payment_id} не подтверждён")


def order_event(name: str, order: Order) -> repo.EventRecord:
    return repo.EventRecord(name, order.user_id, {"order_id": order.id})
