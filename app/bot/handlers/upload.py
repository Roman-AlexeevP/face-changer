"""Приём фото: валидация, сохранение, order → queued и job(new)."""

from dataclasses import dataclass

from aiogram import Bot, F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.handlers.start import show_consent
from app.bot.photo import download_photo, save_photo
from app.bot.services import BotServices
from app.db import job_queue, repo
from app.domain import moderation, order_service
from app.domain.order_service import Order
from app.domain.result import Err

JOB_ATTEMPT = 1


@dataclass(frozen=True)
class PhotoUpload:
    """Контекст одного присланного фото."""

    message: Message
    session: AsyncSession
    order: Order
    bot: Bot
    services: BotServices


async def handle_photo(message: Message, bot: Bot, services: BotServices) -> None:
    if message.from_user is None:
        return
    async with services.session_factory() as session:
        user = await repo.get_or_create_user(session, message.from_user.id)
        if user.consent_version is None:
            await show_consent(message)
            return
        active = await repo.get_active_order(session, user.id)
        if active is None:
            await message.answer(texts.NO_ACTIVE_ORDER)
            return
        if not order_service.is_awaiting_photo(active):
            await message.answer(texts.ACTIVE_ORDER)
            return
        upload = PhotoUpload(message, session, active, bot, services)
        if not await accept_photo(upload):
            return
        await session.commit()
    await message.answer(texts.PHOTO_ACCEPTED)


async def handle_other(message: Message) -> None:
    await message.answer(texts.PHOTO_REQUIRED)


def build_router() -> Router:
    """Создаёт роутер заново, чтобы тесты могли строить несколько диспетчеров."""
    router = Router(name="upload")
    router.message.register(handle_photo, F.photo | F.document)
    router.message.register(handle_other)
    return router


async def accept_photo(upload: PhotoUpload) -> bool:
    """Проверяет фото, сохраняет его и ставит заказ в очередь; отказы шлёт сам."""
    payload = await download_photo(upload.message, upload.bot)
    if isinstance(payload, Err):
        await upload.message.answer(texts.refusal_text(payload.error))
        return False
    prepared = moderation.validate_photo(payload.value)
    if isinstance(prepared, Err):
        await upload.message.answer(texts.refusal_text(prepared.error))
        return False
    if not await save_photo(upload.services.storage, upload.order.id, prepared.value.data):
        await upload.message.answer(texts.STORAGE_ERROR)
        return False
    await queue_order(upload)
    return True


async def queue_order(upload: PhotoUpload) -> None:
    enqueued = order_service.enqueue(upload.order, upload.services.now())
    if isinstance(enqueued, Err):
        raise LookupError(f"Заказ {upload.order.id} не готов к очереди")
    await repo.save_order(upload.session, enqueued.value)
    request = job_queue.JobRequest(
        upload.order.id,
        upload.services.settings.engine,
        f"{upload.order.id}:{JOB_ATTEMPT}",
    )
    await job_queue.create_job(upload.session, request)
    event = repo.EventRecord("photo_accepted", upload.order.user_id, {"order_id": upload.order.id})
    await repo.record_event(upload.session, event)
