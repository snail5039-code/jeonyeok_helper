"""FastAPI 서버 (API 전용, 화면은 frontend/의 Next.js가 담당).

- GET  /health            : 상태와 키 설정 여부
- POST /chat              : 질문 → SSE 스트리밍 (진행 단계, 최종 답변)
- GET  /profile/{user_id} : 저장된 사용자 프로필
- POST /roadmap           : 프로필로 전역 로드맵(시기별 할 일) 만들기
- POST /feedback          : 답변 피드백(도움이 됐어요/아쉬워요) 저장
- GET  /feedback/summary  : 피드백 수

SSE 이벤트
    event: step      data: {"node": "regulation", "label": "관련 법령을 찾고 있어요"}
    event: delta     data: {"text": "..."}   # 답변 초안 조각 (이어 붙여서 바로 보여 준다)
    event: answer    data: {"text": "...", "sources": [...], "profile": {...}, "follow_ups": [...]}
                     # 근거 검증을 마친 최종 답변. 초안과 다를 수 있으니 화면은 이것으로 바꾼다.
    event: question  data: {"text": "...", "profile": {...}}   # 정보가 부족해 되물을 때
    event: error     data: {"message": "..."}
    event: done      data: {}
"""

import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from jeonyeok_helper import __version__
from jeonyeok_helper.agents.graph import PROFILE_NAMESPACE
from jeonyeok_helper.agents.roadmap import RoadmapProfile
from jeonyeok_helper.config import get_settings
from jeonyeok_helper.db import Database, Feedback

log = logging.getLogger(__name__)

STEP_LABELS = {
    "profile": "복무 정보를 정리하고 있어요",
    "regulation": "관련 법령을 찾고 있어요",
    "benefit": "받을 수 있는 혜택을 조회하고 있어요",
    "institution": "신청 기관을 찾고 있어요",
    "respond": "답변을 정리하고 있어요",
    "verify": "근거를 확인하고 있어요",
}

AgentFactory = Callable[[], AbstractAsyncContextManager[CompiledStateGraph]]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = None
    user_id: str | None = None


class FeedbackRequest(BaseModel):
    rating: Literal["up", "down"]
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=20000)
    comment: str | None = Field(default=None, max_length=1000)
    thread_id: str | None = Field(default=None, max_length=64)
    user_id: str | None = Field(default=None, max_length=64)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


RoadmapBuilder = Callable[[RoadmapProfile], Awaitable[dict]]


def _default_runtime() -> tuple[AgentFactory, RoadmapBuilder]:
    """채팅 에이전트와 로드맵이 같은 도구 데이터(정책 목록 캐시 등)를 쓰도록 묶는다."""
    from jeonyeok_helper.agents.roadmap import build_roadmap, make_organizer
    from jeonyeok_helper.agents.runtime import open_agent
    from jeonyeok_helper.benefits.mcp_server import Services

    services = Services()
    organizer = None

    async def roadmap(profile: RoadmapProfile) -> dict:
        nonlocal organizer
        if organizer is None:
            from jeonyeok_helper.llm import get_chat_model

            s = get_settings()
            organizer = make_organizer(
                get_chat_model(temperature=0.1, thinking_budget=s.gemini_thinking_budget)
            )
        return await build_roadmap(services, organizer, profile)

    return (lambda: open_agent(services=services)), roadmap


def create_app(
    agent_factory: AgentFactory | None = None,
    db_url: str | None = None,
    roadmap_builder: RoadmapBuilder | None = None,
) -> FastAPI:
    if agent_factory is None:
        agent_factory, default_roadmap = _default_runtime()
        roadmap_builder = roadmap_builder or default_roadmap

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.db = Database(db_url or get_settings().app_db_url)
        app.state.db.migrate()  # 최신 스키마까지 자동으로
        app.state.roadmap = roadmap_builder
        async with AsyncExitStack() as stack:
            try:
                app.state.agent = await stack.enter_async_context(agent_factory())
                app.state.agent_error = None
            except RuntimeError as e:  # API 키 누락 등: 서버는 띄우고 /chat에서 안내
                log.warning("에이전트를 시작하지 못했습니다: %s", e)
                app.state.agent, app.state.agent_error = None, str(e)
            yield

    app = FastAPI(title="전역도우미", version=__version__, lifespan=lifespan)

    @app.get("/health")
    def health(request: Request) -> dict:
        s = get_settings()
        return {
            "status": "ok",
            "version": __version__,
            "agent_ready": getattr(request.app.state, "agent", None) is not None,
            # 키 값은 노출하지 않고 설정 여부만 알려준다.
            "keys": {
                "gemini": bool(s.google_api_key),
                "law_api": bool(s.law_api_oc),
                "data_go_kr": bool(s.data_go_kr_service_key),
            },
        }

    @app.post("/chat")
    async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
        agent: CompiledStateGraph | None = request.app.state.agent
        if agent is None:
            raise HTTPException(503, request.app.state.agent_error or "에이전트 준비 중")

        thread_id = req.thread_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        if req.user_id:
            config["configurable"]["user_id"] = req.user_id

        async def events() -> AsyncIterator[str]:
            yield _sse("thread", {"thread_id": thread_id})
            try:
                async for mode, chunk in agent.astream(
                    {"messages": [("user", req.message)]},
                    config,
                    stream_mode=["updates", "messages"],
                ):
                    if mode == "messages":
                        # 답변 초안을 만들어지는 대로 보낸다 (다른 노드의 LLM 출력은 제외)
                        token, meta = chunk
                        if meta.get("langgraph_node") == "respond" and (text := token.text):
                            yield _sse("delta", {"text": text})
                        continue
                    for node in chunk:
                        if label := STEP_LABELS.get(node):
                            yield _sse("step", {"node": node, "label": label})
                state = (await agent.aget_state(config)).values
                last = state["messages"][-1]
                payload = {"text": last.text, "profile": state.get("profile", {})}
                if state.get("draft"):
                    yield _sse(
                        "answer",
                        {
                            **payload,
                            "sources": state.get("sources", []),
                            "follow_ups": state.get("follow_ups", []),
                        },
                    )
                else:  # respond를 거치지 않았다면 되묻기
                    yield _sse("question", payload)
            except Exception:
                log.exception("대화 처리 실패")
                message = "답변 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요."
                yield _sse("error", {"message": message})
            yield _sse("done", {})

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/roadmap")
    async def roadmap(profile: RoadmapProfile, request: Request) -> dict:
        """프로필 하나로 시기별 할 일 목록(전역 로드맵)을 한 번에 만든다."""
        if request.app.state.agent is None or request.app.state.roadmap is None:
            raise HTTPException(503, request.app.state.agent_error or "로드맵을 만들 수 없어요")
        try:
            return await request.app.state.roadmap(profile)
        except Exception:
            log.exception("로드맵 생성 실패")
            raise HTTPException(
                500, "로드맵을 만들지 못했어요. 잠시 후 다시 시도해 주세요."
            ) from None

    @app.post("/feedback", status_code=201)
    def feedback(req: FeedbackRequest, request: Request) -> dict:
        with request.app.state.db.session() as session:
            row = Feedback(**req.model_dump())
            session.add(row)
            session.flush()
            return {"id": row.id}

    @app.get("/feedback/summary")
    def feedback_summary(request: Request) -> dict:
        with request.app.state.db.session() as session:
            counts = dict(
                session.execute(
                    select(Feedback.rating, func.count()).group_by(Feedback.rating)
                ).all()
            )
        return {"up": counts.get("up", 0), "down": counts.get("down", 0)}

    @app.get("/profile/{user_id}")
    async def profile(user_id: str, request: Request) -> dict:
        agent: CompiledStateGraph | None = request.app.state.agent
        if agent is None or agent.store is None:
            return {"profile": {}}
        item = await agent.store.aget(PROFILE_NAMESPACE, user_id)
        return {"profile": item.value if item else {}}

    return app


app = create_app()


def run() -> None:
    uvicorn.run("jeonyeok_helper.api.main:app", host="127.0.0.1", port=8000, reload=True)
