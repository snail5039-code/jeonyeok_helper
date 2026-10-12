"""테이블 정의. 바꾸면 Alembic 마이그레이션을 새로 만든다.

cd backend
uv run alembic revision --autogenerate -m "설명"
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint
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


class JourneyItem(Base):
    """사용자의 전역 로드맵 할 일. 프로필로 한 번에 만들거나(plan), 대화하며 하나씩 쌓인다(chat).
    같은 사용자에게 같은 제목의 할 일은 하나만 둔다."""

    __tablename__ = "journey_item"
    __table_args__ = (UniqueConstraint("user_id", "title", name="uq_journey_user_title"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    stage: Mapped[str] = mapped_column(String(16))  # before, right_after, job, study, life, later
    title: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    sources: Mapped[list] = mapped_column(JSON, default=list)  # [{type, title, url}]
    origin: Mapped[str] = mapped_column(String(8), default="chat")  # plan | chat
    question: Mapped[str] = mapped_column(Text, default="")  # 대화에서 나왔으면 그 질문
    # 핵심 할 일: 단계마다 이것만 끝내면 그 단계 완료 (놓치면 손해이거나 기한이 있는 것)
    core: Mapped[bool] = mapped_column(Boolean, default=False)
    # 근거 자료에 적힌 신청 기한 문구 그대로 (예: '전역 후 3년 이내')와 전역일 기준 개월 수
    deadline: Mapped[str] = mapped_column(String(60), default="")
    due_months: Mapped[int | None] = mapped_column(Integer, default=None)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
