"""FastAPI 서버 테스트. 에이전트는 가짜 컴포넌트로 만든 실제 그래프를 쓴다."""

import json
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient
from helpers import make_components
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from jeonyeok_helper.agents.graph import build_graph
from jeonyeok_helper.agents.state import Profile, Route
from jeonyeok_helper.api.main import create_app


def make_client(routes, **kwargs) -> TestClient:
    components, _ = make_components(routes, **kwargs)
    graph = build_graph(components, checkpointer=InMemorySaver(), store=InMemoryStore())

    @asynccontextmanager
    async def factory():
        yield graph

    return TestClient(create_app(agent_factory=factory))


def no_agent_client() -> TestClient:
    @asynccontextmanager
    async def factory():
        raise RuntimeError("GOOGLE_API_KEY가 설정되지 않았습니다.")
        yield

    return TestClient(create_app(agent_factory=factory))


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


def test_web_page_is_served():
    with no_agent_client() as client:
        resp = client.get("/")
    assert resp.status_code == 200
    assert "전역도우미" in resp.text


def test_web_page_ids_are_unique():
    # 아이콘 <symbol id="home">과 화면 영역 id="home"이 겹쳐 화면 전환이 깨진 적이 있다.
    import re
    from collections import Counter

    from jeonyeok_helper.api.main import WEB_DIR

    ids = re.findall(r'\bid="([^"]+)"', (WEB_DIR / "index.html").read_text(encoding="utf-8"))
    assert [i for i, n in Counter(ids).items() if n > 1] == []
