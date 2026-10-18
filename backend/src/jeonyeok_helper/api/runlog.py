"""운영 대시보드: 질문마다 걸린 시간·단계·실패를 남기고(chat_run 표), 최근 며칠을 모아 본다.

- 첫 글자: 답변 초안의 첫 조각(또는 길잡이 말·저장한 답)이 화면에 나간 시각
- 단계: 그래프 노드가 끝난 시각. 앞 단계가 끝난 뒤 이 단계가 끝나기까지를 그 단계의 시간으로 본다
  (규정·혜택 워커처럼 동시에 도는 단계는 겹쳐서 실제보다 짧게 보일 수 있다)
- 실패: 워커 시간 초과·실패, 도구가 돌려준 오류(API 장애 등)
질문은 개인정보 형식을 가린 뒤 앞 300자만 둔다. 누가 물었는지(익명 ID)는 남기지 않는다.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from jeonyeok_helper.agents.guardrails import mask_pii
from jeonyeok_helper.db import ChatRun, Database, Feedback

KEEP_DAYS = 90
TOOL_LINE = re.compile(r"^\[(\w+)\] (.*)$")


def failures_from(findings: list[dict] | None) -> list[dict]:
    """워커 결과에서 실패만: 시간 초과·예외는 워커 요약에, 도구 오류는 원문의 error 칸에."""
    out = []
    for f in findings or []:
        worker, summary = f.get("worker", ""), str(f.get("summary", ""))
        if summary.startswith("(조회"):
            out.append({"where": worker, "error": summary.strip("()")[:200]})
            continue
        for line in summary.splitlines():
            m = TOOL_LINE.match(line)
            if not m:
                continue
            try:
                error = json.loads(m[2]).get("error")
            except (ValueError, AttributeError):  # 원문이 잘려 JSON이 아니면 글자로 찾는다
                found = re.search(r'"error":\s*"([^"]{1,200})', m[2])
                error = found[1] if found else None
            if error:
                out.append({"where": f"{worker}/{m[1]}", "error": str(error)[:200]})
    return out


class RunTimer:
    def __init__(self, question: str):
        self.started = time.perf_counter()
        self.question = mask_pii(question)[0][:300]
        self.kind = "research"
        self.first_ms: int | None = None
        self.steps: list[dict] = []
        self.failures: list[dict] = []
        self.error = ""

    def ms(self) -> int:
        return round((time.perf_counter() - self.started) * 1000)

    def step(self, node: str) -> None:
        self.steps.append({"node": node, "ms": self.ms()})

    def first(self) -> None:
        if self.first_ms is None:
            self.first_ms = self.ms()

    def save(self, db: Database) -> None:
        with db.session() as session:
            session.add(
                ChatRun(
                    kind=self.kind,
                    question=self.question,
                    total_ms=self.ms(),
                    first_ms=self.first_ms,
                    steps=self.steps,
                    failures=self.failures,
                    error=self.error[:500],
                )
            )
            # 오래된 기록은 지운다 (대시보드는 최근 며칠만 본다)
            cutoff = datetime.now(UTC) - timedelta(days=KEEP_DAYS)
            session.execute(delete(ChatRun).where(ChatRun.created_at < cutoff))


def _pct(values: list[int], p: float) -> int | None:
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, round(p * (len(values) - 1)))]


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # SQLite는 시간대 없이 돌려준다


def summary(db: Database, days: int = 7, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    since = now - timedelta(days=days)
    with db.session() as session:
        runs = list(session.scalars(select(ChatRun).where(ChatRun.created_at >= since)))
        feedback = list(session.scalars(select(Feedback).where(Feedback.created_at >= since)))

    searched = [r for r in runs if r.kind == "research"]
    # 단계별 시간: 앞 단계가 끝난 뒤부터 이 단계가 끝날 때까지
    gaps: dict[str, list[int]] = defaultdict(list)
    for r in searched:
        prev = 0
        for s in sorted(r.steps or [], key=lambda s: s["ms"]):
            gaps[s["node"]].append(s["ms"] - prev)
            prev = s["ms"]
    slow_steps = sorted(
        (
            {"node": node, "count": len(v), "p50_ms": _pct(v, 0.5), "p90_ms": _pct(v, 0.9)}
            for node, v in gaps.items()
        ),
        key=lambda s: s["p50_ms"] or 0,
        reverse=True,
    )

    failures = [
        {"at": _aware(r.created_at).isoformat(), "question": r.question} | f
        for r in sorted(runs, key=lambda r: r.created_at, reverse=True)
        for f in (r.failures or [])
    ]
    errors = [
        {"at": _aware(r.created_at).isoformat(), "question": r.question, "error": r.error}
        for r in runs
        if r.kind == "error"
    ]

    down = [f for f in feedback if f.rating == "down"]
    by_question = Counter(f.question.strip()[:120] for f in down)
    daily = Counter(_aware(r.created_at).date().isoformat() for r in runs)

    return {
        "days": days,
        "chats": {"total": len(runs), "by_kind": dict(Counter(r.kind for r in runs))},
        "daily": [
            {
                "day": (now - timedelta(days=i)).date().isoformat(),
                "count": daily.get((now - timedelta(days=i)).date().isoformat(), 0),
            }
            for i in range(days - 1, -1, -1)
        ],  # fmt: skip
        "latency": {
            "first_p50_ms": _pct([r.first_ms for r in searched if r.first_ms], 0.5),
            "first_p90_ms": _pct([r.first_ms for r in searched if r.first_ms], 0.9),
            "total_p50_ms": _pct([r.total_ms for r in searched], 0.5),
            "total_p90_ms": _pct([r.total_ms for r in searched], 0.9),
            "cases": len(searched),
        },
        "slow_steps": slow_steps,
        "failures": {
            "count": len(failures),
            "by_where": dict(Counter(f["where"] for f in failures).most_common()),
            "recent": failures[:20],
        },
        "errors": errors[:20],
        "feedback": {
            "up": len(feedback) - len(down),
            "down": len(down),
            "top_down_questions": [
                {"question": q, "count": n} for q, n in by_question.most_common(10)
            ],
            "recent_down": [
                {
                    "at": _aware(f.created_at).isoformat(),
                    "question": f.question[:300],
                    "answer": f.answer[:300],
                    "comment": f.comment or "",
                }
                for f in sorted(down, key=lambda f: f.created_at, reverse=True)[:20]
            ],
        },
    }
