"""Локальное хранилище: файлы в STORAGE_DIR, без публичного доступа."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

PHOTO_SUFFIX = ".jpg"


@dataclass(frozen=True)
class LocalStorage:
    """Тонкий клиент файловой системы: только сохранение и удаление."""

    directory: Path

    def photo_path(self, order_id: int) -> Path:
        return self.directory / f"photo-{order_id}{PHOTO_SUFFIX}"

    async def save_photo(self, data: bytes, order_id: int) -> Path:
        path = self.photo_path(order_id)
        await asyncio.to_thread(write_bytes, path, data)
        return path

    async def delete_photo(self, order_id: int) -> None:
        await self.delete_file(self.photo_path(order_id))

    async def delete_file(self, path: Path) -> None:
        await asyncio.to_thread(unlink_missing_ok, path)


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def unlink_missing_ok(path: Path) -> None:
    path.unlink(missing_ok=True)
