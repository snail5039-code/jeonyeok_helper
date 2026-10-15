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
from jeonyeok_helper.agents.state import (
    Profile,
    Route,
    Verification,
    add_or_reset,
    merge_profile,
)
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
    rotation = [Route(next=w) for w in ("regulation", "benefit", "institution") * 3]
    components, rec = make_components(rotation)
    graph = build_graph(components, checkpointer=InMemorySaver(), max_worker_calls=3)

    state = ask(graph, "혜택 다 찾아줘")

    assert len(rec["worker"].calls) == 3
    assert state["messages"][-1].text == "최종 답변 [1]"


def test_also_workers_run_together_and_merge_results():
    components, rec = make_components(
        [
            Route(next="benefit", also=["regulation"], instruction="제대군인 혜택"),
            Route(next="answer"),
        ]
    )
    graph = build_graph(components, checkpointer=InMemorySaver())

    state = ask(graph, "제대군인 혜택 받을 수 있나요?")

    assert len(rec["worker"].calls) == 2  # 두 워커가 한 번에
    assert sorted(c["instruction"] for c in rec["worker"].calls) == ["", "제대군인 혜택"]
    assert {f["worker"] for f in state["findings"]} == {"benefit", "regulation"}
    assert state["worker_calls"] == 2
    assert len(state["sources"]) == 1  # 두 워커가 같은 출처를 찾아도 한 번만
    assert len(rec["router"].calls) == 2  # 라우터는 동시 실행이 끝난 뒤 한 번만 다시 판단


def test_worker_that_already_found_something_is_not_called_again():
    components, rec = make_components([Route(next="regulation", instruction="또 찾아")])
    graph = build_graph(components, checkpointer=InMemorySaver(), max_worker_calls=10)

    state = ask(graph, "법령 찾아줘")

    assert len(rec["worker"].calls) == 1  # 한 번에 찾았으면 다시 돌지 않는다 (속도)
    assert state["messages"][-1].text == "최종 답변 [1]"


def test_worker_that_found_nothing_is_retried_at_most_twice():
    empty = {"summary": "조회 결과 없음", "sources": []}
    components, rec = make_components(
        [Route(next="regulation", instruction="다르게 찾아")], worker_out=empty
    )
    graph = build_graph(components, checkpointer=InMemorySaver(), max_worker_calls=10)

    ask(graph, "법령 찾아줘")

    assert len(rec["worker"].calls) == 2


# ---------- 폴백 ----------


def test_worker_failure_is_recorded_and_flow_continues():
    components, rec = make_components(
        [Route(next="benefit"), Route(next="answer")],
        worker_out=RuntimeError("API 503"),
    )
    graph = build_graph(components, checkpointer=InMemorySaver())

    state = ask(graph, "혜택 알려줘")

    # 혜택을 찾을 때는 근거 법령(규정)도 같이 찾는다. 둘 다 실패해도 기록하고 답변까지 간다.
    assert sorted(f["worker"] for f in state["findings"]) == ["benefit", "regulation"]
    assert {f["summary"] for f in state["findings"]} == {"(조회 실패: API 503)"}
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


TOOL_CHOICES: list = []


class FakeToolModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        TOOL_CHOICES.append(kwargs.get("tool_choice"))
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
                AIMessage("이 요약 단계는 호출되지 않아야 한다"),
            ]
        )
    )
    worker = make_react_worker(model, [find_institutions], "기관 담당")

    out = run(worker.ainvoke({"messages": [("user", "예비군 어디서 확인해?")], "instruction": ""}))

    # 워커는 자기 지식으로 답하지 못하고 반드시 도구를 부른다.
    assert TOOL_CHOICES[-1] == "any"
    # 도구 결과를 받으면 LLM 요약 없이 끝내고, 도구 원문을 요약으로 쓴다.
    assert out["summary"].startswith('[find_institutions] {"institutions"')
    assert "병무청" in out["evidence"][0]
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
        async with open_agent(llm=FakeStructuredModel(messages=iter([])), state_db=None) as agent:
            return set(agent.get_graph().nodes)

    nodes = run(check())

    assert {"regulation", "benefit", "institution", "supervisor", "verify"} <= nodes


def test_conversation_and_profile_survive_restart(tmp_path):
    """SQLite에 저장한 대화와 프로필은 서버를 다시 띄워도 남는다."""
    from jeonyeok_helper.agents.runtime import _memory

    db = tmp_path / "state.sqlite"
    config = {"configurable": {"thread_id": "t1", "user_id": "u1"}}

    async def first_run():
        async with _memory(db) as (checkpointer, store):
            components, _ = make_components(
                [Route(next="answer")], profile=Profile(service_type="merit", region="대전")
            )
            graph = build_graph(components, checkpointer=checkpointer, store=store)
            await graph.ainvoke({"messages": [("user", "국가유공자예요")]}, config)

    async def after_restart():
        async with _memory(db) as (checkpointer, store):
            components, _ = make_components([Route(next="answer")])
            graph = build_graph(components, checkpointer=checkpointer, store=store)
            state = (await graph.aget_state(config)).values
            profile = await store.aget(("profiles",), "u1")
            return len(state["messages"]), profile.value

    run(first_run())
    assert run(after_restart()) == (2, {"service_type": "merit", "region": "대전"})


def test_verified_draft_is_kept_as_is():
    """검증에서 문제가 없으면 초안을 그대로 쓴다 (다시 쓰면 줄바꿈 같은 형식이 깨질 수 있다)."""
    components, _ = make_components(
        [Route(next="answer")],
        verifier=Verification(supported=True, answer="줄바꿈이 사라진 답변"),
    )
    graph = build_graph(components, checkpointer=InMemorySaver())

    assert ask(graph, "질문")["messages"][-1].text == "초안 답변 [1]"


def test_duplicate_sources_from_workers_are_merged():
    same = {"type": "institution", "title": "정부24", "url": "https://www.gov.kr"}
    components, _ = make_components(
        [Route(next="benefit"), Route(next="institution"), Route(next="answer")],
        worker_out={"summary": "정부24 안내", "sources": [same]},
    )
    graph = build_graph(components, checkpointer=InMemorySaver())

    assert ask(graph, "혜택 알려줘")["sources"] == [same]


def test_verifier_checks_against_tool_evidence_not_summaries():
    components, rec = make_components(
        [Route(next="benefit"), Route(next="answer")],
        worker_out={
            "summary": "청년수당 월 50만 원 (워커가 지어낸 내용)",
            "sources": [],
            "evidence": ['[search_benefits] {"benefits": [], "error": "서비스키 없음"}'],
        },
    )
    graph = build_graph(components, checkpointer=InMemorySaver())

    ask(graph, "혜택")

    sent = rec["verifier"].calls[0]
    assert "서비스키 없음" in sent["evidence"]
    assert "findings" not in sent  # 워커 요약은 검증 근거로 넘기지 않는다
    assert "서비스키 없음" in rec["responder"].calls[0]["evidence"]


def test_extract_evidence_keeps_raw_tool_output():
    from jeonyeok_helper.agents.workers import extract_evidence

    messages = [
        AIMessage("요약은 근거가 아니다"),
        tool_msg("find_institutions", {"institutions": [{"name": "병무청"}]}),
    ]
    assert extract_evidence(messages) == [
        '[find_institutions] {"institutions": [{"name": "병무청"}]}'
    ]


def test_profile_extraction_schema_stays_small():
    # 내 정보 화면의 자세한 항목(계급·목표·자격증 등)을 추출 항목에 넣으면 '병장'을 계급에만
    # 넣고 복무 형태를 비우거나 말하지 않은 값을 지어낸다 (평가 41/41 → 37/41).
    assert set(Profile.model_fields) == {
        "service_type", "service_years", "discharge_date", "age", "region", "merit_status",
    }  # fmt: skip


def test_discharge_status_tells_whether_user_already_left_the_army():
    from datetime import date

    from jeonyeok_helper.agents.prompts import discharge_status, format_profile

    today = date(2026, 10, 13)
    assert discharge_status("2020-04", today) == "2020-04 전역 (이미 전역함, 약 6년 전)"
    assert discharge_status("2027-03", today) == "2027-03 전역 예정 (아직 복무 중, 5개월 남음)"
    assert discharge_status("2026-08-15", today) == "2026-08 전역 (이미 전역함, 2개월 전)"
    assert discharge_status("2024", today) == "2024년 전역 (이미 전역함, 약 2년 전)"
    assert discharge_status("", today) == ""
    assert discharge_status("unknown", today) == ""
    assert "전역 상태=" in format_profile({"discharge_date": "2020-04"})
    assert "전역 상태" not in format_profile({"region": "서울"})


def test_reserve_status_counts_years_from_the_year_after_discharge():
    from datetime import date

    from jeonyeok_helper.agents.prompts import format_profile, reserve_status

    today = date(2026, 10, 13)
    assert reserve_status("2020-04", today).startswith("6년차, 올해 훈련 대상")
    assert reserve_status("2019-04", today).startswith("7년차, 훈련 면제")
    assert reserve_status("2017-01", today) == "편성 끝남 (2025년 12월 31일)"
    assert reserve_status("2026-03", today).startswith("올해 전역해 내년이 1년차")
    # 간부와 아직 복무 중인 병사에게는 붙이지 않는다
    assert "예비군=" in format_profile({"service_type": "conscript", "discharge_date": "2020-04"})
    assert "예비군=" not in format_profile(
        {"service_type": "short_term_officer", "discharge_date": "2020-04"}
    )
    assert "예비군=" not in format_profile(
        {"service_type": "conscript", "discharge_date": "2027-03"}
    )


def test_slow_worker_is_cut_off_and_answer_still_comes():
    import asyncio

    from langchain_core.runnables import RunnableLambda

    async def slow(_):
        await asyncio.sleep(5)
        return {"summary": "늦은 결과", "sources": []}

    components, _ = make_components([Route(next="regulation"), Route(next="answer")])
    components.workers["regulation"] = RunnableLambda(slow)
    graph = build_graph(components, checkpointer=InMemorySaver(), worker_timeout=0.2)

    state = ask(graph, "법령 찾아줘")

    assert state["messages"][-1].text  # 끊고도 답변까지 간다
