"""Сторож: возвращает зависшие running-задания в очередь."""

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import job_queue, models, repo
from app.domain import order_service
from app.domain.result import Err
from app.worker.retry import build_retry_key
from app.worker.services import WorkerServices

WATCHDOG_INTERVAL_SEC = 60

logger = logging.getLogger(__name__)


async def requeue_stale(services: WorkerServices) -> int:
    """Возвращает в очередь задания, висящие в running дольше порога."""
    now = services.now()
    cutoff = now - timedelta(minutes=services.settings.job_stale_minutes)
    async with services.session_factory() as session:
        stale = await job_queue.list_stale_jobs(session, cutoff)
        count = 0
        for row in stale:
            count += int(await requeue_one(session, row, now))
        await session.commit()
    return count


async def requeue_one(session: AsyncSession, row: models.Job, now: datetime) -> bool:
    """Возвращает один заказ в queued, а задание — в new с новой попыткой."""
    order = await repo.load_order(session, row.order_id, for_update=True)
    if order is None:
        return False
    requeued = order_service.requeue(order, now)
    if isinstance(requeued, Err):
        return False
    attempt = row.attempt + 1
    await repo.save_order(session, requeued.value)
    await job_queue.reschedule_job(
        session,
        row.id,
        attempt=attempt,
        idempotency_key=build_retry_key(row.order_id, attempt),
        next_attempt_at=now,
    )
    event = repo.EventRecord(
        "job_stale",
        order.user_id,
        {"job_id": row.id, "attempt": attempt},
    )
    await repo.record_event(session, event)
    return True


def cleanup_old_photos(directory: Path, now: datetime, ttl_min: int) -> int:
    """Удаляет исходные фото старше TTL; возвращает число удалённых."""
    cutoff = now.timestamp() - ttl_min * 60
    count = 0
    for path in directory.glob("photo-*.jpg"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                count += 1
        except OSError:
            continue
    return count


async def watchdog_loop(services: WorkerServices, stop: asyncio.Event) -> None:
    """Периодически возвращает зависшие задания, пока воркер не остановлен."""
    while not stop.is_set():
        await asyncio.to_thread(
            cleanup_old_photos,
            Path(services.settings.storage_dir),
            services.now(),
            services.settings.storage_url_ttl_min,
        )
        try:
            await requeue_stale(services)
        except Exception:
            logger.exception("watchdog failed")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=WATCHDOG_INTERVAL_SEC)
