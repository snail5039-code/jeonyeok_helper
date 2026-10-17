"""실제 실행용 조립: Gemini + MCP 도구 + 메모리 → 컴파일된 그래프.

메모리(대화 기록 체크포인터, 프로필 저장소)는 PostgreSQL에 둔다 (벡터 검색·피드백과 같은 DB).

    async with open_agent() as agent:
        await agent.ainvoke({"messages": [("user", "질문")]},
                            {"configurable": {"thread_id": "t1", "user_id": "u1"}})

MCP 서버는 같은 프로세스 안에서 메모리 스트림으로 연결한다 (MCP 프로토콜은 그대로).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres.aio import AsyncPostgresStore
from mcp.shared.memory import create_connected_server_and_client_session

from jeonyeok_helper.agents.graph import Components, build_graph
from jeonyeok_helper.agents.guide import make_coach, make_guide
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

log = logging.getLogger(__name__)


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
        coach=make_coach(fast),
        guide=make_guide(fast),
    )


def postgres_conninfo(url: str) -> str:
    """SQLAlchemy 주소(postgresql+psycopg://)를 psycopg가 읽는 주소(postgresql://)로."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


async def migrate_sqlite_profiles(state_db: Path, store) -> int:
    """예전 SQLite 파일(state.sqlite)에 있던 사용자 프로필을 Postgres 저장소로 옮긴다.
    이미 있는 사용자는 건드리지 않는다. 옮긴 뒤 파일 이름을 바꿔 다시 옮기지 않는다.
    (대화 기록은 옮기지 않는다: 이어 쓰지 않는 옛 대화이고 형식이 저장소마다 다르다.)"""
    if not state_db.exists():
        return 0
    from langgraph.store.sqlite import AsyncSqliteStore

    from jeonyeok_helper.agents.graph import PROFILE_NAMESPACE

    moved = 0
    async with AsyncSqliteStore.from_conn_string(str(state_db)) as old:
        offset = 0
        while items := await old.asearch(PROFILE_NAMESPACE, limit=100, offset=offset):
            for item in items:
                if await store.aget(PROFILE_NAMESPACE, item.key) is None:
                    await store.aput(PROFILE_NAMESPACE, item.key, item.value)
                    moved += 1
            offset += len(items)
    state_db.rename(state_db.with_name(state_db.name + ".migrated"))
    return moved


@asynccontextmanager
async def _memory(persistent: bool, state_db: Path | None = None) -> AsyncIterator[tuple]:
    """대화 기록(체크포인터)과 프로필(저장소). persistent가 아니면 메모리에만 둔다(평가·테스트)."""
    if not persistent:
        yield InMemorySaver(), InMemoryStore()
        return
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    from jeonyeok_helper.config import get_settings

    # 요청이 동시에 와도 한 연결을 두고 기다리지 않게 연결 풀을 쓴다
    async with AsyncConnectionPool(
        postgres_conninfo(get_settings().database_url),
        max_size=10,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=False,
    ) as pool:
        checkpointer = AsyncPostgresSaver(pool)
        store = AsyncPostgresStore(pool)
        await checkpointer.setup()
        await store.setup()
        if state_db is not None:
            if moved := await migrate_sqlite_profiles(state_db, store):
                log.info("SQLite 프로필 %d개를 Postgres로 옮김", moved)
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
    """state_db를 생략하면 Postgres(DATABASE_URL)에 저장하고, None을 주면 메모리(평가·테스트용).
    설정의 state_db(예전 SQLite 파일)가 남아 있으면 프로필을 Postgres로 한 번 옮긴다.

    services(benefits.mcp_server.Services)를 주면 MCP 도구가 그 캐시를 같이 쓴다
    (로드맵처럼 도구 데이터를 직접 쓰는 기능과 정책 목록 등을 두 번 받지 않도록).
    """
    from jeonyeok_helper.benefits.mcp_server import create_server
    from jeonyeok_helper.config import get_settings

    settings = get_settings()
    if llm is None:
        from jeonyeok_helper.llm import get_answer_model, get_fast_chat_model

        llm = get_answer_model()
        fast_llm = fast_llm or get_fast_chat_model()
    persistent = state_db is not None
    legacy = settings.state_db if state_db is _DEFAULT else state_db

    server = create_server(services)
    async with (
        create_connected_server_and_client_session(server._mcp_server) as session,
        _memory(persistent, legacy) as (checkpointer, store),
    ):
        tools = await load_mcp_tools(session)
        yield build_graph(
            build_components(llm, tools, fast_llm),
            checkpointer=checkpointer,
            store=store,
            max_worker_calls=settings.max_worker_calls,
        )
