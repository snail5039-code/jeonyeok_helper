"""워커 에이전트 (ReAct) 와 도구 결과에서 출처 추출.

워커 계약: 입력 {messages, instruction, profile} → 출력 {summary, sources}
그래프는 이 계약만 알기 때문에, 테스트에서는 아무 Runnable로 바꿔 끼울 수 있다.
"""

from __future__ import annotations

import json
import re
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


# 근거 원문 보기: 출처마다 도구가 돌려준 원문을 발췌해 붙인다 (화면에서 [n]을 누르면 보인다).
EXCERPT_LIMIT = 1500
# 원문에서 보여 줄 칸과 이름. 여기 없는 칸(주소 링크, 내부 ID 등)은 뺀다.
EXCERPT_FIELDS = {
    "summary": "요약",
    "description": "설명",
    "target": "대상",
    "content": "내용",
    "support": "지원 내용",
    "how_to_apply": "신청 방법",
    "apply": "신청",
    "deadline": "기한",
    "period": "기간",
    "agency": "소관 기관",
    "section": "구분",
    "title": "제목",
    "type": "종류",
    "region": "지역",
    "address": "주소",
    "phone": "전화",
    "contact": "문의",
}


def _excerpt(record: dict) -> str:
    """정해 둔 칸만 '이름: 값' 줄로 모은 발췌"""
    lines = [
        f"{label}: {value.strip()}"
        for key, label in EXCERPT_FIELDS.items()
        if isinstance(value := record.get(key), str) and value.strip()
    ]
    return "\n".join(lines)[:EXCERPT_LIMIT]


def _unwrap(text: str) -> str:
    """PDF에서 뽑은 글은 줄 끝에 공백을 두고 줄을 넘긴다. 그런 줄바꿈은 이어 붙인다."""
    return re.sub(r"[ \t]+\n[ \t]*", " ", text)


def extract_sources(messages: Sequence[AnyMessage]) -> list[dict]:
    """도구 결과에서 답변에 인용할 출처 목록을 만든다. 같은 출처는 한 번만.
    원문이 있으면 excerpt(발췌), 법령은 date(시행일)도 붙인다."""
    sources: list[dict] = []
    seen: set[tuple] = set()

    def add(kind: str, title: str, url: str = "", excerpt: str = "", date: str = "") -> None:
        key = (kind, title, url)
        if title and key not in seen:
            seen.add(key)
            source = {"type": kind, "title": title, "url": url}
            if excerpt:
                source["excerpt"] = excerpt[:EXCERPT_LIMIT]
            if date:
                source["date"] = date
            sources.append(source)

    for msg in messages:
        if not isinstance(msg, ToolMessage) or (data := _tool_payload(msg)) is None:
            continue
        for r in data.get("results", []):
            add(
                "regulation",
                r.get("citation", ""),
                r.get("url", ""),
                _unwrap(r.get("text", "") or ""),
                r.get("enforced_at", "") or "",
            )
        for b in data.get("benefits", []):
            add("benefit", b.get("name", ""), b.get("url", ""), _excerpt(b))
        if msg.name == "get_benefit_detail" and data.get("name"):
            add("benefit", data["name"], data.get("url", ""), _excerpt(data))
        for p in data.get("policies", []):
            add("benefit", p.get("name", ""), p.get("url", ""), _excerpt(p))
        for j in [*data.get("jobs", []), *data.get("nationwide_jobs", [])]:
            add("benefit", f"{j.get('company', '')} 채용", j.get("url", ""), _excerpt(j))
        for v in data.get("vacancies", []):
            title = f"{v.get('company', '')} {v.get('section', '채용')}"
            add("benefit", title, v.get("url", ""), _excerpt(v))
        if data.get("stores"):
            add("benefit", "병무청 나라사랑가게", data.get("info_url", ""), data.get("note", ""))
        for o in data.get("offices", []):
            add("institution", o.get("name", ""), o.get("url", ""), _excerpt(o))
        for h in data.get("hospitals", []):
            add("institution", h.get("name", ""), h.get("map_url", ""), _excerpt(h))
        for inst in [*data.get("institutions", []), *data.get("fallback", [])]:
            add("institution", inst.get("name", ""), inst.get("url", ""), _excerpt(inst))
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
