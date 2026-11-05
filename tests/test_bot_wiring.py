"""Сборка диспетчера: /start, колбэки и непустые тексты."""

from aiogram import Dispatcher, Router
from aiogram.filters import CommandStart

from app.bot import texts
from app.bot.handlers.checkout import handle_checkout
from app.bot.handlers.start import handle_consent, handle_start
from app.bot.handlers.upload import handle_photo
from app.domain.moderation import FileTooLarge
from app.main_bot import build_dispatcher


def iter_message_handlers(router: Router | Dispatcher) -> list[object]:
    handlers = list(router.message.handlers)
    for sub_router in router.sub_routers:
        handlers.extend(iter_message_handlers(sub_router))
    return handlers


def iter_callback_handlers(router: Router | Dispatcher) -> list[object]:
    handlers = list(router.callback_query.handlers)
    for sub_router in router.sub_routers:
        handlers.extend(iter_callback_handlers(sub_router))
    return handlers


def test_dispatcher_registers_start_command() -> None:
    dispatcher = build_dispatcher()
    starts = [
        handler
        for handler in iter_message_handlers(dispatcher)
        if any(isinstance(item.callback, CommandStart) for item in handler.filters)
    ]
    assert len(starts) == 1
    assert starts[0].callback is handle_start


def test_dispatcher_registers_photo_and_callbacks() -> None:
    dispatcher = build_dispatcher()
    messages = {handler.callback for handler in iter_message_handlers(dispatcher)}
    callbacks = {handler.callback for handler in iter_callback_handlers(dispatcher)}

    assert handle_photo in messages
    assert handle_consent in callbacks
    assert handle_checkout in callbacks


def test_texts_are_not_empty() -> None:
    values = [value for value in vars(texts).values() if isinstance(value, str)]
    assert values
    assert all(value.strip() for value in values)
    assert texts.checkout_text("Шаблон", 29900, 5).strip()
    assert texts.refusal_text(FileTooLarge(1, 1)).strip()
    assert texts.failure_text("unknown").strip()
