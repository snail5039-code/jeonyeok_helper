"""LangGraph 슈퍼바이저 그래프.

start → profile → coach ─┬→ END  (talk: 인사·진행 보고·다음 할 일, 검색 없이 짧게)
                         └→ supervisor ─┬→ regulation / benefit / institution → supervisor
                                        ├→ ask_user → END   (정보가 부족하면 되묻기)
                                        └→ respond → verify → guide → END
                                           (답변 → 근거 검증 → 길잡이 한마디·할 일 제안)

coach·guide는 사용자를 로드맵을 따라 안내하는 길잡이 (agents/guide.py). 없으면 검색 답변만 한다.

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

from jeonyeok_helper.agents import guide as guide_rules
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
MAX_CALLS_PER_WORKER = 2


@dataclass
class Components:
    profile_extractor: Runnable  # {messages, profile} → Profile
    router: Runnable  # {messages, profile, findings, worker_calls, max_worker_calls} → Route
    workers: dict[str, Runnable]  # {messages, instruction, profile} → {summary, sources}
    responder: Runnable  # {messages, profile, findings, sources} → str
    verifier: Runnable  # {draft, findings, sources} → Verification
    coach: Runnable | None = None  # {messages, profile, missing, journey} → CoachDecision
    guide: Runnable | None = None  # {question, answer, sources, ...} → GuideDraft


def _user_id(config: RunnableConfig) -> str | None:
    return (config.get("configurable") or {}).get("user_id")


def _journey(config: RunnableConfig) -> list[dict]:
    """API가 넘겨 준 사용자의 로드맵 할 일 목록 (그래프는 DB를 모른다)."""
    return (config.get("configurable") or {}).get("journey") or []


def _last_question(state: AgentState) -> str:
    return next((m.text for m in reversed(state["messages"]) if m.type == "human"), "")


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
            "worker_calls": None,
            "also": [],
            "follow_ups": [],
            "draft": "",
            "guide": {},
        }
        # 같은 사용자면 장기 메모리의 프로필을 매 질문 불러온다 ('내 정보' 화면에서 고친 값이
        # 대화 중에도 바로 반영되도록).
        if store is not None and (uid := _user_id(config)):
            if item := await store.aget(PROFILE_NAMESPACE, uid):
                update["profile"] = item.value
        return update

    async def profile(state: AgentState, config: RunnableConfig, *, store: BaseStore | None = None):
        # 버튼(했어요·나중에)으로 보낸 말에는 복무 정보가 없다. 할 일 이름의 '제대군인' 같은 말을
        # 복무 형태로 잘못 읽지 않도록 추출하지 않는다.
        if (config.get("configurable") or {}).get("action"):
            return {}
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

    async def coach(state: AgentState, config: RunnableConfig):
        """이번 메시지를 검색 없이 말로 답할지(talk), 자료를 찾아 답할지(research) 정한다."""
        # 버튼 동작(했어요·나중에)이 아닌데 신청 방법·자격 등을 물으면 바로 자료를 찾는다
        action = (config.get("configurable") or {}).get("action")
        question = _last_question(state)
        turns = sum(getattr(m, "type", "") == "human" for m in state["messages"])
        # 무엇을 묻는지 모르는 '그거 신청 어디서 해요?'는 검색하지 말고 길잡이가 되묻는다
        vague = guide_rules.is_vague_first_turn(question, turns)
        if c.coach is None or (not action and guide_rules.needs_research(question) and not vague):
            return {"guide": {"mode": "research"}}
        items = _journey(config)
        missing = guide_rules.missing_field(state.get("profile"))
        nxt = guide_rules.next_item(items, state.get("skipped"))
        try:
            decision = await c.coach.ainvoke(
                {
                    "messages": state["messages"],
                    "profile": format_profile(state.get("profile")),
                    "missing": guide_rules.FIELD_LABELS.get(missing, "(없음)"),
                    "journey": guide_rules.format_journey(items, nxt),
                }
            )
        except Exception:
            log.warning("길잡이 판단 실패, 자료를 찾아 답합니다.", exc_info=True)
            return {"guide": {"mode": "research"}}
        if decision.mode != "talk" or not decision.say.strip():
            return {"guide": {"mode": "research"}}
        say = guide_rules.with_question(decision.say, missing)
        # '실수로 했어요 눌렀어' → 그 할 일을 미완료로 되돌리고(API가 저장) 바로 다시 권한다
        reopened = guide_rules.find_done(items, decision.reopen)
        if reopened:
            nxt = {**reopened, "done": False}
        # 길잡이는 늘 다음 걸음을 이끈다: 물을 것이 없으면 다음 할 일을 버튼과 함께 권한다
        step = nxt if (nxt and not missing) else None
        if step:
            say = guide_rules.with_next_step(say, step)
        # 버튼은 규칙으로: 빠진 정보가 있으면 그걸 고르는 버튼, 아니면 다음 할 일 버튼
        if missing:
            replies = guide_rules.ask_replies(missing)
        elif step:
            replies = guide_rules.step_replies(step)
        else:
            replies = []
        return {
            "messages": [AIMessage(say, name="jeonyeok_helper")],
            "guide": {
                "mode": "talk",
                "say": say,
                "ask": missing,
                "step": step,
                "quick_replies": replies,
                "suggest": [],
                "reopen": reopened["id"] if reopened else None,
            },
        }

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
        if route.next not in WORKERS:
            return {"next": "answer"}

        # 규정·혜택처럼 서로 기다릴 필요 없는 워커는 같이 돌린다 (also).
        # 같은 워커를 계속 부르며 시간만 쓰는 경우가 있어, 한 질문에서 워커당 2번까지만 허용한다.
        findings = state.get("findings", [])
        wanted = [route.next, *route.also]
        # 혜택 답변에는 근거 법령이 거의 항상 필요하다. 라우터가 also를 빠뜨려도 같이 돌려
        # 혜택 → 규정을 차례로 기다리는 일을 막는다.
        if route.next == "benefit" and not findings:
            wanted.append("regulation")
        batch: list[str] = []
        for name in wanted:
            used = sum(f["worker"] == name for f in findings)
            if name in c.workers and name not in batch and used < MAX_CALLS_PER_WORKER:
                batch.append(name)
        batch = batch[: max_worker_calls - calls]
        if not batch:
            return {"next": "answer"}
        # 지시는 next 워커에게만 해당한다. also 워커는 마지막 질문을 그대로 처리한다.
        instruction = route.instruction if batch[0] == route.next else ""
        return {"next": batch[0], "also": batch[1:], "instruction": instruction}

    def make_worker_node(name: str):
        async def worker(state: AgentState):
            instruction = state.get("instruction", "") if state.get("next") == name else ""
            try:
                out = await c.workers[name].ainvoke(
                    {
                        "messages": state["messages"],
                        "instruction": instruction,
                        "profile": state.get("profile", {}),
                    }
                )
            except Exception as e:  # 폴백: 실패를 기록하고 다른 경로로 계속 진행
                log.warning("%s 워커 실패", name, exc_info=True)
                out = {"summary": f"(조회 실패: {e})", "sources": []}
            # 출처 중복 제거와 호출 횟수 합산은 상태의 reducer가 한다 (동시 실행 대비).
            return {
                "findings": [{"worker": name, "summary": out.get("summary", "")}],
                "sources": out.get("sources", []),
                "evidence": out.get("evidence", []),
                "worker_calls": 1,
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
        follow_ups: list[str] = []
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
            follow_ups = [q.strip() for q in checked.follow_ups if q.strip()][:3]
        except Exception:
            log.warning("근거 검증 실패, 초안을 그대로 씁니다.", exc_info=True)
            answer = draft
        return {
            "messages": [AIMessage(answer, name="jeonyeok_helper")],
            "follow_ups": follow_ups,
        }

    async def guide(state: AgentState, config: RunnableConfig):
        """답변 위에 보일 한마디와 로드맵에 담을 할 일 제안. 실패해도 답변은 그대로."""
        missing = guide_rules.missing_field(state.get("profile"))
        out = {
            "mode": "research",
            "say": "",
            "ask": missing,
            "step": None,
            "quick_replies": guide_rules.ask_replies(missing) if missing else [],
            "suggest": [],
        }
        if c.guide is None:
            return {"guide": out}
        sources = state.get("sources") or []
        answer = state["messages"][-1].text
        existing = [i["title"] for i in _journey(config)]
        try:
            draft = await c.guide.ainvoke(
                {
                    "question": _last_question(state),
                    "answer": answer,
                    "sources": format_sources(sources),
                    "profile": format_profile(state.get("profile")),
                    "missing": guide_rules.FIELD_LABELS.get(missing, "(없음)"),
                    "existing": ", ".join(existing) or "(없음)",
                }
            )
        except Exception:
            log.warning("길잡이 한마디 실패", exc_info=True)
            return {"guide": out}
        out["say"] = guide_rules.with_question(draft.say, missing) if draft.say.strip() else ""
        if sources:
            out["suggest"] = guide_rules.pick_items(
                draft, answer=answer, sources=sources, existing=existing,
                profile=state.get("profile"),
            )  # fmt: skip
        return {"guide": out}

    g = StateGraph(AgentState)
    g.add_node("start", start)
    g.add_node("profile", profile)
    g.add_node("coach", coach)
    g.add_node("supervisor", supervisor)
    for name in WORKERS:
        if name in c.workers:
            g.add_node(name, make_worker_node(name))
            g.add_edge(name, "supervisor")
    g.add_node("ask_user", ask_user)
    g.add_node("respond", respond)
    g.add_node("verify", verify)
    g.add_node("guide", guide)

    g.add_edge(START, "start")
    g.add_edge("start", "profile")
    g.add_edge("profile", "coach")
    g.add_conditional_edges(
        "coach",
        lambda s: END if s.get("guide", {}).get("mode") == "talk" else "supervisor",
        [END, "supervisor"],
    )

    def after_supervisor(s: AgentState) -> str | list[str]:
        if s["next"] == "answer":
            return "respond"
        if s["next"] == "ask_user":
            return "ask_user"
        return [s["next"], *s.get("also", [])]  # 목록이면 동시에 실행

    g.add_conditional_edges("supervisor", after_supervisor, [*c.workers, "ask_user", "respond"])
    g.add_edge("ask_user", END)
    g.add_edge("respond", "verify")
    g.add_edge("verify", "guide")
    g.add_edge("guide", END)

    return g.compile(checkpointer=checkpointer, store=store)
