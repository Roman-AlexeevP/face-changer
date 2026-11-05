"""Тесты JSON-логов и редакции PII."""

import io
import json
import logging

from app.obs.logs import JsonLogFormatter, configure_logging

REDACTED = "[redacted]"


def build_record(**fields: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    for name, value in fields.items():
        setattr(record, name, value)
    return record


def format_record(record: logging.LogRecord) -> dict[str, object]:
    return json.loads(JsonLogFormatter().format(record))


def test_log_line_is_json_with_message() -> None:
    payload = format_record(build_record(order_id=7))

    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test"
    assert payload["order_id"] == 7
    assert "ts" in payload


def test_sensitive_fields_are_redacted() -> None:
    payload = format_record(
        build_record(tg_id=123, photo_path="/tmp/photo.jpg", photo_url="https://cdn/x?sig=1")
    )

    assert payload["tg_id"] == REDACTED
    assert payload["photo_path"] == REDACTED
    assert payload["photo_url"] == REDACTED


def test_nested_sensitive_fields_are_redacted() -> None:
    payload = format_record(build_record(context={"tg_id": 123, "order_id": 7}))

    context = payload["context"]
    assert isinstance(context, dict)
    assert context["tg_id"] == REDACTED
    assert context["order_id"] == 7


def test_configure_logging_writes_json_to_stream() -> None:
    stream = io.StringIO()
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    try:
        configure_logging("INFO", stream)
        logging.getLogger("worker").info("worker started", extra={"engine": "mock"})
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)

    payload = json.loads(stream.getvalue().strip())
    assert payload["message"] == "worker started"
    assert payload["engine"] == "mock"
