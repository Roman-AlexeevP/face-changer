"""Проверка фото: размер, формат, перекодирование и «ровно одно лицо»."""

from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

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


@dataclass(frozen=True)
class NoFace:
    """Детектор не нашёл ни одного лица."""


@dataclass(frozen=True)
class MultipleFaces:
    """Детектор нашёл больше одного лица."""

    count: int


type PhotoError = (
    FileTooLarge | UnsupportedFormat | ImageTooLarge | CorruptedImage | NoFace | MultipleFaces
)

DEFAULT_POLICY = PhotoPolicy()


class FaceDetector(Protocol):
    """Порт детектора лиц: None означает «детектор не умеет считать»."""

    def count_faces(self, image: bytes) -> int | None:
        """Возвращает число лиц на нормализованном фото."""
        ...


@dataclass(frozen=True)
class StubFaceDetector:
    """Заглушка до подключения реального детектора: ответ всегда «неизвестно»."""

    def count_faces(self, image: bytes) -> int | None:
        return None


def validate_photo(
    data: bytes,
    detector: FaceDetector,
    policy: PhotoPolicy = DEFAULT_POLICY,
) -> Result[PreparedPhoto, PhotoError]:
    """Полная проверка: размер, формат, перекодирование, затем лицо."""
    match prepare_photo(data, policy):
        case Err(error):
            return Err(error)
        case Ok(photo):
            return ensure_single_face(photo, detector)


def prepare_photo(data: bytes, policy: PhotoPolicy) -> Result[PreparedPhoto, PhotoError]:
    """Проверяет лимиты и формат, затем перекодирует фото в JPEG без метаданных."""
    if len(data) > policy.max_bytes:
        return Err(FileTooLarge(len(data), policy.max_bytes))
    match _open_image(data):
        case Err(error):
            return Err(error)
        case Ok(image):
            return _normalize(image, policy)


def ensure_single_face(
    photo: PreparedPhoto, detector: FaceDetector
) -> Result[PreparedPhoto, PhotoError]:
    """Пропускает фото, только если лицо ровно одно.

    Политика MVP для ``None`` («неизвестно»): фото допустимо. Реальный
    детектор лиц появится отдельной задачей, а до тех пор блокировать все
    фотографии нельзя. Политика закреплена тестом
    ``test_unknown_face_count_is_allowed``.
    """
    count = detector.count_faces(photo.data)
    if count is None or count == 1:
        return Ok(photo)
    if count == 0:
        return Err(NoFace())
    return Err(MultipleFaces(count))


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
