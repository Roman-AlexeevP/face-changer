"""Middleware дедупликации update_id: повторный апдейт не обрабатывается."""

from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Update


class DedupeMiddleware(BaseMiddleware):
    """Помнит последние update_id; состояние живёт только в памяти процесса."""

    def __init__(self, capacity: int = 2000) -> None:
        self._capacity = max(1, capacity)
        self._seen: OrderedDict[int, None] = OrderedDict()

    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        if event.update_id in self._seen:
            return None
        self._seen[event.update_id] = None
        if len(self._seen) > self._capacity:
            self._seen.popitem(last=False)
        return await handler(event, data)
