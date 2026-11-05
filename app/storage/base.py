"""Порт временного хранилища: только файлы, без публичных ссылок."""

from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    """Хранилище фото и результатов на время обработки заказа."""

    def photo_path(self, order_id: int) -> Path:
        """Детерминированный путь фото: воркер находит его по номеру заказа."""
        ...

    async def save_photo(self, data: bytes, order_id: int) -> Path:
        """Сохраняет нормализованное фото и возвращает путь."""
        ...

    async def delete_photo(self, order_id: int) -> None:
        """Удаляет фото; отсутствие файла не считается ошибкой."""
        ...

    async def delete_file(self, path: Path) -> None:
        """Удаляет произвольный временный файл, например результат mock-движка."""
        ...
