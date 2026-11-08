"""Статическая проверка схемы: таблицы, колонки, уникальность, индексы."""

from sqlalchemy import UniqueConstraint

from app.db.models import Base

EXPECTED_COLUMNS = {
    "users": {
        "id",
        "tg_id",
        "created_at",
        "is_banned",
        "consent_version",
        "consent_at",
        "trial_used",
    },
    "templates": {
        "id",
        "key",
        "title",
        "source_path",
        "prompt",
        "engine_model",
        "duration_sec",
        "resolution",
        "credits_cost",
        "price_kopecks",
        "is_active",
        "engine_video_url",
        "engine_video_at",
    },
    "service_flags": {"name", "value", "expires_at"},
    "orders": {
        "id",
        "user_id",
        "template_id",
        "status",
        "price_kopecks",
        "credits_cost",
        "payment_provider",
        "payment_id",
        "error_code",
        "created_at",
        "paid_at",
        "delivered_at",
    },
    "jobs": {
        "id",
        "order_id",
        "attempt",
        "engine",
        "request_id",
        "status",
        "idempotency_key",
        "next_attempt_at",
        "submitted_at",
        "finished_at",
        "cost_usd",
        "error_code",
    },
    "ledger": {"id", "user_id", "delta", "reason", "order_id", "created_at"},
    "events": {"id", "user_id", "name", "props", "created_at"},
}

EXPECTED_INDEXES = {
    "orders": {"ix_orders_status"},
    "jobs": {
        "ix_jobs_status_submitted_at",
        "ix_jobs_status_next_attempt_at",
        "ix_jobs_request_id",
    },
    "events": {"ix_events_name_created_at"},
}


def collect_unique_columns(table_name: str) -> set[str]:
    table = Base.metadata.tables[table_name]
    return {
        column.name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
        for column in constraint.columns
    }


def collect_index_names(table_name: str) -> set[str]:
    return {index.name for index in Base.metadata.tables[table_name].indexes}


def test_schema_has_exactly_expected_tables() -> None:
    assert set(Base.metadata.tables) == set(EXPECTED_COLUMNS)


def test_columns_match_architecture() -> None:
    actual = {
        table_name: {column.name for column in table.columns}
        for table_name, table in Base.metadata.tables.items()
    }
    assert actual == EXPECTED_COLUMNS


def test_unique_columns_match_architecture() -> None:
    assert collect_unique_columns("users") == {"tg_id"}
    assert collect_unique_columns("templates") == {"key"}
    assert collect_unique_columns("orders") == {"payment_id"}
    assert collect_unique_columns("jobs") == {"idempotency_key"}


def test_indexes_match_architecture() -> None:
    for table_name, expected in EXPECTED_INDEXES.items():
        assert expected <= collect_index_names(table_name)
