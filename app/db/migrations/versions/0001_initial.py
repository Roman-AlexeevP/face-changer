"""Создание начальной схемы.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def create_users_table() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_banned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("consent_version", sa.String(length=32), nullable=True),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_used", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("tg_id", name="uq_users_tg_id"),
    )


def create_templates_table() -> None:
    op.create_table(
        "templates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("engine_model", sa.String(length=64), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=False),
        sa.Column("resolution", sa.String(length=16), nullable=False),
        sa.Column("credits_cost", sa.Integer(), nullable=False),
        sa.Column("price_kopecks", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("engine_video_url", sa.Text(), nullable=True),
        sa.Column("engine_video_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_templates"),
        sa.UniqueConstraint("key", name="uq_templates_key"),
    )


def create_orders_table() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("price_kopecks", sa.Integer(), nullable=False),
        sa.Column("credits_cost", sa.Integer(), nullable=False),
        sa.Column("payment_provider", sa.String(length=32), nullable=True),
        sa.Column("payment_id", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_orders_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["templates.id"],
            name="fk_orders_template_id_templates",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_orders"),
        sa.UniqueConstraint("payment_id", name="uq_orders_payment_id"),
    )
    op.create_index("ix_orders_status", "orders", ["status"], unique=False)


def create_jobs_table() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("engine", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name="fk_jobs_order_id_orders",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.UniqueConstraint("idempotency_key", name="uq_jobs_idempotency_key"),
    )
    op.create_index("ix_jobs_status_submitted_at", "jobs", ["status", "submitted_at"], unique=False)
    op.create_index(
        "ix_jobs_status_next_attempt_at",
        "jobs",
        ["status", "next_attempt_at"],
        unique=False,
    )
    op.create_index("ix_jobs_request_id", "jobs", ["request_id"], unique=False)


def create_ledger_table() -> None:
    op.create_table(
        "ledger",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_ledger_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name="fk_ledger_order_id_orders",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ledger"),
    )


def create_events_table() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "props",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_events_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
    )
    op.create_index("ix_events_name_created_at", "events", ["name", "created_at"], unique=False)


def upgrade() -> None:
    create_users_table()
    create_templates_table()
    create_orders_table()
    create_jobs_table()
    create_ledger_table()
    create_events_table()


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("ledger")
    op.drop_table("jobs")
    op.drop_table("orders")
    op.drop_table("templates")
    op.drop_table("users")
