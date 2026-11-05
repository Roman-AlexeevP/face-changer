"""Результат операции как значение: ошибки без исключений."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Ok[T]:
    """Успешный результат."""

    value: T


@dataclass(frozen=True)
class Err[E]:
    """Ошибка как значение."""

    error: E


type Result[T, E] = Ok[T] | Err[E]
