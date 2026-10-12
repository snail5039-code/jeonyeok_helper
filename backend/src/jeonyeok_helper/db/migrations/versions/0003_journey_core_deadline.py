"""로드맵 할 일에 핵심 여부와 신청 기한

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "journey_item", sa.Column("core", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "journey_item",
        sa.Column("deadline", sa.String(length=60), nullable=False, server_default=""),
    )
    op.add_column("journey_item", sa.Column("due_months", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("journey_item", "due_months")
    op.drop_column("journey_item", "deadline")
    op.drop_column("journey_item", "core")
