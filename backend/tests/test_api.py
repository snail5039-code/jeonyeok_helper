"""FastAPI 서버 테스트. 에이전트는 가짜 컴포넌트로 만든 실제 그래프를 쓴다."""

import json
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi.testclient import TestClient
from helpers import make_components
from langchain_core.language_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from jeonyeok_helper.agents.graph import build_graph
from jeonyeok_helper.agents.guide import CoachDecision, GuideDraft, PlanItemDraft
from jeonyeok_helper.agents.state import Profile, Route, Verification
from jeonyeok_helper.api.main import create_app
from jeonyeok_helper.db import Feedback


def temp_db() -> str:
    """테스트마다 새 SQLite 파일 (실제 data/app.sqlite는 건드리지 않는다)."""
    return f"sqlite:///{Path(tempfile.mkdtemp()).as_posix()}/app.sqlite"


def make_client(routes, app_kwargs: dict | None = None, **kwargs) -> TestClient:
    components, _ = make_components(routes, **kwargs)
    graph = build_graph(components, checkpointer=InMemorySaver(), store=InMemoryStore())

    @asynccontextmanager
    async def factory():
        yield graph

    return TestClient(create_app(agent_factory=factory, db_url=temp_db(), **(app_kwargs or {})))


def no_agent_client() -> TestClient:
    @asynccontextmanager
    async def factory():
        raise RuntimeError("GOOGLE_API_KEY가 설정되지 않았습니다.")
        yield

    return TestClient(create_app(agent_factory=factory, db_url=temp_db()))


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_health_reports_key_flags_without_values():
    with no_agent_client() as client:
        body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["agent_ready"] is False
    assert all(isinstance(v, bool) for v in body["keys"].values())


def test_chat_streams_steps_then_answer_with_sources():
    with make_client(
        [Route(next="regulation"), Route(next="answer")],
        profile=Profile(service_type="conscript"),
    ) as client:
        resp = client.post(
            "/chat", json={"message": "병사로 전역했는데 군복무 크레딧?", "user_id": "u1"}
        )

    assert resp.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(resp.text)
    names = [e for e, _ in events]
    assert names[0] == "thread" and names[-1] == "done"
    steps = [d["node"] for e, d in events if e == "step"]
    assert steps[:3] == ["profile", "regulation", "respond"]
    assert sorted(steps[3:]) == ["guide", "verify"]  # 검증과 말풍선은 동시에
    answer = next(d for e, d in events if e == "answer")
    assert answer["text"] == "최종 답변 [1]"
    assert answer["sources"][0]["title"] == "국민연금법 제18조"
    assert answer["profile"] == {"service_type": "conscript"}


def test_chat_streams_draft_deltas_before_verified_answer():
    components, _ = make_components([Route(next="answer")])
    # 실제 모델처럼 토큰을 나눠 내보내는 가짜 모델 (단어 단위)
    model = GenericFakeChatModel(messages=iter([AIMessage("초안 답변 입니다")]))
    components.responder = RunnableLambda(lambda _: "프롬프트") | model | StrOutputParser()
    graph = build_graph(components, checkpointer=InMemorySaver())

    @asynccontextmanager
    async def factory():
        yield graph

    with TestClient(create_app(agent_factory=factory, db_url=temp_db())) as client:
        events = parse_sse(client.post("/chat", json={"message": "질문"}).text)

    names = [e for e, _ in events]
    deltas = [d["text"] for e, d in events if e == "delta"]
    assert len(deltas) > 1 and "".join(deltas) == "초안 답변 입니다"
    # 초안 조각이 먼저 오고, 검증을 마친 최종 답변이 뒤에 온다
    assert names.index("delta") < names.index("answer")
    assert next(d for e, d in events if e == "answer")["text"] == "최종 답변 [1]"


def test_answer_carries_follow_up_questions():
    verified = Verification(
        supported=True, follow_ups=["신청은 어디서 해요?", "  ", "부산 혜택도 있어요?", "a", "b"]
    )
    with make_client([Route(next="answer")], verifier=verified) as client:
        events = parse_sse(client.post("/chat", json={"message": "질문"}).text)

    answer = next(d for e, d in events if e == "answer")
    assert answer["text"] == "초안 답변 [1]"  # 문제가 없으면 초안 그대로
    # 빈 질문은 빼고 3개까지
    assert answer["follow_ups"] == ["신청은 어디서 해요?", "부산 혜택도 있어요?", "a"]


def test_chat_sends_question_when_agent_asks_back():
    with make_client([Route(next="ask_user", question="병사로 전역하셨나요?")]) as client:
        events = parse_sse(client.post("/chat", json={"message": "혜택 알려줘"}).text)

    assert ("question", {"text": "병사로 전역하셨나요?", "profile": {}}) in events
    assert not any(e == "answer" for e, _ in events)


def test_reply_to_question_resumes_the_paused_run():
    routes = [Route(next="ask_user", question="병사로 전역하셨나요?"), Route(next="answer")]
    with make_client(routes) as client:
        first = parse_sse(client.post("/chat", json={"message": "혜택 알려줘"}).text)
        thread_id = first[0][1]["thread_id"]
        second = parse_sse(
            client.post("/chat", json={"message": "네 병사요", "thread_id": thread_id}).text
        )
        messages = client.app.state.agent.get_state(
            {"configurable": {"thread_id": thread_id}}
        ).values["messages"]

    assert any(e == "question" for e, _ in first)
    assert any(e == "answer" for e, _ in second)
    # 질문 → 되물음 → 답 → 최종 답변이 한 흐름으로 남는다
    assert [m.text for m in messages][:3] == ["혜택 알려줘", "병사로 전역하셨나요?", "네 병사요"]


def test_same_thread_keeps_conversation():
    with make_client([Route(next="answer")]) as client:
        first = parse_sse(client.post("/chat", json={"message": "안녕"}).text)
        thread_id = first[0][1]["thread_id"]
        client.post("/chat", json={"message": "또 질문", "thread_id": thread_id})
        state_len = len(
            client.app.state.agent.get_state({"configurable": {"thread_id": thread_id}}).values[
                "messages"
            ]
        )
    assert state_len == 4


def test_profile_endpoint_reads_long_term_memory():
    with make_client([Route(next="answer")], profile=Profile(region="부산")) as client:
        assert client.get("/profile/u9").json() == {"profile": {}}
        client.post("/chat", json={"message": "부산 살아요", "user_id": "u9"})
        assert client.get("/profile/u9").json() == {"profile": {"region": "부산"}}


def test_chat_without_agent_returns_503_with_reason():
    with no_agent_client() as client:
        resp = client.post("/chat", json={"message": "안녕"})
    assert resp.status_code == 503
    assert "GOOGLE_API_KEY" in resp.json()["detail"]


def test_empty_message_is_rejected():
    with make_client([Route(next="answer")]) as client:
        assert client.post("/chat", json={"message": ""}).status_code == 422


def test_feedback_is_saved_and_counted():
    with make_client([Route(next="answer")]) as client:
        body = {"rating": "up", "question": "군복무 크레딧?", "answer": "가입기간에 넣어 줘요"}
        first = client.post("/feedback", json=body | {"thread_id": "t1", "user_id": "u1"})
        client.post("/feedback", json=body | {"rating": "down", "comment": "금액이 없어요"})

        assert first.status_code == 201 and first.json()["id"] == 1
        assert client.get("/feedback/summary").json() == {"up": 1, "down": 1}
        with client.app.state.db.session() as session:
            saved = session.get(Feedback, 2)
            assert (saved.rating, saved.comment) == ("down", "금액이 없어요")


# ---------- 내 정보 ----------


def test_profile_put_merges_and_clears_fields():
    with make_client([Route(next="answer")]) as client:
        body = {"service_type": "conscript", "region": "부산", "goals": ["취업", "복학"]}
        assert client.put("/profile/u1", json=body).json()["profile"] == body
        # 보낸 항목만 바꾸고, 빈 값은 지운다
        after = client.put("/profile/u1", json={"region": "", "rank": "병장"}).json()["profile"]
        assert after == {"service_type": "conscript", "goals": ["취업", "복학"], "rank": "병장"}
        assert client.get("/profile/u1").json()["profile"] == after
        assert client.put("/profile/u1", json={"age": 7}).status_code == 422
        assert client.get("/profile/bad%20id").status_code == 422


def test_profile_from_form_reaches_the_agent():
    with make_client([Route(next="answer")]) as client:
        client.put("/profile/u2", json={"service_type": "long_term", "desired_job": "시설관리"})
        events = parse_sse(client.post("/chat", json={"message": "q", "user_id": "u2"}).text)
    answer = next(d for e, d in events if e == "answer")
    assert answer["profile"]["desired_job"] == "시설관리"


# ---------- 전역 로드맵 ----------

ROADMAP = {
    "intro": "병사 로드맵",
    "stages": [
        {
            "key": "right_after",
            "title": "전역 직후",
            "items": [
                {"title": "예비군 편성 확인", "action": "확인하세요", "detail": "", "sources": []},
                {"title": "적금 수령", "action": "받으세요", "detail": "", "sources": []},
            ],
        }
    ],
}


def journey_client(**kwargs) -> TestClient:
    seen = []

    async def builder(profile):
        seen.append(profile)
        return ROADMAP

    client = make_client(
        [Route(next="regulation"), Route(next="answer")] * 3,
        app_kwargs={"roadmap_builder": builder},
        **kwargs,
    )
    client.seen_profiles = seen
    return client


def test_journey_generate_uses_stored_profile_once():
    with journey_client() as client:
        missing = client.post("/journey/u1/generate")
        assert missing.status_code == 400 and "복무 형태" in missing.json()["detail"]

        client.put(
            "/profile/u1", json={"service_type": "conscript", "goals": ["취업"], "rank": "병장"}
        )
        first = client.post("/journey/u1/generate").json()
        assert first["added"] == 2 and [i["title"] for i in first["items"]] == [
            "예비군 편성 확인",
            "적금 수령",
        ]
        assert client.post("/journey/u1/generate").json()["added"] == 0  # 같은 할 일은 한 번만
        sent = client.seen_profiles[0]
        assert sent.goals == ["취업"] and "계급=병장" in sent.notes


def test_journey_item_done_and_delete_only_for_owner():
    with journey_client() as client:
        client.put("/profile/u1", json={"service_type": "conscript"})
        item = client.post("/journey/u1/generate").json()["items"][0]

        done = client.patch(f"/journey/u1/items/{item['id']}", json={"done": True}).json()
        assert done["done"] is True and done["done_at"]
        assert (
            client.patch(f"/journey/u2/items/{item['id']}", json={"done": True}).status_code == 404
        )
        assert client.delete(f"/journey/u2/items/{item['id']}").status_code == 404
        assert client.delete(f"/journey/u1/items/{item['id']}").status_code == 204
        assert [i["title"] for i in client.get("/journey/u1").json()["items"]] == ["적금 수령"]


# ---------- 길잡이 ----------

TALK = CoachDecision(mode="talk", say="좋아요! 다음 할 일 알려 드릴게요.")
FULL_PROFILE = {"service_type": "conscript", "region": "서울", "discharge_date": "2026-03"}


def test_research_answer_comes_with_guide_suggestions_that_user_picks():
    draft = GuideDraft(
        say="국민취업지원제도부터 신청하세요.",
        items=[
            PlanItemDraft(stage="job", title="국민취업지원제도", action="신청하세요", sources=[1],
                          core=True, deadline="지어낸 기한", due_months=12),
            PlanItemDraft(stage="job", title="근거 없음", action="x", sources=[]),
        ],
    )  # fmt: skip
    with journey_client(coach=[CoachDecision(mode="research")], guide=[draft]) as client:
        events = parse_sse(
            client.post("/chat", json={"message": "취업 지원?", "user_id": "u1"}).text
        )
        names = [e for e, _ in events]
        assert names.index("answer") < names.index("guide") < names.index("done")
        guide = next(d for e, d in events if e == "guide")
        # 복무 형태를 모르면 길잡이 말 끝에 묻는 말을 붙인다
        assert guide["mode"] == "research"
        assert guide["say"] == "국민취업지원제도부터 신청하세요. 어떻게 복무했어요?"
        # 근거 출처가 있는 것만, 답변에 없는 기한은 지운다
        [item] = guide["suggest"]
        assert item["title"] == "국민취업지원제도" and item["core"] is True
        assert (item["deadline"], item["due_months"]) == ("", None)
        assert item["sources"][0]["title"] == "국민연금법 제18조"
        # 복무 형태를 모르니 고르는 버튼이 함께 온다
        assert guide["ask"] == "service_type" and len(guide["quick_replies"]) == 4
        # 제안은 저장하지 않고, 사용자가 고른 것만 담는다
        assert client.get("/journey/u1").json()["items"] == []
        added = client.post("/journey/u1/items", json={"items": [item], "question": "취업 지원?"})
        assert added.status_code == 201
        assert added.json()["added"][0]["origin"] == "chat"
        again = client.post("/journey/u1/items", json={"items": [item]}).json()
        assert again["added"] == []  # 같은 제목은 한 번만
        assert client.post("/journey/u1/items", json={"items": []}).status_code == 422


def test_talk_reply_skips_search_and_asks_missing_field_with_buttons():
    with make_client([Route(next="regulation")], coach=[TALK]) as client:
        events = parse_sse(client.post("/chat", json={"message": "안녕", "user_id": "u1"}).text)
    names = [e for e, _ in events]
    assert "answer" not in names and "question" not in names
    assert [d["node"] for e, d in events if e == "step"] == ["profile"]  # 검색 없음
    guide = next(d for e, d in events if e == "guide")
    assert guide["mode"] == "talk" and guide["say"] == f"{TALK.say} 어떻게 복무했어요?"
    assert guide["ask"] == "service_type" and guide["step"] is None
    assert guide["quick_replies"][0]["message"] == "의무복무 병사로 전역했어요"


def test_onboarding_complete_builds_first_roadmap_and_suggests_first_step():
    with journey_client(coach=[TALK]) as client:
        client.put("/profile/u1", json=FULL_PROFILE)
        events = parse_sse(
            client.post("/chat", json={"message": "작년에 전역했어요", "user_id": "u1"}).text
        )
        added = next(d for e, d in events if e == "journey")["added"]
        assert [i["title"] for i in added] == ["예비군 편성 확인", "적금 수령"]
        last_guide = [d for e, d in events if e == "guide"][-1]
        assert last_guide["step"]["title"] == "예비군 편성 확인"
        assert "작전도 완성" in last_guide["say"]
        # 로드맵이 이미 있으면 다시 만들지 않는다
        client.post("/chat", json={"message": "또", "user_id": "u1"})
        assert len(client.seen_profiles) == 1
        # 담긴 임무를 모두 되돌려 비워도 다시 만들지 않는다 (사용자가 고른 것)
        for item in client.get("/journey/u1").json()["items"]:
            client.delete(f"/journey/u1/items/{item['id']}")
        events = parse_sse(client.post("/chat", json={"message": "다시", "user_id": "u1"}).text)
        assert not any(e == "journey" for e, _ in events)
        assert len(client.seen_profiles) == 1


def test_done_button_marks_item_and_coach_moves_to_next():
    with journey_client(coach=[TALK]) as client:
        client.put("/profile/u1", json=FULL_PROFILE)
        first, second = client.post("/journey/u1/generate").json()["items"]
        events = parse_sse(
            client.post(
                "/chat",
                json={"message": "했어요", "user_id": "u1",
                      "action": {"type": "done", "item_id": first["id"]}},
            ).text
        )  # fmt: skip
        done = next(d for e, d in events if e == "journey")["done"]
        assert done["id"] == first["id"] and done["done"] is True
        guide = next(d for e, d in events if e == "guide")
        assert guide["step"]["id"] == second["id"]
        # 길잡이 말에 다음 할 일이 없으면 덧붙여서 대화가 끊기지 않게 한다
        assert f"다음은 '{second['title']}' 차례예요." in guide["say"]
        assert guide["quick_replies"][0]["action"] == {"type": "done", "item_id": second["id"]}


def test_later_button_skips_item_in_this_conversation():
    with journey_client(coach=[TALK]) as client:
        client.put("/profile/u1", json=FULL_PROFILE)
        first, second = client.post("/journey/u1/generate").json()["items"]
        events = parse_sse(
            client.post(
                "/chat",
                json={"message": "나중에", "user_id": "u1",
                      "action": {"type": "later", "item_id": first["id"]}},
            ).text
        )  # fmt: skip
        guide = next(d for e, d in events if e == "guide")
        assert guide["step"]["id"] == second["id"]
        assert client.get("/journey/u1").json()["items"][0]["done"] is False


def test_journey_generate_without_agent_returns_503():
    with no_agent_client() as client:
        assert client.post("/journey/u1/generate").status_code == 503


def test_feedback_rejects_unknown_rating():
    with make_client([Route(next="answer")]) as client:
        body = {"rating": "meh", "question": "q", "answer": "a"}
        assert client.post("/feedback", json=body).status_code == 422


def test_removed_item_can_be_restored_with_its_state():
    with journey_client() as client:
        client.put("/profile/u1", json={"service_type": "conscript"})
        item = client.post("/journey/u1/generate").json()["items"][0]
        client.patch(f"/journey/u1/items/{item['id']}", json={"done": True})
        done = client.get("/journey/u1").json()["items"][0]
        client.delete(f"/journey/u1/items/{item['id']}")
        # 되돌리기: 빼기 전 상태(완료, 원래 출처) 그대로 다시 담는다
        body = {
            k: done[k]
            for k in (
                "stage",
                "title",
                "action",
                "detail",
                "sources",
                "core",
                "deadline",
                "due_months",
                "done",
                "origin",
            )
        }
        restored = client.post("/journey/u1/items", json={"items": [body]}).json()["added"][0]
        assert (
            restored["title"] == done["title"] and restored["done"] is True and restored["done_at"]
        )
        assert restored["origin"] == "plan"


def test_rate_limiter_blocks_after_limit_and_recovers_after_window():
    from jeonyeok_helper.api.limits import RateLimiter

    limiter = RateLimiter(2, window=60)
    assert limiter.allow("a", now=0) and limiter.allow("a", now=1)
    assert not limiter.allow("a", now=2)  # 3번째는 막힘
    assert limiter.allow("b", now=2)  # 다른 사용자는 영향 없음
    assert limiter.allow("a", now=61)  # 창이 지나면 다시 허용
    assert RateLimiter(0).allow("a")  # 0이면 제한 없음


def test_chat_returns_429_with_a_message_when_over_the_limit():
    from jeonyeok_helper.api.limits import RateLimiter

    with make_client(
        [Route(next="regulation"), Route(next="answer")], profile=Profile(service_type="conscript")
    ) as client:
        client.app.state.limiter = RateLimiter(1)
        ok = client.post("/chat", json={"message": "군복무 크레딧?", "user_id": "u-limit"})
        blocked = client.post("/chat", json={"message": "또 물어요", "user_id": "u-limit"})
        other = client.post("/chat", json={"message": "군복무 크레딧?", "user_id": "u-other"})
    assert ok.status_code == 200 and other.status_code == 200
    assert blocked.status_code == 429
    assert "너무 많아요" in blocked.json()["detail"]


def test_answer_cache_keys_skip_contextual_questions_and_expire():
    from jeonyeok_helper.api.cache import AnswerCache

    cache = AnswerCache(ttl=10)
    key = cache.key("군복무 크레딧이 뭐예요?", {"service_type": "conscript"}, [])
    assert key == cache.key("군복무  크레딧이 뭐예요? ", {"service_type": "conscript"}, [])
    assert key != cache.key("군복무 크레딧이 뭐예요?", {"service_type": "long_term"}, [])
    assert cache.key("그거 신청 어디서 해요?", {}, []) is None  # 앞 대화에 기대는 질문
    cache.put(key, {"answer": {"text": "a"}}, now=0)
    assert cache.get(key, now=5) == {"answer": {"text": "a"}}
    assert cache.get(key, now=11) is None


def test_same_question_with_same_conditions_is_answered_from_cache():
    with make_client(
        [Route(next="regulation"), Route(next="answer")],
        profile=Profile(service_type="conscript"),
    ) as client:
        ask = {"message": "병사로 전역했는데 군복무 크레딧?", "user_id": "u1"}
        first = parse_sse(client.post("/chat", json=ask).text)
        # 조건이 같은 다른 사람(처음 온 사람)이 같은 질문을 하면 저장한 답
        second = parse_sse(client.post("/chat", json={**ask, "user_id": "u2"}).text)
        profile = client.get("/profile/u2").json()["profile"]

    answer1 = next(d for e, d in first if e == "answer")
    answer2 = next(d for e, d in second if e == "answer")
    assert answer2["text"] == answer1["text"] and answer2["sources"] == answer1["sources"]
    assert not any(e == "step" for e, _ in second)  # 모델·검색을 다시 돌지 않았다
    assert profile["service_type"] == "conscript"  # 내 정보도 정상 실행처럼 남는다


# ---------- 내 기록 파일 (로그인 대신) ----------


def test_backup_round_trip_restores_profile_and_journey_on_another_browser():
    item = {
        "stage": "job", "title": "국민취업지원제도", "action": "고용24에서 신청",
        "sources": [{"type": "benefit", "title": "국민취업지원제도", "url": "u"}],
        "core": True, "deadline": "전역 후 1년 이내", "due_months": 12, "done": True,
        "origin": "plan",
    }  # fmt: skip
    with make_client([Route(next="answer")]) as client:
        client.put("/profile/old-browser", json={"service_type": "conscript", "region": "부산"})
        client.post("/journey/old-browser/items", json={"items": [item], "question": "취업"})
        backup = client.get("/backup/old-browser").json()

        # 다른 브라우저(새 익명 ID)에 이미 다른 기록이 있어도 파일 내용으로 바뀐다
        client.post("/journey/new-browser/items", json={"items": [{**item, "title": "지울 것"}]})
        restored = client.put("/backup/new-browser", json=backup).json()
        items = client.get("/journey/new-browser").json()["items"]
        profile = client.get("/profile/new-browser").json()["profile"]

    assert backup["app"] == "jeonyeok_helper" and backup["version"] == 1
    assert profile == {"service_type": "conscript", "region": "부산"}
    assert (
        [i["title"] for i in items]
        == ["국민취업지원제도"]
        == [i["title"] for i in restored["items"]]
    )
    got = items[0]
    assert got["done"] and got["core"] and got["due_months"] == 12
    assert got["deadline"] == "전역 후 1년 이내" and got["origin"] == "plan"
    assert got["question"] == "취업" and got["sources"][0]["title"] == "국민취업지원제도"


def test_backup_rejects_files_from_other_apps():
    with make_client([Route(next="answer")]) as client:
        res = client.put("/backup/u1", json={"app": "other", "version": 1, "items": []})
    assert res.status_code == 422


# ---------- 이어 하기 코드 ----------


def test_resume_code_opens_the_same_records_on_another_device():
    with make_client([Route(next="answer")]) as client:
        assert client.get("/resume-code/pc").json() == {"code": None}
        code = client.post("/resume-code/pc").json()["code"]
        # 사람이 소문자·띄어쓰기로 적어도 찾는다
        typed = code.lower().replace("-", " ")
        found = client.post("/resume", json={"code": typed}).json()
        assert client.get("/resume-code/pc").json() == {"code": code}

        # 새 코드를 만들면 이전 코드는 못 쓴다
        newer = client.post("/resume-code/pc").json()["code"]
        old = client.post("/resume", json={"code": code})

    assert found == {"user_id": "pc"}
    assert newer != code and old.status_code == 404


def test_resume_code_format_and_normalize():
    from jeonyeok_helper import resume

    assert resume.normalize("jy-7k3q-9xpa") == "7K3Q9XPA"
    assert resume.normalize("7K3Q 9XPA") == "7K3Q9XPA"
    assert resume.normalize("JY-0OIL-9XPA") is None  # 코드에 없는 글자
    assert resume.normalize("short") is None
    assert resume.display("7K3Q9XPA") == "JY-7K3Q-9XPA"


def test_guessing_resume_codes_is_rate_limited():
    with make_client([Route(next="answer")]) as client:
        codes = [
            client.post("/resume", json={"code": "JY-2222-2222"}).status_code for _ in range(25)
        ]
    assert codes[0] == 404 and 429 in codes


# ---------- 자료 기준일 ----------


def test_answer_carries_data_as_of():
    from datetime import UTC, datetime

    from jeonyeok_helper.db import RefreshRun

    with make_client(
        [Route(next="regulation"), Route(next="answer")],
        profile=Profile(service_type="conscript"),
    ) as client:
        first = parse_sse(client.post("/chat", json={"message": "군복무 크레딧?"}).text)
        # 자료 자동 갱신이 한 번 돌면 그 날짜가 '확인일'이 된다 (10분 캐시를 비우고)
        with client.app.state.db.session() as session:
            session.add(
                RefreshRun(
                    started_at=datetime(2026, 10, 18, 9, tzinfo=UTC),
                    finished_at=datetime(2026, 10, 18, 16, tzinfo=UTC),  # 한국 시각 19일 새벽 1시
                    changed=[],
                    errors=[],
                )
            )
        client.app.state.as_of = None
        second = parse_sse(client.post("/chat", json={"message": "예비군 연기?"}).text)

    as_of = next(d for e, d in first if e == "answer")["as_of"]
    assert as_of == {"checked": None, "latest_enforced": None}
    assert next(d for e, d in second if e == "answer")["as_of"]["checked"] == "2026-10-19"


def test_as_of_picks_latest_enforced_date():
    from jeonyeok_helper.api.main import as_of

    class App:
        class state:
            as_of = (float("inf"), "2026-10-18")

    sources = [
        {"title": "a", "date": "20260101"},
        {"title": "b", "date": "20260820"},
        {"title": "c"},
        {"title": "d", "date": "엉뚱한 값"},
    ]
    assert as_of(App, sources) == {"checked": "2026-10-18", "latest_enforced": "20260820"}


def test_found_sources_arrive_before_the_answer():
    with make_client(
        [Route(next="regulation"), Route(next="answer")],
        profile=Profile(service_type="conscript"),
    ) as client:
        events = parse_sse(client.post("/chat", json={"message": "군복무 크레딧?"}).text)
    names = [e for e, _ in events]
    found = next(d for e, d in events if e == "found")
    assert found["node"] == "regulation"
    assert found["sources"][0]["title"] == "국민연금법 제18조"
    assert "excerpt" not in found["sources"][0]  # 미리 보기는 이름·주소만
    assert names.index("found") < names.index("answer")


def test_client_ip_trusts_forwarded_only_from_the_proxy():
    from starlette.requests import Request as StarletteRequest

    from jeonyeok_helper.api.main import client_ip

    def req(host, forwarded=None):
        headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
        return StarletteRequest({"type": "http", "client": (host, 1), "headers": headers})

    assert client_ip(req("127.0.0.1", "203.0.113.7")) == "203.0.113.7"  # Next 중계
    assert client_ip(req("172.18.0.5", "203.0.113.7, 10.0.0.1")) == "203.0.113.7"  # Docker web
    assert client_ip(req("8.8.4.4", "1.2.3.4")) == "8.8.4.4"  # 밖에서 바로: 믿지 않음
    assert client_ip(req("127.0.0.1")) == "127.0.0.1"


def test_resume_guessing_has_a_global_cap_even_with_fake_addresses(monkeypatch):
    from jeonyeok_helper.api import main

    monkeypatch.setattr(main, "GUESS_LIMIT_PER_MINUTE", 5)
    with make_client([Route(next="answer")]) as client:
        # 주소를 바꿔 가며 보내도(머리글 위조) 모두 합친 상한에 걸린다
        codes = [
            client.post(
                "/resume", json={"code": "JY-2222-2222"}, headers={"X-Forwarded-For": f"10.0.0.{i}"}
            ).status_code
            for i in range(8)
        ]
    assert codes[:5] == [404] * 5 and codes[5:] == [429] * 3
