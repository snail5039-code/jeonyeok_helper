"""실시간 API 응답과 BM25 색인을 저장하는 캐시 표

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cache_entry",
        sa.Column("namespace", sa.String(length=40), primary_key=True),
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.LargeBinary(), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("cache_entry")
