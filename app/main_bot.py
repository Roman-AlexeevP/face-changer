"""Точка сборки бота: роутеры, middleware, хранилище и оплата."""

import asyncio
import sys

from aiogram import Bot, Dispatcher

from app.bot.handlers import checkout, start, upload
from app.bot.middlewares.dedupe import DedupeMiddleware
from app.bot.middlewares.throttle import ThrottleMiddleware
from app.bot.services import BotServices, build_bot_services
from app.config import ConfigError, Settings, load_settings, require_bot_token
from app.db.seed import seed_default_template
from app.db.session import build_engine, build_session_factory
from app.obs.logs import configure_logging


def build_dispatcher(services: BotServices | None = None) -> Dispatcher:
    """Регистрирует хендлеры и middleware; сервисы передаются в data диспетчера."""
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(DedupeMiddleware())
    dispatcher.update.outer_middleware(ThrottleMiddleware())
    dispatcher.include_router(start.build_router())
    dispatcher.include_router(checkout.build_router())
    dispatcher.include_router(upload.build_router())
    dispatcher["services"] = services
    return dispatcher


async def run_bot(settings: Settings, token: str) -> None:
    db_engine = build_engine(settings.database_url)
    session_factory = build_session_factory(db_engine)
    bot = Bot(token=token)
    try:
        await seed_default_template(session_factory, settings)
        dispatcher = build_dispatcher(build_bot_services(settings, session_factory))
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await db_engine.dispose()


def main() -> None:
    try:
        settings = load_settings()
        token = require_bot_token(settings)
    except ConfigError as error:
        print(error, file=sys.stderr)
        raise SystemExit(2) from error
    configure_logging(settings.log_level)
    asyncio.run(run_bot(settings, token))


if __name__ == "__main__":
    main()
