"""Системные часы: единственная точка чтения времени в оболочке."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)
