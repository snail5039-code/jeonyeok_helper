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
        resp = client.post("/chat", json={"message": "군복무 크레딧?", "user_id": "u1"})

    assert resp.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(resp.text)
    names = [e for e, _ in events]
    assert names[0] == "thread" and names[-1] == "done"
    steps = [d["node"] for e, d in events if e == "step"]
    assert steps == ["profile", "regulation", "respond", "verify"]
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


def journey_client(planner=None) -> TestClient:
    seen = []

    async def builder(profile):
        seen.append(profile)
        return ROADMAP

    client = make_client(
        [Route(next="regulation"), Route(next="answer")] * 3,
        app_kwargs={"roadmap_builder": builder, "planner": planner},
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


def test_chat_puts_planned_items_on_journey():
    calls = []

    async def planner(**kwargs):
        calls.append(kwargs)
        return [
            {"stage": "job", "title": "국민취업지원제도", "action": "고용24에서 신청하세요",
             "detail": "", "sources": kwargs["sources"][:1]},
        ]  # fmt: skip

    with journey_client(planner) as client:
        events = parse_sse(
            client.post("/chat", json={"message": "취업 지원?", "user_id": "u1"}).text
        )
        names = [e for e, _ in events]
        assert names.index("answer") < names.index("plan") < names.index("done")
        plan = next(d for e, d in events if e == "plan")
        assert plan["added"][0]["title"] == "국민취업지원제도"
        assert plan["added"][0]["origin"] == "chat" and plan["added"][0]["question"] == "취업 지원?"

        # 다음 답변에서는 이미 담긴 할 일을 알려 주고, 같은 할 일은 다시 담지 않는다
        events = parse_sse(client.post("/chat", json={"message": "또", "user_id": "u1"}).text)
        assert calls[1]["existing"] == ["국민취업지원제도"]
        assert not any(e == "plan" for e, _ in events)
        # user_id가 없으면 로드맵에 담지 않는다
        parse_sse(client.post("/chat", json={"message": "익명"}).text)
        assert len(calls) == 2


def test_journey_generate_without_agent_returns_503():
    with no_agent_client() as client:
        assert client.post("/journey/u1/generate").status_code == 503


def test_feedback_rejects_unknown_rating():
    with make_client([Route(next="answer")]) as client:
        body = {"rating": "meh", "question": "q", "answer": "a"}
        assert client.post("/feedback", json=body).status_code == 422
