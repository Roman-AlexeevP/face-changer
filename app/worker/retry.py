"""Политика повторов задания: чистые функции без I/O."""

MAX_ATTEMPTS = 4
RETRY_DELAYS_SEC = (2, 5, 15)
RETRYABLE_CODES = frozenset({"network", "engine_5xx", "engine_failed"})


def should_retry(code: str, attempt: int) -> bool:
    """Повторяем только известные временные сбои и пока есть попытки."""
    return code in RETRYABLE_CODES and attempt < MAX_ATTEMPTS


def retry_delay_sec(attempt: int) -> int:
    """Пауза перед следующей попыткой: 2, 5, 15 секунд."""
    index = min(max(attempt - 1, 0), len(RETRY_DELAYS_SEC) - 1)
    return RETRY_DELAYS_SEC[index]


def build_retry_key(order_id: int, attempt: int) -> str:
    """Новый ключ идемпотентности для повтора."""
    return f"{order_id}:{attempt}"
