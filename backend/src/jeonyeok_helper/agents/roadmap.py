"""전역 로드맵: 프로필을 한 번 받아 '언제 무엇을 해야 하는지'를 단계별 할 일 목록으로 만든다.

1. 모으기: 복무 형태에 맞는 규정 검색, 정부24 혜택, 청년정책, 관할 보훈관서를 동시에 조회
2. 정리하기: LLM이 모은 자료만으로 단계(전역 전 → 직후 → 구직 → 학업 → 생활 → 나중에)를 나눈다
3. 검사하기: 할 일마다 근거 자료 번호가 실제 모은 자료에 있어야 남긴다 (링크는 우리가 붙임)

채팅과 달리 질문을 기다리지 않고 한 번에 전부 보여 주는 '내비게이터' 화면용.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

StageKey = Literal["before", "right_after", "job", "study", "life", "later"]
STAGE_TITLES: dict[str, str] = {
    "before": "전역 전",
    "right_after": "전역 직후",
    "job": "취업·창업",
    "study": "학업",
    "life": "주거·생활",
    "later": "나중에 챙길 것",
}

# 복무 형태별로 꼭 확인할 주제 (규정 검색 질문)
COMMON_TOPICS = [
    "전역 후 예비군 편성과 훈련 기간",
    "군복무 크레딧 국민연금 가입기간 추가 산입",
    "중소기업 취업 청년 소득세 감면 병역 이행 기간",
]
TOPICS_BY_TYPE = {
    "conscript": [
        "장병내일준비적금 전역 시 재정지원금",
        "의무복무 제대군인 취업 지원 대상",
        "복학 등록금 학자금 지원",
    ],
    "short_term_officer": [
        "단기복무 장교 부사관 전역 후 취업 지원",
        "제대군인 채용시험 응시연령 상한 연장",
        "제대군인 교육지원 학비",
    ],
    "long_term": [
        "중장기복무 제대군인 전직지원금 지급 대상",
        "군인연금 퇴직급여 퇴직연금 지급 요건",
        "장기복무 제대군인 교육지원 대부 지원",
        "전역 예정 군인 전직 교육",
    ],
    "merit": [
        "국가유공자 등록 신청 절차와 서류",
        "보훈급여금 종류와 지급",
        "국가보훈대상자 의료지원",
        "국가유공자 취업 지원",
    ],
}


class RoadmapProfile(BaseModel):
    service_type: Literal["conscript", "short_term_officer", "long_term", "merit"]
    service_years: float | None = Field(default=None, ge=0, le=50)
    discharge_date: str | None = Field(default=None, max_length=20)
    age: int | None = Field(default=None, ge=15, le=100)
    region: str | None = Field(default=None, max_length=30)


class RoadmapItemDraft(BaseModel):
    title: str = Field(description="할 일 이름 (혜택·제도 이름, 20자 안팎)")
    action: str = Field(description="사용자가 할 일을 한 문장으로 (예: '고용24에서 온라인 신청')")
    detail: str = Field(default="", description="대상·내용을 자료에 있는 대로 한두 문장")
    source_ids: list[str] = Field(description="근거로 쓴 자료 번호 (예: ['E3']). 반드시 하나 이상")


class RoadmapStageDraft(BaseModel):
    key: StageKey
    items: list[RoadmapItemDraft]


class RoadmapDraft(BaseModel):
    intro: str = Field(description="사용자 상황 요약과 로드맵 안내 한두 문장")
    stages: list[RoadmapStageDraft]


ROADMAP_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "당신은 군 전역자의 할 일을 시기별로 정리하는 '전역도우미'입니다. 아래 '자료'에 있는 "
            "내용만으로 사용자의 전역 로드맵을 만드세요.\n"
            "- 단계: before(전역 전), right_after(전역 직후), job(취업·창업), study(학업), "
            "life(주거·생활), later(나중에 챙길 것). 해당하는 할 일이 없는 단계는 빼세요.\n"
            "- 할 일마다 근거 자료 번호(source_ids)를 반드시 넣고, 자료에 없는 혜택·금액·기한은 "
            "쓰지 마세요.\n"
            "- 사용자의 복무 형태·나이·지역에 맞지 않는 항목은 빼세요 (예: 다른 지역 혜택, "
            "장기복무자 전용 혜택을 병사에게).\n"
            "- 단계마다 중요한 순서로 최대 4개, 전체 12개 이내. 같은 제도는 한 번만.\n"
            "- 말투는 짧고 쉽게: '~하세요', '~할 수 있어요'.",
        ),
        ("human", "사용자: {profile}\n\n자료:\n{evidence}"),
    ]
)


def _profile_text(p: RoadmapProfile) -> str:
    names = {
        "conscript": "의무복무 병사",
        "short_term_officer": "단기복무 간부",
        "long_term": "중·장기복무 간부",
        "merit": "보훈대상자",
    }
    parts = [names[p.service_type]]
    if p.service_years:
        parts.append(f"{p.service_years:g}년 복무")
    if p.discharge_date:
        parts.append(f"전역 {p.discharge_date}")
    if p.age:
        parts.append(f"{p.age}세")
    if p.region:
        parts.append(f"{p.region} 거주")
    return ", ".join(parts)


def gather(services: Any, profile: RoadmapProfile) -> list[dict]:
    """로드맵 근거 자료. 각 자료: {id, kind, title, url, text}. 실패한 조회는 건너뛴다."""
    evidence: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, title: str, url: str, text: str) -> None:
        if not title or (kind, title) in seen:
            return
        seen.add((kind, title))
        evidence.append(
            {"id": f"E{len(evidence) + 1}", "kind": kind, "title": title, "url": url or "",
             "text": text[:700]}
        )  # fmt: skip

    def safely(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            log.warning("로드맵 자료 조회 실패: %s", getattr(fn, "__name__", fn), exc_info=True)
            return []

    from jeonyeok_helper.benefits.mcp_server import fits_service_type

    # 조회끼리 서로 기다릴 필요가 없어 한꺼번에 돌린다 (차례로 하면 약 28초).
    # 결과를 넣는 순서는 고정해서 자료 번호(E1, E2 …)가 매번 같게 한다.
    topics = COMMON_TOPICS + TOPICS_BY_TYPE[profile.service_type]
    young = profile.age is None and profile.service_type in ("conscript", "short_term_officer")
    with ThreadPoolExecutor(max_workers=len(topics) + 2) as pool:
        laws = [
            pool.submit(safely, services.retriever.retrieve, t, k=3, region=profile.region)
            for t in topics
        ]
        benefits = pool.submit(safely, services.gov24.search, region=profile.region, limit=20)
        youth = (
            pool.submit(
                safely, services.youth.search, region=profile.region, age=profile.age, limit=8
            )  # fmt: skip
            if young or (profile.age is not None and profile.age <= 34)
            else None
        )

    for future in laws:
        for d in future.result():
            add("regulation", d.metadata.get("citation", ""), d.metadata.get("url", ""),
                d.page_content)  # fmt: skip

    for b in [b for b in benefits.result() if fits_service_type(b, profile.service_type)][:10]:
        text = f"{b.summary} 대상: {b.target} 내용: {b.content} 신청: {b.how_to_apply}"
        add("benefit", b.name, b.url, f"{text} 소관: {b.agency}")

    for p in youth.result() if youth else []:
        add("benefit", p.name, p.url,
            f"{p.summary} 지원: {p.support} 대상 나이: {p.min_age}~{p.max_age} "
            f"조건: {p.condition} 기관: {p.agency}")  # fmt: skip

    if profile.region:
        from jeonyeok_helper.benefits.offices import find_offices, load_offices

        for o in find_offices(load_offices(), profile.region)[:2]:
            text = f"관할 보훈관서. 주소 {o.address}, 전화 {o.phone}."
            add("institution", o.name, o.url, f"{text} 보훈 등록·제대군인 지원 상담")
    return evidence


def assemble(draft: RoadmapDraft, evidence: list[dict]) -> dict:
    """LLM 초안에서 근거가 확인되는 할 일만 남기고, 링크·출처는 모은 자료에서 붙인다."""
    by_id = {e["id"]: e for e in evidence}
    stages, used = [], set()
    for key in STAGE_TITLES:  # 단계 순서는 고정
        items = []
        for stage in (s for s in draft.stages if s.key == key):
            for item in stage.items:
                refs = [by_id[i] for i in item.source_ids if i in by_id]
                if not refs or item.title in used:
                    continue  # 근거 없는 할 일, 중복은 뺀다
                used.add(item.title)
                items.append(
                    {
                        "id": f"{key}:{item.title}",
                        "title": item.title,
                        "action": item.action,
                        "detail": item.detail,
                        "sources": [
                            {"type": r["kind"], "title": r["title"], "url": r["url"]} for r in refs
                        ],
                    }
                )
        if items:
            stages.append({"key": key, "title": STAGE_TITLES[key], "items": items})
    return {"intro": draft.intro, "stages": stages}


async def build_roadmap(services: Any, organizer: Runnable, profile: RoadmapProfile) -> dict:
    evidence = await asyncio.to_thread(gather, services, profile)
    if not evidence:
        return {
            "intro": "지금은 자료를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.",
            "stages": [],
        }
    listing = "\n\n".join(f"[{e['id']}] ({e['kind']}) {e['title']}\n{e['text']}" for e in evidence)
    draft: RoadmapDraft = await organizer.ainvoke(
        {"profile": _profile_text(profile), "evidence": listing}
    )
    return assemble(draft, evidence) | {"profile": profile.model_dump(exclude_none=True)}


def make_organizer(llm) -> Runnable:
    return ROADMAP_PROMPT | llm.with_structured_output(RoadmapDraft)
