"""FastAPI 서버 (API 전용, 화면은 frontend/의 Next.js가 담당).

- GET  /health                          : 상태와 키 설정 여부
- POST /chat                            : 질문 → SSE (진행 단계, 답변, 길잡이 한마디·버튼)
- GET  /profile/{user_id}               : 저장된 사용자 프로필 ('내 정보' + 대화에서 알아낸 것)
- PUT  /profile/{user_id}               : '내 정보' 화면에서 고친 프로필 저장
- GET  /journey/{user_id}               : 전역 로드맵 할 일 목록
- POST /journey/{user_id}/generate      : 프로필로 로드맵을 한 번에 채우기
- POST /journey/{user_id}/items         : 길잡이가 제안한 할 일 중 고른 것 담기
- PATCH  /journey/{user_id}/items/{id}  : 할 일 완료/취소
- DELETE /journey/{user_id}/items/{id}  : 할 일 빼기
- POST /feedback                        : 답변 피드백(도움이 됐어요/아쉬워요) 저장
- GET  /feedback/summary                : 피드백 수

SSE 이벤트
    event: step      data: {"node": "regulation", "label": "관련 법령을 찾고 있어요"}
    event: delta     data: {"text": "..."}   # 답변 초안 조각 (이어 붙여서 바로 보여 준다)
    event: answer    data: {"text": "...", "sources": [...], "profile": {...}, "follow_ups": [...]}
                     # 근거 검증을 마친 최종 답변. 초안과 다를 수 있으니 화면은 이것으로 바꾼다.
    event: guide     data: {"mode": "talk"|"research", "say": "...", "quick_replies": [...],
                            "suggest": [할 일 제안], "ask": 빠진 정보, "step": 권한 할 일,
                            "profile": {...}}
                     # talk: 검색 없이 길잡이가 바로 한 말 (answer 없이 이것만 온다)
                     # research: answer 뒤에 오는 한마디와 로드맵에 담을 할 일 제안
    event: journey   data: {"added": [할 일, ...], "done": 할 일?}   # 서버가 로드맵을 바꿨을 때
    event: question  data: {"text": "...", "profile": {...}}   # 정보가 부족해 되물을 때
    event: error     data: {"message": "..."}
    event: done      data: {}
"""

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from typing import Annotated, Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.responses import StreamingResponse
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from jeonyeok_helper import __version__, journey
from jeonyeok_helper.agents import guide as guide_rules
from jeonyeok_helper.agents.graph import PROFILE_NAMESPACE
from jeonyeok_helper.agents.prompts import format_profile
from jeonyeok_helper.agents.roadmap import RoadmapProfile
from jeonyeok_helper.agents.state import cadre_of
from jeonyeok_helper.api.limits import RateLimiter
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
    "guide": "다음에 할 일을 고르고 있어요",
}

AgentFactory = Callable[[], AbstractAsyncContextManager[CompiledStateGraph]]
# 첫 작전도를 자동으로 만들었다는 표시. 사용자가 그 임무들을 되돌려 비워도 다시 만들지 않는다.
ROADMAP_MADE_NAMESPACE = ("roadmap_made",)
RoadmapBuilder = Callable[[RoadmapProfile], Awaitable[dict]]

UserId = Annotated[str, Path(pattern=r"^[\w-]{1,64}$")]


class ChatAction(BaseModel):
    """길잡이 버튼이 함께 보내는 동작: 할 일 완료(done), 이번 대화에서 미루기(later)."""

    type: Literal["done", "later"]
    item_id: str = Field(pattern=r"^[\w-]{1,64}$")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = None
    user_id: str | None = Field(default=None, pattern=r"^[\w-]{1,64}$")
    action: ChatAction | None = None


class FeedbackRequest(BaseModel):
    rating: Literal["up", "down"]
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=20000)
    comment: str | None = Field(default=None, max_length=1000)
    thread_id: str | None = Field(default=None, max_length=64)
    user_id: str | None = Field(default=None, max_length=64)


class ProfileUpdate(BaseModel):
    """'내 정보' 화면의 값. 보낸 항목만 바꾸고, 빈 값을 보내면 그 항목을 지운다."""

    service_type: Literal["conscript", "short_term_officer", "long_term", "merit"] | None = None
    service_years: float | None = Field(default=None, ge=0, le=50)
    discharge_date: str | None = Field(default=None, max_length=20)
    age: int | None = Field(default=None, ge=15, le=100)
    region: str | None = Field(default=None, max_length=30)
    merit_status: str | None = Field(default=None, max_length=60)
    branch: str | None = Field(default=None, max_length=20)
    rank: str | None = Field(default=None, max_length=20)
    specialty: str | None = Field(default=None, max_length=60)
    education: str | None = Field(default=None, max_length=60)
    goals: list[str] | None = Field(default=None, max_length=8)
    desired_job: str | None = Field(default=None, max_length=100)
    certificates: str | None = Field(default=None, max_length=200)
    housing: str | None = Field(default=None, max_length=60)
    injury: str | None = Field(default=None, max_length=100)
    memo: str | None = Field(default=None, max_length=1000)


class DoneUpdate(BaseModel):
    done: bool


class SourceRef(BaseModel):
    type: Literal["regulation", "benefit", "institution"]
    title: str = Field(max_length=300)
    url: str = Field(default="", max_length=1000)


class NewItem(BaseModel):
    stage: Literal["before", "right_after", "job", "study", "life", "later"]
    title: str = Field(min_length=1, max_length=120)
    action: str = Field(default="", max_length=300)
    detail: str = Field(default="", max_length=600)
    sources: list[SourceRef] = Field(default_factory=list, max_length=6)
    core: bool = False
    deadline: str = Field(default="", max_length=60)
    due_months: int | None = Field(default=None, ge=-24, le=120)
    # 빼기를 되돌릴 때 원래 상태(완료 여부, 어디서 담겼는지)를 그대로 복원하기 위한 값
    done: bool = False
    origin: Literal["plan", "chat"] = "chat"


class AddItems(BaseModel):
    items: list[NewItem] = Field(min_length=1, max_length=20)
    question: str = Field(default="", max_length=500)


# 로드맵 정리 단계에 '내 정보'로 넘길 항목 (복무 형태·지역 등은 RoadmapProfile 필드로 따로 간다)
_NOTE_KEYS = ("branch", "rank", "specialty", "education", "desired_job", "certificates",
              "housing", "injury", "merit_status", "memo")  # fmt: skip


def roadmap_profile(profile: dict) -> RoadmapProfile:
    notes = format_profile({k: profile[k] for k in _NOTE_KEYS if profile.get(k)})
    return RoadmapProfile(
        service_type=profile["service_type"],
        service_years=profile.get("service_years"),
        cadre=(
            (cadre_of(str(profile.get("rank") or "")) or profile.get("cadre"))
            if profile["service_type"] in ("short_term_officer", "long_term")
            else None
        ),
        discharge_date=(profile.get("discharge_date") or None),
        age=profile.get("age"),
        region=profile.get("region"),
        goals=profile.get("goals") or [],
        education=profile.get("education") or None,
        notes="" if notes == "(아직 모름)" else notes,
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _default_runtime() -> tuple[
    AgentFactory, RoadmapBuilder, Callable[[RoadmapProfile], Awaitable[None]]
]:
    """채팅 에이전트와 로드맵이 같은 도구 데이터(정책 목록 캐시 등)를 쓰도록 묶는다."""
    from jeonyeok_helper.agents.roadmap import build_roadmap, make_organizer, prefetch
    from jeonyeok_helper.agents.runtime import open_agent
    from jeonyeok_helper.benefits.mcp_server import Services

    services = Services()
    chains: dict = {}

    async def roadmap(profile: RoadmapProfile) -> dict:
        if "organizer" not in chains:
            from jeonyeok_helper.llm import get_fast_chat_model

            # 정리는 자료에서 고르는 일이라 빠른 모델로 충분하다 (답변용 모델보다 약 6초 빠름)
            chains["organizer"] = make_organizer(get_fast_chat_model())
        return await build_roadmap(services, chains["organizer"], profile)

    async def warm(profile: RoadmapProfile) -> None:
        await prefetch(services, profile)

    return (lambda: open_agent(services=services)), roadmap, warm


def _limited(request: Request, key: str | None) -> None:
    """모델을 부르는 요청을 사용자(없으면 접속 주소)별로 제한한다."""
    who = key or (request.client.host if request.client else "unknown")
    if not request.app.state.limiter.allow(who):
        raise HTTPException(429, "요청이 너무 많아요. 잠시 후 다시 시도해 주세요.")


def create_app(
    agent_factory: AgentFactory | None = None,
    db_url: str | None = None,
    roadmap_builder: RoadmapBuilder | None = None,
) -> FastAPI:
    warm_roadmap = None
    if agent_factory is None:
        agent_factory, default_roadmap, warm_roadmap = _default_runtime()
        roadmap_builder = roadmap_builder or default_roadmap

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.db = Database(db_url or get_settings().database_url)
        app.state.db.migrate()  # 최신 스키마까지 자동으로
        app.state.limiter = RateLimiter(get_settings().chat_rate_limit_per_minute)
        app.state.roadmap = roadmap_builder
        app.state.warm_roadmap = warm_roadmap
        app.state.background = set()  # 미리 모으기 작업이 끝나기 전에 사라지지 않게 붙들어 둔다
        async with AsyncExitStack() as stack:
            try:
                app.state.agent = await stack.enter_async_context(agent_factory())
                app.state.agent_error = None
            except RuntimeError as e:  # API 키 누락 등: 서버는 띄우고 /chat에서 안내
                log.warning("에이전트를 시작하지 못했습니다: %s", e)
                app.state.agent, app.state.agent_error = None, str(e)
            yield

    app = FastAPI(title="전역도우미", version=__version__, lifespan=lifespan)

    def require_agent(request: Request) -> CompiledStateGraph:
        agent: CompiledStateGraph | None = request.app.state.agent
        if agent is None:
            raise HTTPException(503, request.app.state.agent_error or "에이전트 준비 중")
        return agent

    async def stored_profile(agent: CompiledStateGraph, user_id: str) -> dict:
        if agent.store is None:
            return {}
        item = await agent.store.aget(PROFILE_NAMESPACE, user_id)
        return dict(item.value) if item else {}

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
                "youthcenter": bool(s.youthcenter_api_key),
            },
        }

    def warm_in_background(request: Request, profile: dict) -> None:
        warm = request.app.state.warm_roadmap
        if warm is None or not (profile.get("service_type") and profile.get("region")):
            return
        task = asyncio.create_task(warm(roadmap_profile(profile)))
        request.app.state.background.add(task)
        task.add_done_callback(request.app.state.background.discard)

    async def first_roadmap(request: Request, user_id: str, profile: dict) -> AsyncIterator[str]:
        """처음 쓰는 사람이 복무 형태·지역·전역일을 다 알려 주면 로드맵을 만들고
        첫 할 일을 권한다."""
        if request.app.state.roadmap is None:
            return
        store = getattr(request.app.state.agent, "store", None)
        if store is not None and await store.aget(ROADMAP_MADE_NAMESPACE, user_id):
            return  # 이미 한 번 만들었다 (되돌려 비운 것은 사용자의 선택)
        yield _sse("step", {"node": "roadmap", "label": "내 전역 로드맵을 만들고 있어요"})
        try:
            roadmap = await request.app.state.roadmap(roadmap_profile(profile))
        except Exception:
            log.exception("첫 로드맵 생성 실패")
            return
        db: Database = request.app.state.db
        added = await asyncio.to_thread(
            journey.add_items, db, user_id, journey.roadmap_to_items(roadmap), "plan"
        )
        if not added:
            return
        if store is not None:
            await store.aput(ROADMAP_MADE_NAMESPACE, user_id, {"count": len(added)})
        yield _sse("journey", {"added": added})
        first = guide_rules.next_item(added)
        say = f"작전도 완성! 임무 {len(added)}개를 담았어요."
        if first:
            say += f" 첫 임무는 '{first['title']}'이에요. {first['action']}"
        yield _sse(
            "guide",
            {
                "mode": "talk",
                "say": say,
                "ask": None,
                "step": first,
                "quick_replies": guide_rules.step_replies(first) if first else [],
                "suggest": [],
                "profile": profile,
            },
        )

    @app.post("/chat")
    async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
        agent = require_agent(request)
        _limited(request, req.user_id)
        db: Database = request.app.state.db

        thread_id = req.thread_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        inputs: dict = {"messages": [("user", req.message)]}
        done_item = None
        items: list[dict] = []
        if req.user_id:
            config["configurable"]["user_id"] = req.user_id
            # 버튼 동작을 먼저 반영해야 길잡이가 '다음 할 일'을 제대로 고른다
            if req.action:
                config["configurable"]["action"] = req.action.type
            if req.action and req.action.type == "done":
                done_item = await asyncio.to_thread(
                    journey.set_done, db, req.user_id, req.action.item_id, True
                )
            elif req.action and req.action.type == "later":
                inputs["skipped"] = [req.action.item_id]
            items = await asyncio.to_thread(journey.list_items, db, req.user_id)
            config["configurable"]["journey"] = items

        async def events() -> AsyncIterator[str]:
            yield _sse("thread", {"thread_id": thread_id})
            if done_item:
                yield _sse("journey", {"added": [], "done": done_item})
            # 답변·길잡이는 해당 단계가 끝난 직후의 전체 상태(values)로 보낸다
            pending: set[str] = set()
            state: dict = {}
            sent: set[str] = set()

            def flush(values: dict) -> list[str]:
                out = []
                if "answer" in pending and values.get("draft"):
                    out.append(
                        _sse(
                            "answer",
                            {
                                "text": values["messages"][-1].text,
                                "profile": values.get("profile", {}),
                                "sources": values.get("sources", []),
                                "follow_ups": values.get("follow_ups", []),
                            },
                        )
                    )
                    sent.add("answer")
                if "guide" in pending and (g := values.get("guide")) and g.get("mode"):
                    if g["mode"] == "talk" or "answer" in sent:
                        out.append(_sse("guide", {**g, "profile": values.get("profile", {})}))
                        sent.add("guide")
                pending.clear()
                return out

            try:
                async for mode, chunk in agent.astream(
                    inputs, config, stream_mode=["updates", "messages", "values"]
                ):
                    if mode == "messages":
                        # 답변 초안을 만들어지는 대로 보낸다 (다른 노드의 LLM 출력은 제외)
                        token, meta = chunk
                        if meta.get("langgraph_node") == "respond" and (text := token.text):
                            yield _sse("delta", {"text": text})
                        continue
                    if mode == "values":
                        state = chunk
                        for event in flush(chunk):
                            yield event
                        continue
                    for node in chunk:
                        if label := STEP_LABELS.get(node):
                            yield _sse("step", {"node": node, "label": label})
                        if node == "verify":
                            pending.add("answer")
                        elif node in ("guide", "coach"):
                            pending.add("guide")
                state = (await agent.aget_state(config)).values or state
                pending.update({"answer", "guide"} - sent)
                for event in flush(state):
                    yield event
                if req.user_id and (reopen := state.get("guide", {}).get("reopen")):
                    undone = await asyncio.to_thread(
                        journey.set_done, db, req.user_id, reopen, False
                    )
                    if undone:
                        yield _sse("journey", {"added": [], "done": undone})
                talked = state.get("guide", {}).get("mode") == "talk"
                if not state.get("draft") and not talked:  # respond를 거치지 않았다면 되묻기
                    yield _sse(
                        "question",
                        {"text": state["messages"][-1].text, "profile": state.get("profile", {})},
                    )
                profile = state.get("profile", {})
                missing = guide_rules.missing_field(profile)
                if req.user_id and not items and missing == "discharge_date":
                    warm_in_background(request, profile)  # 전역일을 답하는 동안 자료를 미리 모은다
                if req.user_id and not items and not missing:
                    async for event in first_roadmap(request, req.user_id, profile):
                        yield event
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
    async def get_profile(user_id: UserId, request: Request) -> dict:
        agent: CompiledStateGraph | None = request.app.state.agent
        if agent is None:
            return {"profile": {}}
        return {"profile": await stored_profile(agent, user_id)}

    @app.put("/profile/{user_id}")
    async def put_profile(user_id: UserId, update: ProfileUpdate, request: Request) -> dict:
        agent = require_agent(request)
        if agent.store is None:
            raise HTTPException(503, "프로필 저장소가 없어요")
        profile = await stored_profile(agent, user_id)
        for key, value in update.model_dump(exclude_unset=True).items():
            if value in (None, "", []):
                profile.pop(key, None)
            else:
                profile[key] = value
        await agent.store.aput(PROFILE_NAMESPACE, user_id, profile)
        return {"profile": profile}

    @app.get("/journey/{user_id}")
    def get_journey(user_id: UserId, request: Request) -> dict:
        return {"items": journey.list_items(request.app.state.db, user_id)}

    @app.post("/journey/{user_id}/generate")
    async def generate_journey(user_id: UserId, request: Request) -> dict:
        """저장된 프로필('내 정보')로 시기별 할 일을 한 번에 만들어 로드맵에 담는다."""
        _limited(request, user_id)
        agent = require_agent(request)
        if request.app.state.roadmap is None:
            raise HTTPException(503, "로드맵을 만들 수 없어요")
        profile = await stored_profile(agent, user_id)
        if not profile.get("service_type"):
            raise HTTPException(400, "복무 형태를 먼저 알려 주세요 ('내 정보'에서 고를 수 있어요)")
        try:
            roadmap = await request.app.state.roadmap(roadmap_profile(profile))
        except Exception:
            log.exception("로드맵 생성 실패")
            raise HTTPException(
                500, "로드맵을 만들지 못했어요. 잠시 후 다시 시도해 주세요."
            ) from None
        db: Database = request.app.state.db
        added = journey.add_items(db, user_id, journey.roadmap_to_items(roadmap), "plan")
        return {
            "intro": roadmap.get("intro", ""),
            "added": len(added),
            "items": journey.list_items(db, user_id),
        }

    @app.post("/journey/{user_id}/items", status_code=201)
    def add_journey_items(user_id: UserId, body: AddItems, request: Request) -> dict:
        """길잡이가 제안한 할 일 중 사용자가 고른 것을 담는다 (이미 있는 제목은 건너뜀)."""
        items = [i.model_dump() for i in body.items]
        added = journey.add_items(request.app.state.db, user_id, items, "chat", body.question)
        return {"added": added}

    @app.patch("/journey/{user_id}/items/{item_id}")
    def update_journey_item(
        user_id: UserId, item_id: str, update: DoneUpdate, request: Request
    ) -> dict:
        item = journey.set_done(request.app.state.db, user_id, item_id, update.done)
        if item is None:
            raise HTTPException(404, "없는 할 일이에요")
        return item

    @app.delete("/journey/{user_id}/items/{item_id}", status_code=204)
    def delete_journey_item(user_id: UserId, item_id: str, request: Request) -> None:
        if not journey.delete_item(request.app.state.db, user_id, item_id):
            raise HTTPException(404, "없는 할 일이에요")

    return app


app = create_app()


def run() -> None:
    uvicorn.run("jeonyeok_helper.api.main:app", host="127.0.0.1", port=8000, reload=True)
