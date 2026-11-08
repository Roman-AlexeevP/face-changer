"""Маппинг результата движка в действие пайплайна — без БД и сети."""

from app.engines.base import EngineNoCredits, EngineResult, EngineStatus
from app.worker.outcomes import (
    FAILED_CODE,
    MODERATED_CODE,
    NO_CREDITS_CODE,
    Outcome,
    OutcomeKind,
    decide_outcome,
)

RESULT_URL = "https://cdn.example/video.mp4"


def test_done_delivers_video() -> None:
    result = EngineResult(EngineStatus.DONE, RESULT_URL)
    assert decide_outcome(result) == Outcome(OutcomeKind.DELIVER, result_url=RESULT_URL)


def test_done_without_url_fails() -> None:
    assert decide_outcome(EngineResult(EngineStatus.DONE)) == Outcome(OutcomeKind.FAIL, "done")


def test_rejected_rejects_order() -> None:
    result = EngineResult(EngineStatus.REJECTED, error_code="moderated")
    assert decide_outcome(result) == Outcome(OutcomeKind.REJECT, "moderated")


def test_rejected_without_code_uses_default() -> None:
    result = EngineResult(EngineStatus.REJECTED)
    assert decide_outcome(result) == Outcome(OutcomeKind.REJECT, MODERATED_CODE)


def test_failed_fails_with_engine_code() -> None:
    result = EngineResult(EngineStatus.FAILED, error_code="timeout")
    assert decide_outcome(result) == Outcome(OutcomeKind.FAIL, "timeout")


def test_failed_without_code_uses_status() -> None:
    result = EngineResult(EngineStatus.FAILED)
    assert decide_outcome(result) == Outcome(OutcomeKind.FAIL, EngineStatus.FAILED.value)


def test_no_credits_fails_with_own_code() -> None:
    result = EngineResult(EngineStatus.NO_CREDITS, error_code="insufficient_funds")
    assert decide_outcome(result) == Outcome(OutcomeKind.FAIL, NO_CREDITS_CODE)


def test_no_credits_exception_matches_pipeline_code() -> None:
    assert EngineNoCredits.code == NO_CREDITS_CODE
    assert FAILED_CODE != NO_CREDITS_CODE
