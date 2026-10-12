"""테이블 정의. 바꾸면 Alembic 마이그레이션을 새로 만든다.

cd backend
uv run alembic revision --autogenerate -m "설명"
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Feedback(Base):
    """답변 아래 '도움이 됐어요 / 아쉬워요' 피드백. 어떤 질문에서 답이 부족했는지 모으는 용도."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    rating: Mapped[str] = mapped_column(String(8))  # up | down
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    thread_id: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), default=None)
