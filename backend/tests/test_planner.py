import asyncio

from langchain_core.runnables import RunnableLambda

from jeonyeok_helper.agents.planner import PlanDraft, PlanItemDraft, plan_from_answer

SOURCES = [
    {"type": "benefit", "title": "국민취업지원제도", "url": "https://gov.kr/1"},
    {"type": "regulation", "title": "구직자 취업촉진법 제6조", "url": "https://law.go.kr/2"},
]


def run(draft: PlanDraft, existing=(), sources=SOURCES):
    seen = []

    async def fake(inp):
        seen.append(inp)
        return draft

    items = asyncio.run(
        plan_from_answer(
            RunnableLambda(fake),
            question="취업 지원?",
            answer="고용24에서 신청하세요 [1][2]",
            sources=sources,
            profile="복무 형태=conscript",
            existing=list(existing),
        )
    )
    return items, seen


def item(title: str, sources: list[int], stage="job") -> PlanItemDraft:
    return PlanItemDraft(stage=stage, title=title, action="신청하세요", sources=sources)


def test_plan_keeps_grounded_new_items_and_maps_sources():
    draft = PlanDraft(
        items=[
            item("국민취업지원제도", [1, 2]),
            item("근거 없는 할 일", []),  # 출처가 없으면 뺀다
            item("엉뚱한 번호", [9]),  # 없는 출처 번호도
            item("이미 있는 일", [1]),
            item("국민취업지원제도", [1]),  # 같은 답변 안의 중복
        ]
    )
    items, seen = run(draft, existing=["이미 있는 일"])
    assert [i["title"] for i in items] == ["국민취업지원제도"]
    assert [s["title"] for s in items[0]["sources"]] == [
        "국민취업지원제도",
        "구직자 취업촉진법 제6조",
    ]
    assert "[1] 국민취업지원제도" in seen[0]["sources"] and seen[0]["existing"] == "이미 있는 일"


def test_plan_skips_llm_when_answer_has_no_sources():
    items, seen = run(PlanDraft(items=[item("x", [1])]), sources=[])
    assert items == [] and seen == []
