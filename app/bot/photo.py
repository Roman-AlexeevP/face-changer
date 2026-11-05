"""Загрузка фото из Telegram и сохранение во временное хранилище."""

from io import BytesIO

from aiogram import Bot
from aiogram.types import Document, Message, PhotoSize

from app.domain.moderation import MAX_BYTES, FileTooLarge, PhotoError, UnsupportedFormat
from app.domain.result import Err, Ok, Result
from app.storage.base import Storage

type Attachment = PhotoSize | Document


def pick_attachment(message: Message) -> Attachment | None:
    """Берёт самое крупное фото или документ с image-типом."""
    if message.photo:
        return message.photo[-1]
    document = message.document
    if document is not None and (document.mime_type or "").startswith("image/"):
        return document
    return None


async def download_photo(message: Message, bot: Bot) -> Result[bytes, PhotoError]:
    """Скачивает фото в память; размер проверяется до скачивания."""
    attachment = pick_attachment(message)
    if attachment is None:
        return Err(UnsupportedFormat(None))
    if attachment.file_size is not None and attachment.file_size > MAX_BYTES:
        return Err(FileTooLarge(attachment.file_size, MAX_BYTES))
    buffer = BytesIO()
    await bot.download(attachment, destination=buffer)
    return Ok(buffer.getvalue())


async def save_photo(storage: Storage, order_id: int, data: bytes) -> bool:
    """Сохраняет фото; ошибку диска возвращает как False, чтобы ответить человеку."""
    try:
        await storage.save_photo(data, order_id)
    except OSError:
        return False
    return True
