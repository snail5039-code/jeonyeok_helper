"""실제 실행용 조립: Gemini + MCP 도구 + 메모리 → 컴파일된 그래프.

    async with open_agent() as agent:
        await agent.ainvoke({"messages": [("user", "질문")]},
                            {"configurable": {"thread_id": "t1", "user_id": "u1"}})

MCP 서버는 같은 프로세스 안에서 메모리 스트림으로 연결한다 (MCP 프로토콜은 그대로).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.memory import InMemoryStore
from langgraph.store.sqlite import AsyncSqliteStore
from mcp.shared.memory import create_connected_server_and_client_session

from jeonyeok_helper.agents.graph import Components, build_graph
from jeonyeok_helper.agents.prompts import (
    PROFILE_PROMPT,
    RESPOND_PROMPT,
    ROUTER_PROMPT,
    VERIFY_PROMPT,
    WORKER_PROMPTS,
    WORKER_TOOLS,
)
from jeonyeok_helper.agents.state import Profile, Route, Verification
from jeonyeok_helper.agents.workers import make_react_worker


def build_components(
    llm: BaseChatModel, tools: list[BaseTool], fast_llm: BaseChatModel | None = None
) -> Components:
    """llm은 답변 작성에, fast_llm은 판단 단계와 워커에 쓴다.

    워커는 도구를 고르고 결과를 옮기는 일이라 깊은 추론이 필요 없고, 답변은 워커 요약이 아니라
    도구 원문(evidence)을 근거로 쓰기 때문에 빠른 설정으로도 품질이 유지된다.
    """
    fast = fast_llm or llm
    by_name = {t.name: t for t in tools}
    workers = {}
    for worker, names in WORKER_TOOLS.items():
        worker_tools = [by_name[n] for n in names if n in by_name]
        if worker_tools:
            workers[worker] = make_react_worker(fast, worker_tools, WORKER_PROMPTS[worker])
    return Components(
        profile_extractor=PROFILE_PROMPT | fast.with_structured_output(Profile),
        router=ROUTER_PROMPT | fast.with_structured_output(Route),
        workers=workers,
        responder=RESPOND_PROMPT | llm | StrOutputParser(),
        verifier=VERIFY_PROMPT | fast.with_structured_output(Verification),
    )


@asynccontextmanager
async def _memory(state_db: Path | None) -> AsyncIterator[tuple]:
    """대화 기록(체크포인터)과 프로필(저장소). state_db가 없으면 메모리에만 둔다."""
    if state_db is None:
        yield InMemorySaver(), InMemoryStore()
        return
    state_db.parent.mkdir(parents=True, exist_ok=True)
    async with (
        AsyncSqliteSaver.from_conn_string(str(state_db)) as checkpointer,
        AsyncSqliteStore.from_conn_string(str(state_db)) as store,
    ):
        await store.setup()
        yield checkpointer, store


_DEFAULT = object()


@asynccontextmanager
async def open_agent(
    llm: BaseChatModel | None = None,
    *,
    fast_llm: BaseChatModel | None = None,
    state_db: Path | None | object = _DEFAULT,
    services=None,
) -> AsyncIterator[CompiledStateGraph]:
    """state_db를 생략하면 설정의 SQLite 파일, None을 주면 메모리(평가·테스트용).

    services(benefits.mcp_server.Services)를 주면 MCP 도구가 그 캐시를 같이 쓴다
    (로드맵처럼 도구 데이터를 직접 쓰는 기능과 정책 목록 등을 두 번 받지 않도록).
    """
    from jeonyeok_helper.benefits.mcp_server import create_server
    from jeonyeok_helper.config import get_settings

    settings = get_settings()
    if llm is None:
        from jeonyeok_helper.llm import get_chat_model, get_fast_chat_model

        # 같은 질문에 같은 혜택이 나오도록 온도 0 (일관성 점검에서 넓은 질문의 항목이 흔들렸음)
        llm = get_chat_model(temperature=0, thinking_budget=settings.gemini_thinking_budget)
        fast_llm = fast_llm or get_fast_chat_model()
    db = settings.state_db if state_db is _DEFAULT else state_db

    server = create_server(services)
    async with (
        create_connected_server_and_client_session(server._mcp_server) as session,
        _memory(db) as (checkpointer, store),
    ):
        tools = await load_mcp_tools(session)
        yield build_graph(
            build_components(llm, tools, fast_llm),
            checkpointer=checkpointer,
            store=store,
            max_worker_calls=settings.max_worker_calls,
        )
