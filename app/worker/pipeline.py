"""Обработка одного задания: генерация, доставка и компенсация при ошибке."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, texts
from app.db import job_queue, models, repo
from app.domain import ledger, order_service, sales
from app.domain.order_service import Order
from app.domain.result import Err, Ok
from app.engines.base import EngineError, EngineNoCredits, EngineResult, JobSpec
from app.storage.base import Storage
from app.worker.job_state import retry_job, save_request_id
from app.worker.notify import load_chat_id, notify_failure, notify_rejected
from app.worker.outcomes import (
    FAILED_CODE,
    MODERATED_CODE,
    NO_CREDITS_CODE,
    Outcome,
    OutcomeKind,
    decide_outcome,
)
from app.worker.retry import should_retry
from app.worker.services import WorkerServices

logger = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    """Пайплайн не смог продолжить; ``code`` уходит в текст пользователю."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Failure:
    """Причина и время провала заказа."""

    code: str
    at: datetime


async def process_job(services: WorkerServices, claim: job_queue.ClaimedJob) -> None:
    """Ведёт заказ от взятого job до терминального статуса."""
    try:
        template = await start_order(services, claim)
        result = await generate_video(services, claim, template)
        await apply_outcome(services, claim, decide_outcome(result))
    except EngineNoCredits:
        await no_credits_job(services, claim)
    except (EngineError, PipelineError) as error:
        if should_retry(error.code, claim.attempt) and await retry_job(services, claim, error.code):
            return
        await fail_job(services, claim, error.code)
    except Exception:
        logger.exception("job failed unexpectedly", extra={"job_id": claim.id})
        await fail_job(services, claim, "internal")


async def apply_outcome(
    services: WorkerServices, claim: job_queue.ClaimedJob, outcome: Outcome
) -> None:
    """Выполняет действие, выбранное чистой функцией решения."""
    if outcome.kind is OutcomeKind.DELIVER:
        await deliver(services, claim, outcome.result_url)
    elif outcome.kind is OutcomeKind.REJECT:
        await reject_job(services, claim, outcome.error_code or MODERATED_CODE)
    elif outcome.error_code == NO_CREDITS_CODE:
        await no_credits_job(services, claim)
    else:
        code = outcome.error_code or FAILED_CODE
        if should_retry(code, claim.attempt) and await retry_job(services, claim, code):
            return
        await fail_job(services, claim, code)


async def start_order(services: WorkerServices, claim: job_queue.ClaimedJob) -> models.Template:
    """Переводит заказ в running и достаёт шаблон для задания."""
    async with services.session_factory() as session:
        order = await repo.load_order(session, claim.order_id, for_update=True)
        if order is None:
            raise PipelineError("order_missing")
        started = order_service.start(order, services.now())
        if isinstance(started, Err):
            raise PipelineError("order_not_runnable")
        await repo.save_order(session, started.value)
        template = await repo.load_template(session, started.value.template_id)
        await session.commit()
    if template is None:
        raise PipelineError("template_missing")
    return template


def build_spec(claim: job_queue.ClaimedJob, template: models.Template, storage: Storage) -> JobSpec:
    """Собирает задание для движка из заказа, шаблона и пути фото."""
    return JobSpec(
        template_key=template.key,
        video_url=template.source_path,
        photo_url=str(storage.photo_path(claim.order_id)),
        prompt=template.prompt,
        duration_sec=template.duration_sec,
        resolution=template.resolution,
        idempotency_key=claim.idempotency_key,
        request_id=claim.request_id,
    )


async def generate_video(
    services: WorkerServices, claim: job_queue.ClaimedJob, template: models.Template
) -> EngineResult:
    spec = build_spec(claim, template, services.storage)
    hook = partial(save_request_id, services, claim.id)
    return await services.engine.generate(spec, on_submit=hook)


async def deliver(services: WorkerServices, claim: job_queue.ClaimedJob, path: str | None) -> None:
    if path is None:
        raise PipelineError(FAILED_CODE)
    chat_id = await load_chat_id(services, claim)
    if chat_id is None:
        raise PipelineError("user_missing")
    try:
        await send_video(services.bot, chat_id, path)
    except Exception:
        await delete_result(services, path)
        raise
    await mark_delivered(services, claim)
    await cleanup(services, claim, path)


async def delete_result(services: WorkerServices, path: str) -> None:
    """Удаляет локальный результат; URL движка удалять не нужно."""
    if await asyncio.to_thread(is_local_file, path):
        await services.storage.delete_file(Path(path))


async def send_video(bot: Bot, chat_id: int, path: str) -> None:
    video = FSInputFile(path) if await asyncio.to_thread(is_local_file, path) else path
    await bot.send_video(
        chat_id,
        video,
        caption=texts.VIDEO_CAPTION,
        reply_markup=keyboards.again_keyboard(),
    )


def is_local_file(path: str) -> bool:
    return Path(path).exists()


async def mark_delivered(services: WorkerServices, claim: job_queue.ClaimedJob) -> None:
    now = services.now()
    async with services.session_factory() as session:
        order = await repo.load_order(session, claim.order_id, for_update=True)
        if order is None:
            raise PipelineError("order_missing")
        delivered = order_service.deliver(order, now)
        if isinstance(delivered, Err):
            raise PipelineError("order_not_deliverable")
        await repo.save_order(session, delivered.value)
        outcome = job_queue.JobOutcome(claim.id, job_queue.JobStatus.DONE, now)
        await job_queue.finish_job(session, outcome)
        event = repo.EventRecord(
            "order_delivered", delivered.value.user_id, {"order_id": claim.order_id}
        )
        await repo.record_event(session, event)
        await session.commit()


async def cleanup(
    services: WorkerServices, claim: job_queue.ClaimedJob, result_path: str | None
) -> None:
    try:
        await services.storage.delete_photo(claim.order_id)
        if result_path is not None:
            await delete_result(services, result_path)
    except OSError:
        logger.warning("cleanup failed", extra={"job_id": claim.id})


async def fail_job(services: WorkerServices, claim: job_queue.ClaimedJob, code: str) -> None:
    await mark_failed(services, claim, code)
    await cleanup(services, claim, None)
    await notify_failure(services, claim, code)


async def mark_failed(services: WorkerServices, claim: job_queue.ClaimedJob, code: str) -> None:
    now = services.now()
    async with services.session_factory() as session:
        order = await repo.load_order(session, claim.order_id, for_update=True)
        if order is not None:
            await fail_order(session, order, Failure(code, now))
        outcome = job_queue.JobOutcome(claim.id, job_queue.JobStatus.FAILED, now, code)
        await job_queue.finish_job(session, outcome)
        event = repo.EventRecord("job_failed", None, {"job_id": claim.id, "error_code": code})
        await repo.record_event(session, event)
        await session.commit()


async def fail_order(session: AsyncSession, order: Order, failure: Failure) -> None:
    failed = order_service.fail(order, failure.at, failure.code)
    if isinstance(failed, Err):
        return
    await repo.save_order(session, failed.value)
    await refund_credit(session, failed.value, failure.at)


async def refund_credit(session: AsyncSession, order: Order, now: datetime) -> None:
    entries = await repo.load_order_ledger(session, order.id)
    refund = ledger.refund(order, entries)
    if not isinstance(refund, Ok):
        return
    await repo.add_ledger_entry(session, refund.value)
    event = repo.EventRecord("refund_issued", order.user_id, {"order_id": order.id})
    await repo.record_event(session, event)
    refunded = order_service.mark_refunded(order, now)
    if isinstance(refunded, Ok):
        await repo.save_order(session, refunded.value)


async def reject_job(services: WorkerServices, claim: job_queue.ClaimedJob, code: str) -> None:
    await mark_rejected(services, claim, code)
    await cleanup(services, claim, None)
    await notify_rejected(services, claim)


async def mark_rejected(services: WorkerServices, claim: job_queue.ClaimedJob, code: str) -> None:
    now = services.now()
    async with services.session_factory() as session:
        order = await repo.load_order(session, claim.order_id, for_update=True)
        if order is not None:
            await reject_order(session, order, Failure(code, now))
        outcome = job_queue.JobOutcome(claim.id, job_queue.JobStatus.FAILED, now, code)
        await job_queue.finish_job(session, outcome)
        user_id = order.user_id if order is not None else None
        event = repo.EventRecord("order_rejected", user_id, {"order_id": claim.order_id})
        await repo.record_event(session, event)
        await session.commit()


async def reject_order(session: AsyncSession, order: Order, failure: Failure) -> None:
    rejected = order_service.reject(order, failure.at, failure.code)
    if isinstance(rejected, Err):
        return
    await repo.save_order(session, rejected.value)
    await refund_credit(session, rejected.value, failure.at)


async def no_credits_job(services: WorkerServices, claim: job_queue.ClaimedJob) -> None:
    await mark_no_credits(services, claim)
    await cleanup(services, claim, None)
    await notify_failure(services, claim, NO_CREDITS_CODE)


async def mark_no_credits(services: WorkerServices, claim: job_queue.ClaimedJob) -> None:
    now = services.now()
    async with services.session_factory() as session:
        order = await repo.load_order(session, claim.order_id, for_update=True)
        if order is not None:
            await fail_order(session, order, Failure(NO_CREDITS_CODE, now))
        outcome = job_queue.JobOutcome(claim.id, job_queue.JobStatus.FAILED, now, NO_CREDITS_CODE)
        await job_queue.finish_job(session, outcome)
        await repo.write_flag(session, sales.build_sales_block(now))
        user_id = order.user_id if order is not None else None
        event = repo.EventRecord("engine_no_credits", user_id, {"job_id": claim.id})
        await repo.record_event(session, event)
        await session.commit()
