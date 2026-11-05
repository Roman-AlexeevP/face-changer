"""Проверка фото: размер, формат и перекодирование без детекции лиц."""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps

from app.domain.result import Err, Ok, Result

MAX_BYTES = 20 * 1024 * 1024
MAX_SIDE = 4096
JPEG_QUALITY = 90
ALLOWED_FORMATS: frozenset[str] = frozenset({"JPEG", "PNG", "WEBP"})


@dataclass(frozen=True)
class PhotoPolicy:
    """Лимиты приёма фото из требования tg-entry."""

    max_bytes: int = MAX_BYTES
    max_side: int = MAX_SIDE


@dataclass(frozen=True)
class PreparedPhoto:
    """Нормализованное фото: JPEG без EXIF и его размеры."""

    data: bytes
    width: int
    height: int
    media_type: str = "image/jpeg"


@dataclass(frozen=True)
class FileTooLarge:
    """Файл больше лимита в байтах."""

    size_bytes: int
    limit_bytes: int


@dataclass(frozen=True)
class UnsupportedFormat:
    """Формат не входит в список разрешённых."""

    format: str | None


@dataclass(frozen=True)
class ImageTooLarge:
    """Сторона изображения больше лимита в пикселях."""

    width: int
    height: int
    limit_px: int


@dataclass(frozen=True)
class CorruptedImage:
    """Данные не открываются как изображение."""


type PhotoError = FileTooLarge | UnsupportedFormat | ImageTooLarge | CorruptedImage

DEFAULT_POLICY = PhotoPolicy()


def validate_photo(
    data: bytes, policy: PhotoPolicy = DEFAULT_POLICY
) -> Result[PreparedPhoto, PhotoError]:
    """Проверяет лимиты, формат и перекодирует фото; лица не проверяются."""
    return prepare_photo(data, policy)


def prepare_photo(data: bytes, policy: PhotoPolicy) -> Result[PreparedPhoto, PhotoError]:
    """Проверяет лимиты и формат, затем перекодирует фото в JPEG без метаданных."""
    if len(data) > policy.max_bytes:
        return Err(FileTooLarge(len(data), policy.max_bytes))
    match _open_image(data):
        case Err(error):
            return Err(error)
        case Ok(image):
            return _normalize(image, policy)


def _open_image(data: bytes) -> Result[Image.Image, PhotoError]:
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except (OSError, Image.DecompressionBombError):
        return Err(CorruptedImage())
    if image.format not in ALLOWED_FORMATS:
        return Err(UnsupportedFormat(image.format))
    return Ok(image)


def _normalize(image: Image.Image, policy: PhotoPolicy) -> Result[PreparedPhoto, PhotoError]:
    if max(image.width, image.height) > policy.max_side:
        return Err(ImageTooLarge(image.width, image.height, policy.max_side))
    return Ok(_reencode(image))


def _reencode(image: Image.Image) -> PreparedPhoto:
    normalized = ImageOps.exif_transpose(image).convert("RGB")
    buffer = BytesIO()
    normalized.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return PreparedPhoto(data=buffer.getvalue(), width=normalized.width, height=normalized.height)
