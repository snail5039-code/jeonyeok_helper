"""대화 → 로드맵: 답변이 끝날 때마다 사용자가 '해야 할 일'을 뽑아 전역 로드맵에 담는다.

채팅 답변은 읽고 지나가기 쉽다. 답변 속 '고용24에서 신청하세요' 같은 할 일을 로드맵 항목으로
남겨 두면, 대화를 이어 갈수록 로드맵이 채워지고 사용자는 그 길을 따라 하나씩 끝낼 수 있다.

- 답변과 근거 출처만 보고 뽑는다 (출처 번호가 없으면 버린다: 근거 없는 할 일 방지)
- 이미 로드맵에 있는 할 일은 다시 넣지 않는다
- 정보만 알려 준 답변(예: '제대군인의 날은 언제?')에서는 아무것도 뽑지 않는다
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from jeonyeok_helper.agents.roadmap import StageKey

PLAN_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "당신은 군 전역자의 전역 로드맵을 관리합니다. 아래 상담 답변에서 사용자가 직접 해야 할 "
            "일(신청, 등록, 확인, 준비)을 0~3개 뽑으세요.\n"
            "- 답변에 있는 내용만 쓰고, 근거 출처 번호(sources)를 반드시 넣으세요.\n"
            "- 사용자에게 해당하지 않거나, 할 일이 아니라 정보일 뿐이면 뽑지 마세요 (빈 목록).\n"
            "- '이미 로드맵에 있는 할 일'과 같은 일은 다시 넣지 마세요.\n"
            "- stage: before(전역 전), right_after(전역 직후), job(취업·창업), study(학업), "
            "life(주거·생활), later(나중에 챙길 것). 사용자의 전역 시기를 고려하세요.\n"
            "- title은 혜택·제도 이름 20자 안팎, action은 '~하세요' 한 문장.",
        ),
        (
            "human",
            "사용자 프로필: {profile}\n이미 로드맵에 있는 할 일: {existing}\n\n"
            "질문: {question}\n\n답변:\n{answer}\n\n근거 출처:\n{sources}",
        ),
    ]
)


class PlanItemDraft(BaseModel):
    stage: StageKey
    title: str = Field(description="할 일 이름 (혜택·제도 이름, 20자 안팎)")
    action: str = Field(description="사용자가 할 일 한 문장 (예: '고용24에서 온라인 신청하세요')")
    detail: str = Field(default="", description="대상·금액·기한을 답변에 있는 대로 한 문장")
    sources: list[int] = Field(description="근거 출처 번호 (예: [1, 3]). 반드시 하나 이상")


class PlanDraft(BaseModel):
    items: list[PlanItemDraft] = Field(default_factory=list, description="뽑은 할 일 0~3개")


def make_planner(llm) -> Runnable:
    return PLAN_PROMPT | llm.with_structured_output(PlanDraft)


async def plan_from_answer(
    planner: Runnable,
    *,
    question: str,
    answer: str,
    sources: list[dict],
    profile: str,
    existing: list[str],
) -> list[dict]:
    """답변에서 할 일을 뽑아 {stage, title, action, detail, sources} 목록으로. 근거가 없거나
    이미 있는 할 일은 뺀다."""
    if not sources:
        return []
    listing = "\n".join(f"[{i}] {s.get('title', '')}" for i, s in enumerate(sources, 1))
    draft: PlanDraft = await planner.ainvoke(
        {
            "profile": profile,
            "existing": ", ".join(existing) or "(없음)",
            "question": question,
            "answer": answer,
            "sources": listing,
        }
    )
    known = {t.strip() for t in existing}
    items = []
    for item in draft.items[:3]:
        refs = [sources[i - 1] for i in item.sources if 1 <= i <= len(sources)]
        title = item.title.strip()[:120]
        if not refs or not title or title in known:
            continue
        known.add(title)
        items.append(
            {
                "stage": item.stage,
                "title": title,
                "action": item.action.strip(),
                "detail": item.detail.strip(),
                "sources": refs,
            }
        )
    return items
