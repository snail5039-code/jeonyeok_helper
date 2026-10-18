"""테이블 정의. 바꾸면 Alembic 마이그레이션을 새로 만든다.

cd backend
uv run alembic revision --autogenerate -m "설명"
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
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


class CacheEntry(Base):
    """서버를 다시 켜도 남는 캐시: 실시간 API 응답(정부24·온통청년 등)과 BM25 키워드 색인.
    value는 pickle로 저장한다. 메모리 캐시가 비었을 때 여기서 먼저 찾는다 (db/cache.py)."""

    __tablename__ = "cache_entry"

    namespace: Mapped[str] = mapped_column(String(40), primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)  # 원래 키의 md5
    value: Mapped[bytes] = mapped_column(LargeBinary)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResumeCode(Base):
    """이어 하기 코드: 로그인 없이 다른 기기에서 같은 기록(익명 ID)을 열기 위한 짧은 코드.
    사용자당 하나이고, 새로 만들면 이전 코드는 지워진다."""

    __tablename__ = "resume_code"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)  # 예: JY7K3Q9XPA (하이픈 없이)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class PushSubscription(Base):
    """브라우저 알림(Web Push) 구독. 익명 ID 하나에 기기(브라우저)마다 하나씩 생긴다.
    푸시 서비스가 '없는 구독'(404·410)이라고 하면 지운다."""

    __tablename__ = "push_subscription"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    endpoint: Mapped[str] = mapped_column(String(1024), unique=True)
    p256dh: Mapped[str] = mapped_column(String(256))
    auth: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class PushSent(Base):
    """기한 알림을 보낸 기록. 같은 할 일에 같은 알림(30·7·1일 전)을 두 번 보내지 않는다."""

    __tablename__ = "push_sent"

    item_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    days_before: Mapped[int] = mapped_column(Integer, primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class SourceVersion(Base):
    """자료 자동 갱신: 마지막으로 수집한 법령·행정규칙·조례의 개정 번호(일련번호).
    국가법령정보센터는 개정될 때마다 일련번호가 바뀌어서, 번호가 다를 때만 다시 수집한다."""

    __tablename__ = "source_version"

    kind: Mapped[str] = mapped_column(String(16), primary_key=True)  # law, admrul, ordin
    key: Mapped[str] = mapped_column(String(64), primary_key=True)  # 법령ID 등 바뀌지 않는 ID
    version: Mapped[str] = mapped_column(String(64))  # 일련번호
    name: Mapped[str] = mapped_column(String(200), default="")
    enforced_at: Mapped[str] = mapped_column(String(16), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class RefreshRun(Base):
    """자료 자동 갱신 한 번의 기록: 바뀐 자료, 실패, 갱신 뒤 검색 골든셋 점수."""

    __tablename__ = "refresh_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    changed: Mapped[list] = mapped_column(
        JSON, default=list
    )  # ["법령 제대군인지원에 관한 법률", ...]
    errors: Mapped[list] = mapped_column(JSON, default=list)
    docs_written: Mapped[int] = mapped_column(Integer, default=0)
    docs_deleted: Mapped[int] = mapped_column(Integer, default=0)
    # 검색 골든셋 결과 {"hit", "recall", "mrr", "cases", "errors"} (바뀐 게 없으면 None)
    retrieval: Mapped[dict | None] = mapped_column(JSON, default=None)
    score_dropped: Mapped[bool] = mapped_column(Boolean, default=False)
