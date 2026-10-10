"""실제 실행용 조립: Gemini + MCP 도구 + 메모리 → 컴파일된 그래프.

    async with open_agent() as agent:
        await agent.ainvoke({"messages": [("user", "질문")]},
                            {"configurable": {"thread_id": "t1", "user_id": "u1"}})

MCP 서버는 같은 프로세스 안에서 메모리 스트림으로 연결한다 (MCP 프로토콜은 그대로).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.memory import InMemoryStore
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


def build_components(llm: BaseChatModel, tools: list[BaseTool]) -> Components:
    by_name = {t.name: t for t in tools}
    workers = {}
    for worker, names in WORKER_TOOLS.items():
        worker_tools = [by_name[n] for n in names if n in by_name]
        if worker_tools:
            workers[worker] = make_react_worker(llm, worker_tools, WORKER_PROMPTS[worker])
    return Components(
        profile_extractor=PROFILE_PROMPT | llm.with_structured_output(Profile),
        router=ROUTER_PROMPT | llm.with_structured_output(Route),
        workers=workers,
        responder=RESPOND_PROMPT | llm | StrOutputParser(),
        verifier=VERIFY_PROMPT | llm.with_structured_output(Verification),
    )


@asynccontextmanager
async def open_agent(llm: BaseChatModel | None = None) -> AsyncIterator[CompiledStateGraph]:
    from jeonyeok_helper.benefits.mcp_server import create_server
    from jeonyeok_helper.config import get_settings

    if llm is None:
        from jeonyeok_helper.llm import get_chat_model

        llm = get_chat_model(temperature=0.2)

    server = create_server()
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        tools = await load_mcp_tools(session)
        # TODO(4단계): 서버 재시작 후에도 대화가 남도록 SQLite/Postgres 체크포인터로 교체
        yield build_graph(
            build_components(llm, tools),
            checkpointer=InMemorySaver(),
            store=InMemoryStore(),
            max_worker_calls=get_settings().max_worker_calls,
        )
