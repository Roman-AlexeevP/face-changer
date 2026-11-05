"""Middleware простого лимита частоты на пользователя."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Update

from app.bot import texts


@dataclass(frozen=True)
class ThrottlePolicy:
    """Минимальный интервал между апдейтами одного пользователя."""

    min_interval_sec: float = 1.0
    capacity: int = 5000


class ThrottleMiddleware(BaseMiddleware):
    """Отбрасывает слишком частые апдейты и вежливо просит подождать."""

    def __init__(self, policy: ThrottlePolicy | None = None) -> None:
        self._policy = policy or ThrottlePolicy()
        self._last_seen: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        user_id = extract_user_id(event)
        if user_id is None:
            return await handler(event, data)
        if self._is_throttled(user_id):
            await notify_throttled(event)
            return None
        return await handler(event, data)

    def _is_throttled(self, user_id: int) -> bool:
        now = monotonic()
        previous = self._last_seen.get(user_id)
        if previous is not None and now - previous < self._policy.min_interval_sec:
            return True
        self._remember(user_id, now)
        return False

    def _remember(self, user_id: int, now: float) -> None:
        self._last_seen[user_id] = now
        if len(self._last_seen) > self._policy.capacity:
            self._last_seen.pop(next(iter(self._last_seen)))


def extract_user_id(event: Update) -> int | None:
    """Достаёт tg_id из сообщения или callback, не логируя его."""
    if event.message is not None and event.message.from_user is not None:
        return event.message.from_user.id
    if event.callback_query is not None and event.callback_query.from_user is not None:
        return event.callback_query.from_user.id
    return None


async def notify_throttled(event: Update) -> None:
    """Сообщает о лимите тем способом, который доступен для апдейта."""
    if event.message is not None:
        await event.message.answer(texts.THROTTLE)
    elif event.callback_query is not None:
        await event.callback_query.answer(texts.THROTTLE, show_alert=False)
