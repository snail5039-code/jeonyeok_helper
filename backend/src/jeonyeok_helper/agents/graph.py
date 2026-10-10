"""LangGraph 슈퍼바이저 그래프.

start → profile → supervisor ─┬→ regulation / benefit / institution → supervisor (반복)
                              ├→ ask_user → END            (정보가 부족하면 되묻기)
                              └→ respond → verify → END    (답변 초안 → 근거 검증)

각 단계의 LLM 호출은 Components로 주입받는다. 그래프는 흐름만 책임진다.
"""

# 주의: `from __future__ import annotations`를 쓰면 LangGraph가 노드의 `store` 인자를
# 알아보지 못해 장기 메모리가 주입되지 않는다. 이 파일에서는 쓰지 않는다.

import logging
from dataclasses import dataclass

from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from jeonyeok_helper.agents.prompts import (
    format_evidence,
    format_findings,
    format_profile,
    format_sources,
)
from jeonyeok_helper.agents.state import (
    WORKERS,
    AgentState,
    Profile,
    Route,
    Verification,
    merge_profile,
)

log = logging.getLogger(__name__)

PROFILE_NAMESPACE = ("profiles",)


@dataclass
class Components:
    profile_extractor: Runnable  # {messages, profile} → Profile
    router: Runnable  # {messages, profile, findings, worker_calls, max_worker_calls} → Route
    workers: dict[str, Runnable]  # {messages, instruction, profile} → {summary, sources}
    responder: Runnable  # {messages, profile, findings, sources} → str
    verifier: Runnable  # {draft, findings, sources} → Verification


def _user_id(config: RunnableConfig) -> str | None:
    return (config.get("configurable") or {}).get("user_id")


def build_graph(
    components: Components,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
    max_worker_calls: int = 4,
) -> CompiledStateGraph:
    c = components

    async def start(state: AgentState, config: RunnableConfig, *, store: BaseStore | None = None):
        update = {
            "findings": None,
            "sources": None,
            "evidence": None,
            "worker_calls": 0,
            "draft": "",
        }
        # 새 대화라도 같은 사용자면 장기 메모리의 프로필을 불러온다.
        if store is not None and (uid := _user_id(config)) and not state.get("profile"):
            if item := await store.aget(PROFILE_NAMESPACE, uid):
                update["profile"] = item.value
        return update

    async def profile(state: AgentState, config: RunnableConfig, *, store: BaseStore | None = None):
        try:
            extracted: Profile = await c.profile_extractor.ainvoke(
                {"messages": state["messages"], "profile": format_profile(state.get("profile"))}
            )
        except Exception:
            log.warning("프로필 추출 실패, 기존 프로필로 진행합니다.", exc_info=True)
            return {}
        new = extracted.model_dump(exclude_none=True)
        if store is not None and (uid := _user_id(config)):
            await store.aput(PROFILE_NAMESPACE, uid, merge_profile(state.get("profile"), new))
        return {"profile": new}

    async def supervisor(state: AgentState):
        calls = state.get("worker_calls", 0)
        if calls >= max_worker_calls:
            return {"next": "answer"}
        try:
            route: Route = await c.router.ainvoke(
                {
                    "messages": state["messages"],
                    "profile": format_profile(state.get("profile")),
                    "findings": format_findings(state.get("findings")),
                    "worker_calls": calls,
                    "max_worker_calls": max_worker_calls,
                }
            )
        except Exception:
            log.warning("라우팅 실패, 지금까지 찾은 내용으로 답변합니다.", exc_info=True)
            return {"next": "answer"}
        if route.next == "ask_user":
            return {"next": "ask_user", "instruction": route.question}
        if route.next in WORKERS and route.next not in c.workers:
            return {"next": "answer"}
        return {"next": route.next, "instruction": route.instruction}

    def make_worker_node(name: str):
        async def worker(state: AgentState):
            try:
                out = await c.workers[name].ainvoke(
                    {
                        "messages": state["messages"],
                        "instruction": state.get("instruction", ""),
                        "profile": state.get("profile", {}),
                    }
                )
            except Exception as e:  # 폴백: 실패를 기록하고 다른 경로로 계속 진행
                log.warning("%s 워커 실패", name, exc_info=True)
                out = {"summary": f"(조회 실패: {e})", "sources": []}
            # 여러 워커가 같은 기관을 찾는 경우가 많아서, 이미 있는 출처는 빼고 더한다.
            seen = {(s["type"], s["title"], s.get("url", "")) for s in state.get("sources", [])}
            new_sources = []
            for s in out.get("sources", []):
                key = (s.get("type"), s.get("title"), s.get("url", ""))
                if key not in seen:
                    seen.add(key)
                    new_sources.append(s)
            return {
                "findings": [{"worker": name, "summary": out.get("summary", "")}],
                "sources": new_sources,
                "evidence": out.get("evidence", []),
                "worker_calls": state.get("worker_calls", 0) + 1,
            }

        return worker

    async def ask_user(state: AgentState):
        question = state.get("instruction") or "복무 형태(병사·간부)와 복무 기간을 알려주시겠어요?"
        return {"messages": [AIMessage(question, name="jeonyeok_helper")]}

    async def respond(state: AgentState):
        draft = await c.responder.ainvoke(
            {
                "messages": state["messages"],
                "profile": format_profile(state.get("profile")),
                "findings": format_findings(state.get("findings")),
                "sources": format_sources(state.get("sources")),
                "evidence": format_evidence(state.get("evidence")),
            }
        )
        return {"draft": str(getattr(draft, "text", draft))}

    async def verify(state: AgentState):
        draft = state.get("draft", "")
        try:
            checked: Verification = await c.verifier.ainvoke(
                {
                    # 워커 요약은 넘기지 않는다: 요약에 섞인 지식을 근거로 믿으면 안 된다.
                    "draft": draft,
                    "sources": format_sources(state.get("sources")),
                    "evidence": format_evidence(state.get("evidence")),
                }
            )
            # 문제가 없으면 초안을 그대로 쓴다. 다시 쓰게 하면 줄바꿈 같은 형식이 깨질 수 있다.
            answer = draft if checked.supported else (checked.answer or draft)
        except Exception:
            log.warning("근거 검증 실패, 초안을 그대로 씁니다.", exc_info=True)
            answer = draft
        return {"messages": [AIMessage(answer, name="jeonyeok_helper")]}

    g = StateGraph(AgentState)
    g.add_node("start", start)
    g.add_node("profile", profile)
    g.add_node("supervisor", supervisor)
    for name in WORKERS:
        if name in c.workers:
            g.add_node(name, make_worker_node(name))
            g.add_edge(name, "supervisor")
    g.add_node("ask_user", ask_user)
    g.add_node("respond", respond)
    g.add_node("verify", verify)

    g.add_edge(START, "start")
    g.add_edge("start", "profile")
    g.add_edge("profile", "supervisor")
    g.add_conditional_edges(
        "supervisor",
        lambda s: "respond" if s["next"] == "answer" else s["next"],
        [*c.workers, "ask_user", "respond"],
    )
    g.add_edge("ask_user", END)
    g.add_edge("respond", "verify")
    g.add_edge("verify", END)

    return g.compile(checkpointer=checkpointer, store=store)
