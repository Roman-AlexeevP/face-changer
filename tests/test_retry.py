"""Политика повторов задания: чистые функции без БД и сети."""

import pytest

from app.worker.retry import (
    MAX_ATTEMPTS,
    build_retry_key,
    retry_delay_sec,
    should_retry,
)


@pytest.mark.parametrize("code", ["network", "engine_5xx", "engine_failed"])
def test_retryable_codes_are_retried_before_limit(code: str) -> None:
    assert should_retry(code, 1) is True
    assert should_retry(code, MAX_ATTEMPTS - 1) is True


@pytest.mark.parametrize("code", ["no_credits", "moderated", "bad_input", "timeout", "unknown"])
def test_non_retryable_codes_are_not_retried(code: str) -> None:
    assert should_retry(code, 1) is False


def test_attempt_limit_stops_retries() -> None:
    assert should_retry("network", MAX_ATTEMPTS) is False
    assert should_retry("network", MAX_ATTEMPTS + 1) is False


def test_backoff_is_two_five_fifteen() -> None:
    assert [retry_delay_sec(attempt) for attempt in (1, 2, 3)] == [2, 5, 15]


def test_retry_key_changes_with_attempt() -> None:
    assert build_retry_key(42, 1) == "42:1"
    assert build_retry_key(42, 2) == "42:2"
