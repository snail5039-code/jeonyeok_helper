"""사용자별 전역 로드맵(할 일 목록) 저장과 조회. 표: journey_item (db/models.py)

할 일은 두 곳에서 들어온다.
- plan: '내 정보'로 한 번에 만든 로드맵 (agents/roadmap.py)
- chat: 대화 답변에서 뽑은 할 일 (agents/planner.py)
같은 사용자에게 같은 제목의 할 일은 하나만 둔다.

신청 기한은 LLM이 지어내기 쉬워서, 근거 글에 그 문구가 실제로 있을 때만 남긴다(ground_deadline).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select

from jeonyeok_helper.agents.roadmap import STAGE_TITLES
from jeonyeok_helper.db import Database, JourneyItem

STAGE_ORDER = {key: i for i, key in enumerate(STAGE_TITLES)}
DUE_MONTHS_RANGE = range(-24, 121)  # 전역 2년 전 ~ 10년 후


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def ground_deadline(
    deadline: str, due_months: int | None, texts: Iterable[str]
) -> tuple[str, int | None]:
    """기한 문구가 근거 글에 그대로 있으면 (문구, 개월 수), 없으면 ('', None).
    개월 수는 문구가 확인될 때만, 말이 되는 범위일 때만 남긴다."""
    phrase = deadline.strip()[:60]
    if not phrase or _squash(phrase) not in _squash(" ".join(texts)):
        return "", None
    return phrase, due_months if due_months in DUE_MONTHS_RANGE else None


def to_dict(item: JourneyItem) -> dict:
    return {
        "id": item.id,
        "stage": item.stage,
        "title": item.title,
        "action": item.action,
        "detail": item.detail,
        "sources": item.sources or [],
        "origin": item.origin,
        "question": item.question,
        "core": item.core,
        "deadline": item.deadline,
        "due_months": item.due_months,
        "done": item.done,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "done_at": item.done_at.isoformat() if item.done_at else None,
    }


def list_items(db: Database, user_id: str) -> list[dict]:
    with db.session() as session:
        rows = session.scalars(select(JourneyItem).where(JourneyItem.user_id == user_id)).all()
        items = [to_dict(r) for r in rows]
    return sorted(items, key=lambda i: (STAGE_ORDER.get(i["stage"], 99), i["created_at"] or ""))


def add_items(
    db: Database, user_id: str, items: list[dict], origin: str, question: str = ""
) -> list[dict]:
    """새 할 일만 넣고, 넣은 것을 돌려준다 (이미 있는 제목은 건너뜀)."""
    added = []
    with db.session() as session:
        existing = set(
            session.scalars(select(JourneyItem.title).where(JourneyItem.user_id == user_id))
        )
        for it in items:
            title = it["title"].strip()[:120]
            if not title or title in existing or it.get("stage") not in STAGE_ORDER:
                continue
            existing.add(title)
            row = JourneyItem(
                user_id=user_id,
                stage=it["stage"],
                title=title,
                action=it.get("action", ""),
                detail=it.get("detail", ""),
                sources=it.get("sources", []),
                origin=origin,
                question=question[:500],
                core=bool(it.get("core")),
                deadline=it.get("deadline", "")[:60],
                due_months=it.get("due_months"),
            )
            session.add(row)
            session.flush()
            added.append(to_dict(row))
    return added


def set_done(db: Database, user_id: str, item_id: str, done: bool) -> dict | None:
    with db.session() as session:
        row = session.get(JourneyItem, item_id)
        if row is None or row.user_id != user_id:
            return None
        row.done = done
        row.done_at = datetime.now(UTC) if done else None
        session.flush()
        return to_dict(row)


def delete_item(db: Database, user_id: str, item_id: str) -> bool:
    with db.session() as session:
        row = session.get(JourneyItem, item_id)
        if row is None or row.user_id != user_id:
            return False
        session.delete(row)
        return True


def roadmap_to_items(roadmap: dict) -> list[dict]:
    """agents.roadmap.build_roadmap 결과(단계별 묶음)를 할 일 목록으로."""
    return [
        {
            "stage": stage["key"],
            "title": it["title"],
            "action": it["action"],
            "detail": it["detail"],
            "sources": it["sources"],
            "core": it.get("core", False),
            "deadline": it.get("deadline", ""),
            "due_months": it.get("due_months"),
        }
        for stage in roadmap.get("stages", [])
        for it in stage["items"]
    ]
