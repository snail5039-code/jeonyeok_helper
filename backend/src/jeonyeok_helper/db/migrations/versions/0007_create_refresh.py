"""자료 자동 갱신: 수집한 자료의 개정 번호와 갱신 기록 표

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_version",
        sa.Column("kind", sa.String(length=16), primary_key=True),
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("enforced_at", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "refresh_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("changed", sa.JSON(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("docs_written", sa.Integer(), nullable=False),
        sa.Column("docs_deleted", sa.Integer(), nullable=False),
        sa.Column("retrieval", sa.JSON(), nullable=True),
        sa.Column("score_dropped", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("refresh_run")
    op.drop_table("source_version")
