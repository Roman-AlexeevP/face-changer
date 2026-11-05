"""Тесты результата как значения."""

from dataclasses import FrozenInstanceError

import pytest

from app.domain.result import Err, Ok


def test_ok_keeps_value() -> None:
    assert Ok(42).value == 42


def test_err_keeps_error() -> None:
    assert Err("boom").error == "boom"


def test_results_are_equal_by_value() -> None:
    assert Ok("x") == Ok("x")
    assert Err("x") == Err("x")
    assert Ok("x") != Err("x")


def test_result_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        Ok(1).value = 2


def test_result_supports_pattern_matching() -> None:
    match Ok(7):
        case Ok(value):
            assert value == 7
        case _:
            pytest.fail("Ok не распознан")
