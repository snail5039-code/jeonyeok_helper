"""운영 대시보드: 질문별 기록(시간·단계·실패)과 요약, 관리자 열쇠."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from test_api import make_client, temp_db

from jeonyeok_helper.agents.state import Profile, Route
from jeonyeok_helper.api import runlog
from jeonyeok_helper.config import get_settings
from jeonyeok_helper.db import ChatRun, Database, Feedback


def test_failures_from_worker_findings():
    findings = [
        {"worker": "benefit", "summary": "(조회 시간 초과)"},
        {
            "worker": "regulation",
            "summary": '[search_regulations] {"results": []}\n'
            '[search_benefits] {"benefits": [], "error": "정부24 응답 없음"}',
        },
        # 원문이 600자에서 잘려 JSON이 깨져도 오류는 찾는다
        {
            "worker": "job",
            "summary": '[search_jobs] {"jobs": [], "error": "고용24 점검 중", "fallb',
        },
        {"worker": "benefit", "summary": "[search_benefits] 그냥 글"},
    ]
    assert runlog.failures_from(findings) == [
        {"where": "benefit", "error": "조회 시간 초과"},
        {"where": "regulation/search_benefits", "error": "정부24 응답 없음"},
        {"where": "job/search_jobs", "error": "고용24 점검 중"},
    ]


def test_question_is_masked_before_saving():
    timer = runlog.RunTimer("제 주민번호는 990101-1234567 이에요")
    assert "1234567" not in timer.question


def test_chat_is_recorded():
    with make_client(
        [Route(next="regulation"), Route(next="answer")],
        profile=Profile(service_type="conscript"),
    ) as client:
        client.post("/chat", json={"message": "군복무 크레딧?"})
        client.post("/chat", json={"message": "군복무 크레딧?"})  # 같은 질문은 저장한 답
        with client.app.state.db.session() as session:
            runs = list(session.scalars(select(ChatRun).order_by(ChatRun.id)))
    first, second = runs
    assert first.kind == "research" and second.kind == "cached"
    assert first.first_ms is not None and first.total_ms >= first.first_ms
    assert [s["node"] for s in first.steps][:3] == ["start", "guard", "profile"]


def add_run(db, **kw):
    values = {"kind": "research", "question": "q", "total_ms": 10000, "first_ms": 5000,
              "steps": [], "failures": [], "error": ""}  # fmt: skip
    values.update(kw)
    with db.session() as session:
        session.add(ChatRun(**values))


def test_summary_finds_slow_steps_failures_and_down_votes():
    db = Database(temp_db())
    db.migrate()
    steps = [{"node": "profile", "ms": 1000}, {"node": "regulation", "ms": 9000},
             {"node": "respond", "ms": 12000}]  # fmt: skip
    for _ in range(3):
        add_run(db, steps=steps)
    add_run(db, kind="cached", total_ms=50, first_ms=40)
    add_run(db, failures=[{"where": "benefit", "error": "조회 시간 초과"}], question="취업 지원?")
    add_run(db, kind="error", error="TimeoutError", question="연금?")
    old = datetime.now(UTC) - timedelta(days=10)
    add_run(db, created_at=old, failures=[{"where": "old", "error": "x"}])  # 기간 밖
    with db.session() as session:
        session.add(
            Feedback(rating="down", question="전직지원금 얼마?", answer="a", comment="틀림")
        )
        session.add(Feedback(rating="down", question="전직지원금 얼마?", answer="b"))
        session.add(Feedback(rating="up", question="크레딧?", answer="c"))

    s = runlog.summary(db, days=7)
    assert s["chats"]["total"] == 6
    assert s["chats"]["by_kind"] == {"research": 4, "cached": 1, "error": 1}
    # 가장 느린 단계: 규정 찾기 (1초 → 9초, 8초)
    assert s["slow_steps"][0] == {"node": "regulation", "count": 3, "p50_ms": 8000, "p90_ms": 8000}
    assert s["latency"]["first_p50_ms"] == 5000 and s["latency"]["cases"] == 4
    assert s["failures"]["by_where"] == {"benefit": 1}
    assert s["errors"][0]["error"] == "TimeoutError"
    assert s["feedback"]["down"] == 2 and s["feedback"]["up"] == 1
    assert s["feedback"]["top_down_questions"] == [{"question": "전직지원금 얼마?", "count": 2}]
    assert s["feedback"]["recent_down"][0]["comment"] in ("틀림", "")
    assert len(s["daily"]) == 7 and s["daily"][-1]["count"] == 6


def test_admin_summary_needs_the_token(monkeypatch):
    s = get_settings()
    with make_client([Route(next="answer")]) as client:
        monkeypatch.setattr(s, "admin_token", "")
        off = client.get("/admin/summary")
        monkeypatch.setattr(s, "admin_token", "secret-token")
        no_key = client.get("/admin/summary")
        wrong = client.get("/admin/summary", headers={"X-Admin-Token": "nope"})
        ok = client.get("/admin/summary", headers={"X-Admin-Token": "secret-token"})
    assert off.status_code == 404
    assert no_key.status_code == 401 and wrong.status_code == 401
    assert ok.status_code == 200 and ok.json()["days"] == 7
