"""Точка сборки воркера: свой Bot, движок, хранилище и цикл очереди."""

import asyncio
import logging
import signal
import sys

from aiogram import Bot

from app.config import (
    ConfigError,
    Settings,
    load_settings,
    require_bot_token,
    require_engine_credentials,
)
from app.db.session import build_engine as build_db_engine
from app.db.session import build_session_factory
from app.engines.base import VideoEngine
from app.engines.factory import build_video_engine
from app.obs.logs import configure_logging
from app.storage.local import LocalStorage
from app.worker.loop import run_pool
from app.worker.services import WorkerServices

logger = logging.getLogger(__name__)


def install_signal_handlers() -> asyncio.Event:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_stop(*_: object) -> None:
        loop.call_soon_threadsafe(stop_event.set)

    for signal_number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signal_number, request_stop)
    return stop_event


async def run_worker(settings: Settings, token: str, engine: VideoEngine) -> None:
    stop_event = install_signal_handlers()
    bot = Bot(token=token)
    db_engine = build_db_engine(settings.database_url)
    services = WorkerServices(
        settings=settings,
        session_factory=build_session_factory(db_engine),
        bot=bot,
        engine=engine,
        storage=LocalStorage(settings.storage_dir),
    )
    logger.info("worker started", extra={"engine": settings.engine})
    try:
        await run_pool(services, stop_event)
    finally:
        await bot.session.close()
        await db_engine.dispose()
        logger.info("worker stopped")


def main() -> None:
    try:
        settings = load_settings()
        token = require_bot_token(settings)
        require_engine_credentials(settings)
        engine = build_video_engine(settings)
    except ConfigError as error:
        print(error, file=sys.stderr)
        raise SystemExit(2) from error
    configure_logging(settings.log_level)
    asyncio.run(run_worker(settings, token, engine))


if __name__ == "__main__":
    main()
