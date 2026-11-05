"""/start, экран согласия и запись consent_version/consent_at."""

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards, texts
from app.bot.services import BotServices
from app.db import models, repo
from app.domain.order_service import Order

CONSENT_VERSION = "v1"


def build_router() -> Router:
    """Создаёт роутер заново: диспетчеры в тестах не делят глобальное состояние."""
    router = Router(name="start")
    router.message.register(handle_start, CommandStart())
    router.callback_query.register(handle_consent, F.data == keyboards.CONSENT_CALLBACK)
    return router


async def handle_start(message: Message, services: BotServices) -> None:
    user = message.from_user
    if user is None:
        return
    async with services.session_factory() as session:
        record = await repo.get_or_create_user(session, user.id)
        await session.commit()
        if record.consent_version is None:
            await show_consent(message)
            return
        active = await repo.get_active_order(session, record.id)
        template = await repo.get_default_template(session)
    await show_home(message, active, template)


async def handle_consent(callback: CallbackQuery, services: BotServices) -> None:
    target = callback.message
    if callback.from_user is None or not isinstance(target, Message):
        return
    async with services.session_factory() as session:
        user = await repo.get_or_create_user(session, callback.from_user.id)
        consent = repo.ConsentRecord(CONSENT_VERSION, services.now())
        await repo.record_consent(session, user, consent)
        await repo.record_event(session, consent_event(user.id))
        await session.commit()
        template = await repo.get_default_template(session)
    await callback.answer()
    await target.answer(texts.CONSENT_ACCEPTED)
    await show_home(target, None, template)


async def show_consent(message: Message) -> None:
    """Экран правил; используется и при попытке прислать фото до согласия."""
    await message.answer(texts.CONSENT_TEXT, reply_markup=keyboards.consent_keyboard())


async def show_home(
    message: Message, active: Order | None, template: models.Template | None
) -> None:
    """Выбирает экран после /start: активный заказ либо кнопка оплаты."""
    if active is not None:
        await message.answer(texts.ACTIVE_ORDER)
        return
    if template is None:
        await message.answer(texts.NO_TEMPLATE)
        return
    text = texts.checkout_text(template.title, template.price_kopecks, template.duration_sec)
    await message.answer(text, reply_markup=keyboards.checkout_keyboard(template.price_kopecks))


def consent_event(user_id: int) -> repo.EventRecord:
    return repo.EventRecord("consent_given", user_id, {"version": CONSENT_VERSION})
