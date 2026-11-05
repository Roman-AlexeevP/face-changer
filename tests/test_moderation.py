"""Тесты проверки фото: лимиты, перекодирование, EXIF и «одно лицо»."""

from dataclasses import dataclass
from io import BytesIO

import pytest
from PIL import Image

from app.domain.moderation import (
    ALLOWED_FORMATS,
    MAX_BYTES,
    MAX_SIDE,
    CorruptedImage,
    FileTooLarge,
    ImageTooLarge,
    MultipleFaces,
    NoFace,
    PhotoPolicy,
    StubFaceDetector,
    UnsupportedFormat,
    prepare_photo,
    validate_photo,
)
from app.domain.result import Err, Ok


@dataclass(frozen=True)
class FakeFaceDetector:
    """Детектор с заранее заданным ответом."""

    faces: int | None

    def count_faces(self, image: bytes) -> int | None:
        return self.faces


def encode(image: Image.Image, image_format: str = "JPEG", exif: bytes | None = None) -> bytes:
    buffer = BytesIO()
    if exif is None:
        image.save(buffer, format=image_format)
    else:
        image.save(buffer, format=image_format, exif=exif)
    return buffer.getvalue()


def photo_bytes(size: tuple[int, int] = (64, 48), image_format: str = "JPEG") -> bytes:
    return encode(Image.new("RGB", size, color=(90, 60, 30)), image_format)


def test_prepare_jpeg_returns_normalized_photo() -> None:
    result = prepare_photo(photo_bytes(), PhotoPolicy())
    match result:
        case Ok(photo):
            assert photo.media_type == "image/jpeg"
            assert (photo.width, photo.height) == (64, 48)
            assert photo.data.startswith(b"\xff\xd8")
        case Err(error):
            pytest.fail(f"неожиданная ошибка: {error}")


def test_prepare_png_converts_to_jpeg() -> None:
    result = prepare_photo(photo_bytes(image_format="PNG"), PhotoPolicy())
    assert isinstance(result, Ok)
    assert result.value.data.startswith(b"\xff\xd8")


def test_prepare_rejects_oversized_file() -> None:
    data = photo_bytes()
    result = prepare_photo(data, PhotoPolicy(max_bytes=10))
    assert result == Err(FileTooLarge(len(data), 10))


def test_prepare_rejects_too_wide_image() -> None:
    result = prepare_photo(photo_bytes(size=(64, 48)), PhotoPolicy(max_side=32))
    assert result == Err(ImageTooLarge(64, 48, 32))


def test_prepare_rejects_unsupported_format() -> None:
    assert prepare_photo(photo_bytes(image_format="GIF"), PhotoPolicy()) == Err(
        UnsupportedFormat("GIF")
    )


def test_prepare_rejects_corrupted_data() -> None:
    assert prepare_photo(b"not an image", PhotoPolicy()) == Err(CorruptedImage())


def test_prepare_strips_exif() -> None:
    exif = Image.Exif()
    exif[0x013B] = "Alice"
    data = encode(Image.new("RGB", (32, 32)), exif=exif.tobytes())
    with Image.open(BytesIO(data)) as original:
        assert original.getexif()

    result = prepare_photo(data, PhotoPolicy())
    assert isinstance(result, Ok)
    with Image.open(BytesIO(result.value.data)) as normalized:
        assert not normalized.getexif()


def test_default_policy_matches_requirements() -> None:
    policy = PhotoPolicy()
    assert policy.max_bytes == 20 * 1024 * 1024 == MAX_BYTES
    assert policy.max_side == MAX_SIDE == 4096
    assert "JPEG" in ALLOWED_FORMATS


def test_stub_face_detector_returns_unknown() -> None:
    assert StubFaceDetector().count_faces(photo_bytes()) is None


def test_unknown_face_count_is_allowed() -> None:
    """Политика MVP: пока детектора нет, «неизвестно» не блокирует фото."""
    result = validate_photo(photo_bytes(), StubFaceDetector())
    match result:
        case Ok(photo):
            assert (photo.width, photo.height) == (64, 48)
        case Err(error):
            pytest.fail(f"неожиданная ошибка: {error}")


def test_exactly_one_face_is_allowed() -> None:
    result = validate_photo(photo_bytes(), FakeFaceDetector(faces=1))
    assert isinstance(result, Ok)


def test_no_face_is_rejected() -> None:
    assert validate_photo(photo_bytes(), FakeFaceDetector(faces=0)) == Err(NoFace())


def test_multiple_faces_are_rejected() -> None:
    assert validate_photo(photo_bytes(), FakeFaceDetector(faces=2)) == Err(MultipleFaces(2))
