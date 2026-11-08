"""Чистое решение по результату движка: доставить, отклонить или провалить."""

from dataclasses import dataclass
from enum import StrEnum

from app.engines.base import EngineResult, EngineStatus

NO_CREDITS_CODE = "no_credits"
MODERATED_CODE = "moderated"
FAILED_CODE = "engine_failed"


class OutcomeKind(StrEnum):
    """Действие пайплайна над заказом."""

    DELIVER = "deliver"
    REJECT = "reject"
    FAIL = "fail"


@dataclass(frozen=True)
class Outcome:
    """Что сделать с заказом, с каким кодом и по какой ссылке."""

    kind: OutcomeKind
    error_code: str | None = None
    result_url: str | None = None


def decide_outcome(result: EngineResult) -> Outcome:
    """Переводит терминальный статус движка в действие пайплайна."""
    if result.status is EngineStatus.DONE and result.result_url is not None:
        return Outcome(OutcomeKind.DELIVER, result_url=result.result_url)
    if result.status is EngineStatus.REJECTED:
        return Outcome(OutcomeKind.REJECT, result.error_code or MODERATED_CODE)
    if result.status is EngineStatus.NO_CREDITS:
        return Outcome(OutcomeKind.FAIL, NO_CREDITS_CODE)
    return Outcome(OutcomeKind.FAIL, result.error_code or result.status.value)
