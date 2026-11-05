"""Цикл воркера: забирает job через SKIP LOCKED и держит заданную конкурентность."""

import asyncio
import logging

from app.db import repo
from app.worker.pipeline import process_job
from app.worker.services import WorkerServices

IDLE_DELAY_SEC = 1.0

logger = logging.getLogger(__name__)


async def run_pool(services: WorkerServices, stop: asyncio.Event) -> None:
    """Запускает N слотов; каждый обрабатывает по одной задаче за итерацию."""
    concurrency = max(1, services.settings.worker_concurrency)
    slots = [asyncio.create_task(run_slot(services, stop)) for _ in range(concurrency)]
    try:
        await asyncio.gather(*slots)
    finally:
        for slot in slots:
            slot.cancel()
        await asyncio.gather(*slots, return_exceptions=True)


async def run_slot(services: WorkerServices, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            claimed = await claim_next(services)
        except Exception:
            logger.exception("job claim failed")
            await asyncio.sleep(IDLE_DELAY_SEC)
            continue
        if claimed is None:
            await asyncio.sleep(IDLE_DELAY_SEC)
            continue
        try:
            await process_job(services, claimed)
        except Exception:
            logger.exception("job loop failed", extra={"job_id": claimed.id})


async def claim_next(services: WorkerServices) -> repo.ClaimedJob | None:
    async with services.session_factory() as session:
        claimed = await repo.claim_job(session, services.now())
        await session.commit()
        return claimed
