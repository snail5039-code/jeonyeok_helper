"""워커 에이전트 (ReAct) 와 도구 결과에서 출처 추출.

워커 계약: 입력 {messages, instruction, profile} → 출력 {summary, sources}
그래프는 이 계약만 알기 때문에, 테스트에서는 아무 Runnable로 바꿔 끼울 수 있다.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, wrap_model_call
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, HumanMessage, ToolMessage
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool

from jeonyeok_helper.agents.prompts import format_profile


def _tool_payload(msg: ToolMessage) -> dict | None:
    """MCP 도구 결과는 JSON 문자열(또는 그걸 담은 text 블록 목록)로 온다."""
    content = msg.content
    if isinstance(content, list):
        content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def extract_sources(messages: Sequence[AnyMessage]) -> list[dict]:
    """도구 결과에서 답변에 인용할 출처 목록을 만든다. 같은 출처는 한 번만."""
    sources: list[dict] = []
    seen: set[tuple] = set()

    def add(kind: str, title: str, url: str = "") -> None:
        key = (kind, title, url)
        if title and key not in seen:
            seen.add(key)
            sources.append({"type": kind, "title": title, "url": url})

    for msg in messages:
        if not isinstance(msg, ToolMessage) or (data := _tool_payload(msg)) is None:
            continue
        for r in data.get("results", []):
            add("regulation", r.get("citation", ""), r.get("url", ""))
        for b in data.get("benefits", []):
            add("benefit", b.get("name", ""), b.get("url", ""))
        if msg.name == "get_benefit_detail" and data.get("name"):
            add("benefit", data["name"], data.get("url", ""))
        for p in data.get("policies", []):
            add("benefit", p.get("name", ""), p.get("url", ""))
        for j in data.get("jobs", []):
            add("benefit", f"{j.get('company', '')} 채용", j.get("url", ""))
        for v in data.get("vacancies", []):
            add("benefit", f"{v.get('company', '')} {v.get('section', '채용')}", v.get("url", ""))
        if data.get("stores"):
            add("benefit", "병무청 나라사랑가게", data.get("info_url", ""))
        for o in data.get("offices", []):
            add("institution", o.get("name", ""), o.get("url", ""))
        for h in data.get("hospitals", []):
            add("institution", h.get("name", ""), h.get("map_url", ""))
        for inst in [*data.get("institutions", []), *data.get("fallback", [])]:
            add("institution", inst.get("name", ""), inst.get("url", ""))
    return sources


@wrap_model_call
async def require_tool_call(request: ModelRequest, handler):
    """워커는 반드시 도구를 부른다. 안 부르고 자기 지식으로 답하면 근거(evidence)가 없어
    검증 단계에서 답변이 통째로 지워진다 (예: '병적증명서 어디서?' → 빈 답변)."""
    return await handler(request.override(tool_choice="any"))


def make_react_worker(llm: BaseChatModel, tools: list[BaseTool], system_prompt: str) -> Runnable:
    # 도구를 부른 뒤 결과를 다시 LLM으로 요약하지 않고 바로 끝낸다 (return_direct).
    # 답변·검증은 요약이 아니라 도구 원문(evidence)을 근거로 쓰므로 요약은 시간만 든다(약 3초).
    direct = [t.model_copy(update={"return_direct": True}) for t in tools]
    agent = create_agent(llm, direct, system_prompt=system_prompt, middleware=[require_tool_call])

    async def run(inp: dict) -> dict:
        task = HumanMessage(
            f"[슈퍼바이저 지시] {inp.get('instruction') or '마지막 질문을 처리하세요.'}\n"
            f"[사용자 프로필] {format_profile(inp.get('profile'))}"
        )
        history = [*inp["messages"], task]
        result = await agent.ainvoke({"messages": history})
        produced = result["messages"][len(history) :]
        return {
            "summary": summarize(produced),
            "sources": extract_sources(produced),
            "evidence": extract_evidence(produced),
        }

    return RunnableLambda(run)


def _tool_texts(messages: Sequence[AnyMessage], limit: int) -> list[str]:
    """도구 결과를 '[도구 이름] 원문' 문자열로. 원문은 limit자에서 자른다."""
    texts = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            data = _tool_payload(msg)
            text = json.dumps(data, ensure_ascii=False) if data is not None else str(msg.content)
            texts.append(f"[{msg.name}] {text[:limit]}")
    return texts


def summarize(messages: Sequence[AnyMessage], limit: int = 600) -> str:
    """라우터가 '충분히 찾았는지' 판단할 짧은 요약. 도구를 안 썼으면 워커의 마지막 말."""
    if texts := _tool_texts(messages, limit):
        return "\n".join(texts)
    return messages[-1].text if messages else ""


def extract_evidence(messages: Sequence[AnyMessage], limit: int = 3000) -> list[str]:
    """도구가 실제로 돌려준 원문. 근거 검증은 워커 요약이 아니라 이 원문을 기준으로 한다
    (요약에는 LLM이 자기 지식을 섞을 수 있다)."""
    return _tool_texts(messages, limit)
