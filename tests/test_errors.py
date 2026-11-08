"""Нормализация кодов ошибок и тексты для пользователя."""

import pytest

from app.bot import texts
from app.worker.errors import normalize_error_code


@pytest.mark.parametrize(
    "code",
    ["timeout", "moderated", "no_credits", "engine_5xx", "network", "bad_input", "unknown"],
)
def test_public_codes_are_kept(code: str) -> None:
    assert normalize_error_code(code) == code


@pytest.mark.parametrize("code", ["engine_auth", "engine_bad_config", "rate_limited"])
def test_internal_codes_are_kept(code: str) -> None:
    assert normalize_error_code(code) == code


@pytest.mark.parametrize("code", ["unknown_status", "bad_response"])
def test_aliases_become_unknown(code: str) -> None:
    assert normalize_error_code(code) == "unknown"


def test_provider_code_becomes_unknown() -> None:
    assert normalize_error_code("face_not_found") == "unknown"


@pytest.mark.parametrize("code", ["timeout", "network", "engine_5xx", "bad_input"])
def test_failure_text_is_specific(code: str) -> None:
    assert texts.failure_text(code) != texts.GENERIC_FAILURE
