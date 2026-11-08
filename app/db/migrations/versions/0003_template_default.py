"""Шаблон по умолчанию: флаг is_default.

Revision ID: 0003_template_default
Revises: 0002_service_flags
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_template_default"
down_revision: str | None = "0002_service_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "templates",
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.execute("UPDATE templates SET is_default = true WHERE key = 'default'")


def downgrade() -> None:
    op.drop_column("templates", "is_default")
