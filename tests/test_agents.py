"""슈퍼바이저 그래프 흐름 테스트. LLM 대신 정해진 답을 돌려주는 가짜 Runnable을 쓴다."""

import asyncio
import json

from helpers import make_components
from langchain_core.language_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from jeonyeok_helper.agents.graph import build_graph
from jeonyeok_helper.agents.state import Profile, Route, add_or_reset, merge_profile
from jeonyeok_helper.agents.workers import extract_sources, make_react_worker


def run(coro):
    return asyncio.run(coro)


def ask(graph, text, thread="t1", user=None):
    config = {"configurable": {"thread_id": thread, **({"user_id": user} if user else {})}}
    return run(graph.ainvoke({"messages": [("user", text)]}, config))


# ---------- 기본 흐름 ----------


def test_supervisor_calls_worker_then_answers_with_verified_text():
    components, rec = make_components(
        [Route(next="regulation", instruction="군복무 크레딧 근거"), Route(next="answer")]
    )
    graph = build_graph(components, checkpointer=InMemorySaver())

    state = ask(graph, "군복무 크레딧이 뭐야?")

    assert rec["worker"].calls[0]["instruction"] == "군복무 크레딧 근거"
    assert state["messages"][-1].text == "최종 답변 [1]"
    assert state["sources"] == [{"type": "regulation", "title": "국민연금법 제18조", "url": "u1"}]
    # 답변·검증 단계에 워커가 찾은 내용과 번호 붙은 출처가 전달된다.
    assert "국민연금법 제18조" in rec["responder"].calls[0]["findings"]
    assert rec["verifier"].calls[0]["sources"] == "[1] 국민연금법 제18조 - u1"
    assert rec["verifier"].calls[0]["draft"] == "초안 답변 [1]"


def test_ask_user_returns_question_without_answering():
    components, rec = make_components(
        [Route(next="ask_user", question="병사로 전역하셨나요, 간부로 전역하셨나요?")]
    )
    graph = build_graph(components, checkpointer=InMemorySaver())

    state = ask(graph, "나 뭐 받을 수 있어?")

    assert state["messages"][-1].text == "병사로 전역하셨나요, 간부로 전역하셨나요?"
    assert rec["responder"].calls == [] and rec["worker"].calls == []


def test_worker_calls_are_capped():
    components, rec = make_components([Route(next="benefit", instruction="또 찾아")])
    graph = build_graph(components, checkpointer=InMemorySaver(), max_worker_calls=3)

    state = ask(graph, "혜택 다 찾아줘")

    assert len(rec["worker"].calls) == 3
    assert state["messages"][-1].text == "최종 답변 [1]"


# ---------- 폴백 ----------


def test_worker_failure_is_recorded_and_flow_continues():
    components, rec = make_components(
        [Route(next="benefit"), Route(next="answer")],
        worker_out=RuntimeError("API 503"),
    )
    graph = build_graph(components, checkpointer=InMemorySaver())

    state = ask(graph, "혜택 알려줘")

    assert state["findings"] == [{"worker": "benefit", "summary": "(조회 실패: API 503)"}]
    assert state["messages"][-1].text == "최종 답변 [1]"


def test_verifier_failure_falls_back_to_draft():
    components, _ = make_components([Route(next="answer")], verifier=RuntimeError("timeout"))
    graph = build_graph(components, checkpointer=InMemorySaver())

    assert ask(graph, "안녕")["messages"][-1].text == "초안 답변 [1]"


def test_router_failure_answers_with_what_we_have():
    components, rec = make_components([RuntimeError("bad json")])
    graph = build_graph(components, checkpointer=InMemorySaver())

    assert ask(graph, "질문")["messages"][-1].text == "최종 답변 [1]"
    assert rec["worker"].calls == []


def test_missing_worker_routes_to_answer():
    components, _ = make_components(
        [Route(next="benefit")], workers={"regulation": RunnableLambda(lambda _: {})}
    )
    graph = build_graph(components, checkpointer=InMemorySaver())

    assert ask(graph, "혜택")["messages"][-1].text == "최종 답변 [1]"


# ---------- 메모리 ----------


def test_turn_state_resets_but_profile_persists_in_thread():
    components, rec = make_components(
        [Route(next="regulation"), Route(next="answer")],
        profile=Profile(service_type="conscript", region="서울"),
    )
    graph = build_graph(components, checkpointer=InMemorySaver())

    ask(graph, "병사로 전역했고 서울 살아요. 군복무 크레딧 알려줘")
    rec["profile"].outputs = [Profile()]  # 두 번째 질문에서는 새 정보 없음
    rec["router"].outputs = [Route(next="institution"), Route(next="answer")]
    state = ask(graph, "그럼 신청은 어디서 해?")

    assert state["profile"] == {"service_type": "conscript", "region": "서울"}
    assert len(state["findings"]) == 1  # 이전 턴의 결과는 지워짐
    assert len(state["messages"]) == 4


def test_profile_is_shared_across_threads_via_store():
    store = InMemoryStore()
    components, rec = make_components(
        [Route(next="answer")], profile=Profile(service_type="long_term", service_years=12)
    )
    graph = build_graph(components, checkpointer=InMemorySaver(), store=store)

    ask(graph, "12년 복무하고 전역 예정이에요", thread="a", user="u1")
    rec["profile"].outputs = [Profile()]
    state = ask(graph, "전직지원금 있어?", thread="b", user="u1")

    assert state["profile"] == {"service_type": "long_term", "service_years": 12}


def test_reducers():
    assert merge_profile({"age": 22, "region": "서울"}, {"age": None, "region": "경기"}) == {
        "age": 22,
        "region": "경기",
    }
    assert add_or_reset([1], [2]) == [1, 2]
    assert add_or_reset([1, 2], None) == []


# ---------- 워커 ----------


def tool_msg(name, payload):
    return ToolMessage(
        content=[{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        name=name,
        tool_call_id="1",
    )


def test_extract_sources_from_mcp_tool_results():
    messages = [
        tool_msg("search_regulations", {"results": [{"citation": "병역법 제1조", "url": "a"}]}),
        tool_msg("search_benefits", {"benefits": [{"name": "전직지원금", "url": "b"}]}),
        tool_msg(
            "search_benefits", {"benefits": [], "error": "x", "fallback": [{"name": "정부24"}]}
        ),
        tool_msg("find_institutions", {"institutions": [{"name": "병무청", "url": "c"}]}),
        tool_msg("search_regulations", {"results": [{"citation": "병역법 제1조", "url": "a"}]}),
        ToolMessage(content="not json", name="x", tool_call_id="2"),
    ]

    assert extract_sources(messages) == [
        {"type": "regulation", "title": "병역법 제1조", "url": "a"},
        {"type": "benefit", "title": "전직지원금", "url": "b"},
        {"type": "institution", "title": "정부24", "url": ""},
        {"type": "institution", "title": "병무청", "url": "c"},
    ]


class FakeToolModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def test_react_worker_calls_tool_and_returns_summary_with_sources():
    @tool
    def find_institutions(query: str) -> str:
        """기관 찾기"""
        return json.dumps({"institutions": [{"name": "병무청", "url": "https://www.mma.go.kr"}]})

    model = FakeToolModel(
        messages=iter(
            [
                AIMessage(
                    "",
                    tool_calls=[
                        {"name": "find_institutions", "args": {"query": "예비군"}, "id": "c1"}
                    ],
                ),
                AIMessage("예비군은 병무청에서 확인하세요."),
            ]
        )
    )
    worker = make_react_worker(model, [find_institutions], "기관 담당")

    out = run(worker.ainvoke({"messages": [("user", "예비군 어디서 확인해?")], "instruction": ""}))

    assert out["summary"] == "예비군은 병무청에서 확인하세요."
    assert out["sources"] == [
        {"type": "institution", "title": "병무청", "url": "https://www.mma.go.kr"}
    ]


# ---------- 실제 조립 (MCP 서버 연결) ----------


class FakeStructuredModel(FakeToolModel):
    def with_structured_output(self, schema, **kwargs):
        return RunnableLambda(lambda _: schema.model_construct())


def test_open_agent_wires_real_mcp_tools_to_workers():
    from jeonyeok_helper.agents.runtime import open_agent

    async def check():
        async with open_agent(llm=FakeStructuredModel(messages=iter([]))) as agent:
            return set(agent.get_graph().nodes)

    nodes = run(check())

    assert {"regulation", "benefit", "institution", "supervisor", "verify"} <= nodes
