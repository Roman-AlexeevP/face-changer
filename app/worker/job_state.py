"""Сохранение request_id и возврат задания в очередь после сбоя."""

from datetime import timedelta

from app.db import job_queue, repo
from app.domain import order_service
from app.domain.result import Err
from app.worker.retry import build_retry_key, retry_delay_sec
from app.worker.services import WorkerServices


async def save_request_id(services: WorkerServices, job_id: int, request_id: str) -> None:
    """Пишет request_id сразу после submit, чтобы пережить рестарт."""
    async with services.session_factory() as session:
        await job_queue.mark_submitted(session, job_id, request_id)
        await session.commit()


async def retry_job(services: WorkerServices, claim: job_queue.ClaimedJob, code: str) -> bool:
    """Возвращает заказ в queued, а задание — в new с новой попыткой."""
    now = services.now()
    attempt = claim.attempt + 1
    next_attempt = now + timedelta(seconds=retry_delay_sec(claim.attempt))
    async with services.session_factory() as session:
        order = await repo.load_order(session, claim.order_id, for_update=True)
        if order is None:
            return False
        requeued = order_service.requeue(order, now)
        if isinstance(requeued, Err):
            return False
        await repo.save_order(session, requeued.value)
        await job_queue.reschedule_job(
            session,
            claim.id,
            attempt=attempt,
            idempotency_key=build_retry_key(claim.order_id, attempt),
            next_attempt_at=next_attempt,
        )
        event = repo.EventRecord(
            "job_retry",
            order.user_id,
            {"job_id": claim.id, "error_code": code, "attempt": attempt},
        )
        await repo.record_event(session, event)
        await session.commit()
    return True
