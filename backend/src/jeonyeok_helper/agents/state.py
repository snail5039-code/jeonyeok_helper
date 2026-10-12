"""그래프 상태와 구조화 출력 스키마."""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

WORKERS = ("regulation", "benefit", "institution")
ServiceType = Literal["conscript", "short_term_officer", "long_term", "merit", "unknown"]


def merge_profile(old: dict | None, new: dict | None) -> dict:
    """새로 알게 된 값만 덮어쓴다 (None은 '모름'이므로 기존 값을 지우지 않는다)."""
    merged = dict(old or {})
    merged.update({k: v for k, v in (new or {}).items() if v not in (None, "", "unknown")})
    return merged


def add_or_reset(old: list | None, new: list | None) -> list:
    """턴마다 비워야 하는 목록. None을 넣으면 초기화, 목록을 넣으면 이어 붙인다."""
    if new is None:
        return []
    return [*(old or []), *new]


def add_unique_or_reset(old: list | None, new: list | None) -> list:
    """출처 목록. 동시에 돈 워커들이 같은 기관을 찾는 경우가 많아 같은 출처는 한 번만."""
    if new is None:
        return []
    merged, seen = [], set()
    for s in [*(old or []), *new]:
        key = (s.get("type"), s.get("title"), s.get("url", ""))
        if key not in seen:
            seen.add(key)
            merged.append(s)
    return merged


def count_or_reset(old: int | None, new: int | None) -> int:
    """워커 호출 횟수. 동시에 돈 워커들이 각자 1을 더한다. None이면 초기화."""
    return 0 if new is None else (old or 0) + new


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    # 대화가 이어지는 동안 유지 (+ user_id가 있으면 장기 메모리에도 저장)
    profile: Annotated[dict, merge_profile]
    # 아래는 질문(턴)마다 초기화
    findings: Annotated[list[dict], add_or_reset]  # 워커별 요약 {worker, summary}
    sources: Annotated[list[dict], add_unique_or_reset]  # 출처 {type, title, url}
    evidence: Annotated[list[str], add_or_reset]  # 도구가 돌려준 원문 (근거 검증 기준)
    worker_calls: Annotated[int, count_or_reset]
    next: str
    also: list[str]  # next와 동시에 돌릴 워커
    instruction: str
    draft: str


class Profile(BaseModel):
    """대화에서 알아낸 전역자 정보. 언급되지 않은 값은 비워 둔다."""

    service_type: ServiceType = Field(
        default="unknown",
        description=(
            "conscript=의무복무 병사, short_term_officer=5년 미만 간부, "
            "long_term=5년 이상 중·장기 복무 간부, merit=국가유공자·보훈보상대상자"
        ),
    )
    service_years: float | None = Field(default=None, description="복무 기간(년)")
    discharge_date: str | None = Field(default=None, description="전역일 또는 예정일 (YYYY-MM)")
    age: int | None = None
    region: str | None = Field(default=None, description="거주 시·도 (예: 서울, 경기)")
    merit_status: str | None = Field(default=None, description="보훈 대상 여부와 종류")


class Route(BaseModel):
    next: Literal["regulation", "benefit", "institution", "ask_user", "answer"] = Field(
        description=(
            "regulation=법령·규정 근거 검색, benefit=공공서비스 혜택 조회, "
            "institution=신청 기관·연락처 찾기, ask_user=답하려면 사용자 정보가 꼭 필요할 때 "
            "되묻기, answer=모은 정보로 답변"
        )
    )
    also: list[Literal["regulation", "benefit", "institution"]] = Field(
        default_factory=list,
        description="next가 워커일 때, 같은 질문에 함께 필요해서 동시에 돌릴 다른 워커",
    )
    instruction: str = Field(default="", description="워커에게 맡길 구체적인 작업")
    question: str = Field(default="", description="ask_user일 때 사용자에게 할 질문")


class Verification(BaseModel):
    supported: bool = Field(description="초안의 모든 주장이 근거 자료로 뒷받침되는지")
    issues: list[str] = Field(default_factory=list, description="근거가 없거나 틀린 부분")
    # 문제가 없을 때 답변 전체를 다시 쓰게 하면 그만큼 시간이 든다(약 3초). 고칠 때만 채운다.
    answer: str = Field(default="", description="supported=false일 때만: 문제를 고친 최종 답변")
