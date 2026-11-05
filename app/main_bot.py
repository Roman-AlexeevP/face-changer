"""Точка сборки бота: только заглушка /start."""

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.config import ConfigError, load_settings, require_bot_token
from app.obs.logs import configure_logging

DEVELOPMENT_MESSAGE = "Сервис в разработке"


async def reply_development(message: Message) -> None:
    await message.answer(DEVELOPMENT_MESSAGE)


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.message.register(reply_development, CommandStart())
    return dispatcher


async def run_bot(token: str) -> None:
    bot = Bot(token=token)
    dispatcher = build_dispatcher()
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


def main() -> None:
    try:
        settings = load_settings()
        token = require_bot_token(settings)
    except ConfigError as error:
        print(error, file=sys.stderr)
        raise SystemExit(2) from error
    configure_logging(settings.log_level)
    asyncio.run(run_bot(token))


if __name__ == "__main__":
    main()
