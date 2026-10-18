"""LangGraph 슈퍼바이저 그래프.

start → guard ─┬→ END  (입력 가드레일: 프롬프트 인젝션은 막고, 개인정보는 가린 뒤 진행)
               └→ profile → coach ─┬→ END  (talk: 인사·진행 보고·다음 할 일, 검색 없이 짧게)
                                   └→ supervisor ─┬→ regulation / benefit / institution → supervisor
                                                  ├→ ask_user ⏸ → guard → profile → ...
                                                  │  (정보가 부족하면 interrupt로 멈춰 되묻고,
                                                  │   답이 오면 찾은 것을 그대로 두고 이어서 진행)
                                                  └→ respond → verify + guide → END
                                                     (답변 → 근거 검증·길잡이 한마디·할 일 제안)

coach·guide는 사용자를 로드맵을 따라 안내하는 길잡이 (agents/guide.py). 없으면 검색 답변만 한다.

각 단계의 LLM 호출은 Components로 주입받는다. 그래프는 흐름만 책임진다.
"""

# 주의: `from __future__ import annotations`를 쓰면 LangGraph가 노드의 `store` 인자를
# 알아보지 못해 장기 메모리가 주입되지 않는다. 이 파일에서는 쓰지 않는다.

import asyncio
import logging
import re
from dataclasses import dataclass

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, trim_messages
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import NodeError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from langgraph.types import Command, RetryPolicy, TimeoutPolicy, interrupt

from jeonyeok_helper.agents import guardrails
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


def apply_edits(draft: str, edits) -> str:
    """검증이 알려 준 부분만 바꾼다. 초안에 없는 문장은 건너뛴다(모델이 살짝 다르게 옮긴 경우)."""
    text = draft
    for e in edits:
        if e.find and e.find in text:
            text = text.replace(e.find, e.replace, 1)
        elif e.find:
            log.warning("검증 수정 위치를 초안에서 찾지 못함: %s", e.find[:60])
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# 잠깐 끊긴 연결처럼 다시 시도하면 될 수 있는 오류
TRANSIENT_ERRORS = (ConnectionError, OSError)
RESPOND_FAILED = "답변을 만드는 데 시간이 너무 오래 걸렸어요. 잠시 뒤 다시 물어봐 주세요."

MAX_CALLS_PER_WORKER = 2
# 같은 워커를 다시 부르는 것은 앞에서 아무것도 못 찾았을 때만 (이미 찾았는데 한 번 더 돌면
# 질문 하나에 8~10초가 더 걸렸다: '15년 복무, 부산' 질문이 혜택·규정을 두 번씩 돌았음)
EMPTY_FINDING = re.compile(r"조회 결과 없음|조회 실패|조회 시간 초과|찾지 못|결과가 없")


@dataclass
class Components:
    profile_extractor: Runnable  # {messages, profile} → Profile
    router: Runnable  # {messages, profile, findings, worker_calls, max_worker_calls} → Route
    workers: dict[str, Runnable]  # {messages, instruction, profile} → {summary, sources}
    responder: Runnable  # {messages, profile, findings, sources} → str
    verifier: Runnable  # {draft, findings, sources} → Verification
    coach: Runnable | None = None  # {messages, profile, missing, journey} → CoachDecision
    guide: Runnable | None = None  # {question, answer, sources, ...} → GuideDraft


# LLM에 넘기는 대화 기록의 상한 (대략의 토큰 수). 대화가 길어져도 매 질문의 속도·비용이
# 늘지 않게 최근 대화만 넘긴다. 복무 정보는 프로필로 따로 쌓이므로 앞부분을 잘라도 잃지 않는다.
HISTORY_MAX_TOKENS = 4000


def recent(messages: list[AnyMessage]) -> list[AnyMessage]:
    """최근 대화만 남긴다. 사용자 말로 시작하게 잘라 답변만 덩그러니 남지 않게 한다."""
    trimmed = trim_messages(
        messages,
        strategy="last",
        token_counter=count_tokens_approximately,
        max_tokens=HISTORY_MAX_TOKENS,
        start_on="human",
        allow_partial=False,
    )
    # 마지막 질문 하나가 상한보다 길어도 질문은 꼭 넘긴다
    return trimmed or messages[-1:]


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
    worker_timeout: float = 45,
    respond_timeout: float = 90,
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

    async def guard(state: AgentState):
        """입력 가드레일: 인젝션은 여기서 끝내고, 개인정보는 가린 뒤 다음 단계로 넘긴다."""
        last = state["messages"][-1]
        if getattr(last, "type", "") != "human":
            return {}
        if guardrails.is_injection(last.text):
            log.info("입력 가드레일: 인젝션으로 보여 막음")
            say = guardrails.BLOCKED_REPLY
            return {
                "messages": [AIMessage(say, name="jeonyeok_helper")],
                "guide": {"mode": "talk", "say": say, "ask": None, "step": None,
                          "quick_replies": [], "suggest": [], "blocked": True},
            }  # fmt: skip
        masked, found = guardrails.mask_pii(last.text)
        if found:
            # 같은 id로 돌려주면 대화 기록의 원래 메시지가 가린 글로 바뀐다
            log.info("입력 가드레일: %s 가림", ", ".join(found))
            return {"messages": [HumanMessage(masked, id=last.id)]}
        return {}

    async def profile(state: AgentState, config: RunnableConfig, *, store: BaseStore | None = None):
        # 버튼(했어요·나중에)으로 보낸 말에는 복무 정보가 없다. 할 일 이름의 '제대군인' 같은 말을
        # 복무 형태로 잘못 읽지 않도록 추출하지 않는다.
        if (config.get("configurable") or {}).get("action"):
            return {}
        try:
            extracted: Profile = await c.profile_extractor.ainvoke(
                {
                    "messages": recent(state["messages"]),
                    "profile": format_profile(state.get("profile")),
                }
            )
        except Exception:
            log.warning("프로필 추출 실패, 기존 프로필로 진행합니다.", exc_info=True)
            return {}
        new = guide_rules.repair_profile(
            "\n".join(m.text for m in state["messages"] if getattr(m, "type", "") == "human"),
            extracted.model_dump(exclude_none=True),
        )
        if store is not None and (uid := _user_id(config)):
            await store.aput(PROFILE_NAMESPACE, uid, merge_profile(state.get("profile"), new))
        return {"profile": new}

    async def coach(state: AgentState, config: RunnableConfig):
        """이번 메시지를 검색 없이 말로 답할지(talk), 자료를 찾아 답할지(research) 정한다."""
        # 버튼 동작(했어요·나중에)이 아닌데 신청 방법·자격 등을 물으면 바로 자료를 찾는다
        if (state.get("guide") or {}).get("resumed"):
            return {"guide": {"mode": "research"}}
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
                    "messages": recent(state["messages"]),
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
        replies = guide_rules.kit_replies(_last_question(state)) + replies
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
        # 워커 두 곳 이상이 이미 무언가를 찾았으면 라우터에게 다시 묻지 않고 답한다
        # (거의 항상 'answer'를 고르는 데 1초를 썼다)
        found = {
            f["worker"] for f in state.get("findings", []) if not EMPTY_FINDING.search(f["summary"])
        }
        if len(found) >= 2:
            return {"next": "answer"}
        try:
            route: Route = await c.router.ainvoke(
                {
                    "messages": recent(state["messages"]),
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
            mine = [f for f in findings if f["worker"] == name]
            found_before = any(not EMPTY_FINDING.search(f["summary"]) for f in mine)
            if (
                name in c.workers
                and name not in batch
                and len(mine) < MAX_CALLS_PER_WORKER
                and not found_before
            ):
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
            # 워커는 규정·혜택이 동시에 돈다. LangGraph의 노드 error_handler는 병렬로 도는 노드가
            # 실패하면 동작하지 않아(1.2.16에서 확인) 시간 제한·실패 기록은 노드 안에서 한다.
            # 잠깐 끊긴 연결은 워커 Runnable의 with_retry가 한 번 더 시도한다.
            try:
                # 모델 응답이 가끔 1분 넘게 늦어져 화면이 계속 도는 일이 있었다 (같은 질문이
                # 평소 30초, 한 번은 101초). 상한을 넘기면 끊고 다른 워커가 찾은 것으로 답한다.
                out = await asyncio.wait_for(
                    workers[name].ainvoke(
                        {
                            "messages": recent(state["messages"]),
                            "instruction": instruction,
                            "profile": state.get("profile", {}),
                        }
                    ),
                    timeout=worker_timeout,
                )
            except TimeoutError:
                log.warning("%s 워커 %s초 초과, 찾은 것까지로 답합니다", name, worker_timeout)
                out = {"summary": "(조회 시간 초과)", "sources": []}
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

    # 네트워크가 잠깐 끊긴 오류만 한 번 더 시도한다
    workers = {
        name: w.with_retry(retry_if_exception_type=TRANSIENT_ERRORS, stop_after_attempt=2)
        for name, w in c.workers.items()
    }

    async def ask_user(state: AgentState):
        """Human-in-the-loop: 정보가 모자라면 그래프를 멈추고(interrupt) 사용자의 답을 기다린다.
        답이 오면(Command(resume=답)) 여기서부터 이어서, 지금까지 찾은 것은 그대로 두고 진행한다."""
        question = state.get("instruction") or "복무 형태(병사·간부)와 복무 기간을 알려주시겠어요?"
        reply = interrupt({"question": question})
        return {
            "messages": [
                AIMessage(question, name="jeonyeok_helper"),
                HumanMessage(str(reply)),
            ],
            # 되물은 것에 대한 답이므로 길잡이 대화로 빠지지 않고 자료 찾기를 이어 간다
            "guide": {"mode": "research", "resumed": True},
        }

    async def respond(state: AgentState):
        draft = await c.responder.ainvoke(
            {
                "messages": recent(state["messages"]),
                "profile": format_profile(state.get("profile")),
                "findings": format_findings(state.get("findings")),
                "sources": format_sources(state.get("sources")),
                "evidence": format_evidence(state.get("evidence")),
            }
        )
        return {"draft": str(getattr(draft, "text", draft))}

    def respond_failed(state: AgentState, error: NodeError) -> Command:
        """답변 작성이 시간 초과나 오류로 끝내 실패하면 화면이 계속 돌지 않게 안내하고 끝낸다."""
        log.warning("답변 작성 실패: %r", error.error)
        return Command(
            update={"messages": [AIMessage(RESPOND_FAILED, name="jeonyeok_helper")], "draft": ""},
            goto=END,
        )

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
            # 문제가 없으면 초안을 그대로 쓴다. 고칠 데가 있으면 그 부분만 바꾼다
            # (답 전체를 다시 쓰게 하면 7초쯤 더 걸리고 줄바꿈 같은 형식도 깨질 수 있다).
            if checked.supported:
                answer = draft
            elif checked.edits:
                # 고친 결과가 비면(답 전체를 지우라는 수정) 빈 답 대신 초안을 쓴다
                answer = apply_edits(draft, checked.edits) or draft
            else:
                answer = checked.answer or draft
            follow_ups = [q.strip() for q in checked.follow_ups if q.strip()][:3]
        except Exception:
            log.warning("근거 검증 실패, 초안을 그대로 씁니다.", exc_info=True)
            answer = draft
        # 출력 가드레일: 개인정보 형식이 섞였으면 가린다
        answer, found = guardrails.mask_pii(answer)
        if found:
            log.warning("출력 가드레일: 답변의 %s 가림", ", ".join(found))
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
            "quick_replies": guide_rules.kit_replies(_last_question(state))
            + (guide_rules.ask_replies(missing) if missing else []),
            "suggest": [],
        }
        if c.guide is None:
            return {"guide": out}
        sources = state.get("sources") or []
        # 검증과 동시에 돌아서 초안을 본다 (검증은 문장 몇 개만 고친다)
        answer = state.get("draft") or state["messages"][-1].text
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
    g.add_node("guard", guard)
    g.add_node("profile", profile)
    g.add_node("coach", coach)
    g.add_node("supervisor", supervisor)
    for name in WORKERS:
        if name in c.workers:
            g.add_node(name, make_worker_node(name))
            g.add_edge(name, "supervisor")
    g.add_node("ask_user", ask_user)
    # 답변 작성은 혼자 도는 노드라 LangGraph 노드 정책으로 시간 제한·재시도·실패 처리를 한다.
    # 시간 초과는 다시 기다리면 너무 오래 걸려 재시도하지 않고, 끊긴 연결만 한 번 더 시도한다.
    g.add_node(
        "respond",
        respond,
        timeout=TimeoutPolicy(run_timeout=respond_timeout),
        retry_policy=RetryPolicy(max_attempts=2, initial_interval=0.5, retry_on=TRANSIENT_ERRORS),
        error_handler=respond_failed,
    )
    g.add_node("verify", verify)
    g.add_node("guide", guide)

    g.add_edge(START, "start")
    g.add_edge("start", "guard")
    g.add_conditional_edges(
        "guard",
        lambda s: END if s.get("guide", {}).get("blocked") else "profile",
        [END, "profile"],
    )
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
    # 되묻기 답을 받으면 입력 가드레일과 프로필 추출부터 다시 거친다
    g.add_edge("ask_user", "guard")
    # 검증과 말풍선은 서로 기다릴 필요가 없어 같이 돌린다 (약 2~3초 절약)
    g.add_edge("respond", "verify")
    g.add_edge("respond", "guide")
    g.add_edge("verify", END)
    g.add_edge("guide", END)

    return g.compile(checkpointer=checkpointer, store=store)
