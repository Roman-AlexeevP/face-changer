"""Сервисные флаги: пауза продаж при исчерпании кредитов движка.

Revision ID: 0002_service_flags
Revises: 0001_initial
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_service_flags"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_flags",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("name", name="pk_service_flags"),
    )


def downgrade() -> None:
    op.drop_table("service_flags")
