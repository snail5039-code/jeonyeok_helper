"""이어 하기 코드 표

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resume_code",
        sa.Column("code", sa.String(length=16), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_resume_code_user_id", "resume_code", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_resume_code_user_id", table_name="resume_code")
    op.drop_table("resume_code")
