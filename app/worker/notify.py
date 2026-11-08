"""Уведомления пользователю из воркера: отказ и ошибка."""

import logging

from app.bot import texts
from app.db import job_queue, repo
from app.worker.services import WorkerServices

logger = logging.getLogger(__name__)


async def notify_rejected(services: WorkerServices, claim: job_queue.ClaimedJob) -> None:
    chat_id = await load_chat_id(services, claim)
    if chat_id is None:
        return
    try:
        await services.bot.send_message(chat_id, texts.MODERATION_REJECTED)
    except Exception:
        logger.warning("failed to notify rejection", extra={"job_id": claim.id})


async def notify_failure(services: WorkerServices, claim: job_queue.ClaimedJob, code: str) -> None:
    chat_id = await load_chat_id(services, claim)
    if chat_id is None:
        return
    try:
        await services.bot.send_message(chat_id, texts.failure_text(code))
    except Exception:
        logger.warning("failed to notify user", extra={"job_id": claim.id})


async def load_chat_id(services: WorkerServices, claim: job_queue.ClaimedJob) -> int | None:
    async with services.session_factory() as session:
        order = await repo.load_order(session, claim.order_id)
        if order is None:
            return None
        user = await repo.load_user(session, order.user_id)
        return user.tg_id if user is not None else None
