"""Структурные JSON-логи: только идентификаторы, без PII."""

import json
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TextIO

REDACTED = "[redacted]"

SENSITIVE_FIELDS = frozenset(
    {
        "tg_id",
        "telegram_id",
        "photo",
        "photo_path",
        "photo_url",
        "source_photo",
        "signed_url",
        "download_url",
    }
)

CORE_FIELDS = frozenset({"ts", "level", "logger", "message", "exception"})

RECORD_FIELDS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)))

MAX_REDACTION_DEPTH = 3


@dataclass(frozen=True)
class JsonLogFormatter:
    """Форматтер, совместимый с logging.Handler по протоколу format(record)."""

    def format(self, record: logging.LogRecord) -> str:
        return format_log_line(build_log_entry(record))


def configure_logging(level: str, stream: TextIO | None = None) -> None:
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def build_log_entry(record: logging.LogRecord) -> dict[str, object]:
    entry = collect_extra_fields(record)
    entry.update(
        {
            "ts": format_timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
    )
    if record.exc_info:
        entry["exception"] = logging.Formatter().formatException(record.exc_info)
    return entry


def format_log_line(entry: dict[str, object]) -> str:
    return json.dumps(entry, ensure_ascii=False, separators=(",", ":"), default=str)


def format_timestamp(created: float) -> str:
    return datetime.fromtimestamp(created, tz=UTC).isoformat()


def collect_extra_fields(record: logging.LogRecord) -> dict[str, object]:
    fields = {
        key: value
        for key, value in record.__dict__.items()
        if key not in RECORD_FIELDS and key not in CORE_FIELDS
    }
    return {key: redact_field(key, value) for key, value in fields.items()}


def redact_field(key: str, value: object, depth: int = 0) -> object:
    if key.lower() in SENSITIVE_FIELDS:
        return REDACTED
    if depth >= MAX_REDACTION_DEPTH:
        return REDACTED
    if isinstance(value, dict):
        return redact_mapping(value, depth)
    if isinstance(value, (list, tuple)):
        return [redact_field(key, item, depth + 1) for item in value]
    return value


def redact_mapping(value: dict, depth: int) -> dict[str, object]:
    return {
        str(item_key): redact_field(str(item_key), item, depth + 1)
        for item_key, item in value.items()
    }
