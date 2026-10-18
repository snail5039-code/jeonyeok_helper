"""운영 대시보드: 질문별 시간·단계·실패 기록 표

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("total_ms", sa.Integer(), nullable=False),
        sa.Column("first_ms", sa.Integer(), nullable=True),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("failures", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
    )
    op.create_index("ix_chat_run_created_at", "chat_run", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_chat_run_created_at", table_name="chat_run")
    op.drop_table("chat_run")
