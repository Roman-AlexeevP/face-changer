"""Точка сборки воркера: процесс-заглушка до появления очереди."""

import asyncio
import logging
import signal
import sys

from app.config import ConfigError, Settings, load_settings, require_engine_credentials
from app.obs.logs import configure_logging


def install_signal_handlers() -> asyncio.Event:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_stop(*_: object) -> None:
        loop.call_soon_threadsafe(stop_event.set)

    for signal_number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signal_number, request_stop)
    return stop_event


async def run_worker(settings: Settings) -> None:
    logger = logging.getLogger(__name__)
    logger.info("worker started", extra={"engine": settings.engine})
    stop_event = install_signal_handlers()
    await stop_event.wait()
    logger.info("worker stopped")


def main() -> None:
    try:
        settings = load_settings()
        require_engine_credentials(settings)
    except ConfigError as error:
        print(error, file=sys.stderr)
        raise SystemExit(2) from error
    configure_logging(settings.log_level)
    asyncio.run(run_worker(settings))


if __name__ == "__main__":
    main()
