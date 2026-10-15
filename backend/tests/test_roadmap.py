import asyncio
from types import SimpleNamespace

from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

from jeonyeok_helper.agents.roadmap import (
    RoadmapDraft,
    RoadmapItemDraft,
    RoadmapProfile,
    RoadmapStageDraft,
    assemble,
    build_roadmap,
    gather,
)


class FakeRetriever:
    def __init__(self):
        self.calls = []

    def retrieve(self, question, k=5, region=None):
        self.calls.append((question, region))
        return [
            Document(page_content=f"{question} 조문", metadata={"citation": f"법 {question[:6]}"})
        ]


class FakeYouth:
    def __init__(self):
        self.calls = []

    def search(self, region=None, age=None, limit=8, keyword=None):
        self.calls.append((region, age))
        fields = {"summary": "월세", "support": "20만원", "condition": "", "agency": "서울시"}
        return [
            SimpleNamespace(
                name="청년 월세 지원", url="https://y", min_age=19, max_age=34, **fields
            )
        ]


class FailingGov24:
    def search(self, **kwargs):
        raise RuntimeError("API 503")


def services(youth=None):
    return SimpleNamespace(
        retriever=FakeRetriever(), gov24=FailingGov24(), youth=youth or FakeYouth()
    )


def test_gather_collects_by_service_type_and_skips_failures():
    svc = services()
    ev = gather(svc, RoadmapProfile(service_type="long_term", region="부산 해운대", age=45))

    topics = [q for q, _ in svc.retriever.calls]
    assert "중장기복무 제대군인 전직지원금 지급 대상" in topics  # 장기복무 주제
    assert all(region == "부산 해운대" for _, region in svc.retriever.calls)  # 지역 조례도
    assert svc.youth.calls == []  # 45세는 청년정책 대상이 아님
    # 혜택 API가 실패해도 나머지 자료로 진행, 관할 보훈관서가 들어간다
    assert any(e["kind"] == "institution" and "부산" in e["title"] for e in ev)
    assert [e["id"] for e in ev] == [f"E{i}" for i in range(1, len(ev) + 1)]


def test_gather_adds_youth_policies_for_young_conscripts():
    svc = services()
    ev = gather(svc, RoadmapProfile(service_type="conscript", region="서울"))
    assert svc.youth.calls == [("서울", None)]
    assert any(e["title"] == "청년 월세 지원" for e in ev)


def test_assemble_keeps_only_grounded_items_in_stage_order():
    evidence = [
        {"id": "E1", "kind": "regulation", "title": "국민연금법 제18조", "url": "u1", "text": ""},
        {"id": "E2", "kind": "benefit", "title": "청년 월세", "url": "u2", "text": ""},
    ]
    draft = RoadmapDraft(
        intro="병사 전역자 로드맵",
        stages=[
            RoadmapStageDraft(
                key="later",
                items=[
                    RoadmapItemDraft(title="군복무 크레딧", action="자동 반영", source_ids=["E1"])
                ],
            ),
            RoadmapStageDraft(
                key="life",
                items=[
                    RoadmapItemDraft(title="청년 월세", action="온통청년 신청", source_ids=["E2"]),
                    RoadmapItemDraft(
                        title="지어낸 혜택", action="?", source_ids=["E9"]
                    ),  # 근거 없음
                    RoadmapItemDraft(title="청년 월세", action="중복", source_ids=["E2"]),
                ],
            ),
            RoadmapStageDraft(key="job", items=[]),
        ],
    )
    out = assemble(draft, evidence)

    assert [s["key"] for s in out["stages"]] == ["life", "later"]  # 고정 순서, 빈 단계 제외
    assert [i["title"] for i in out["stages"][0]["items"]] == ["청년 월세"]
    assert out["stages"][1]["items"][0]["sources"] == [
        {"type": "regulation", "title": "국민연금법 제18조", "url": "u1"}
    ]


def test_assemble_keeps_core_and_only_deadlines_found_in_the_item_sources():
    evidence = [
        {"id": "E1", "kind": "benefit", "title": "제대군인 취업지원", "url": "",
         "text": "전역 후 3년 이내 제대군인지원센터에 신청"},
        {"id": "E2", "kind": "benefit", "title": "청년 월세", "url": "", "text": "월 20만 원"},
    ]  # fmt: skip
    draft = RoadmapDraft(
        intro="",
        stages=[
            RoadmapStageDraft(
                key="job",
                items=[
                    RoadmapItemDraft(title="취업지원 신청", action="신청", source_ids=["E1"],
                                     core=True, deadline="전역 후 3년 이내", due_months=36),
                    RoadmapItemDraft(title="청년 월세", action="신청", source_ids=["E2"],
                                     deadline="전역 후 3년 이내", due_months=36),
                ],
            )
        ],
    )  # fmt: skip
    first, second = assemble(draft, evidence)["stages"][0]["items"]
    assert (first["core"], first["deadline"], first["due_months"]) == (True, "전역 후 3년 이내", 36)
    # 다른 자료에 있는 기한을 가져다 붙이지 않는다
    assert (second["core"], second["deadline"], second["due_months"]) == (False, "", None)


def test_build_roadmap_passes_profile_and_evidence_to_organizer():
    seen = {}

    def organize(inp):
        seen.update(inp)
        return RoadmapDraft(
            intro="안내",
            stages=[
                RoadmapStageDraft(
                    key="right_after",
                    items=[RoadmapItemDraft(title="예비군", action="확인", source_ids=["E1"])],
                )
            ],
        )

    profile = RoadmapProfile(service_type="conscript", region="서울", age=24)
    out = asyncio.run(build_roadmap(services(), RunnableLambda(organize), profile))

    assert seen["profile"] == "의무복무 병사, 24세, 서울 거주"
    assert seen["evidence"].startswith("[E1]")
    assert out["stages"][0]["title"] == "전역 직후"
    assert out["profile"]["region"] == "서울"


def test_fits_education_drops_undergrad_scholarships_for_graduate_students():
    from jeonyeok_helper.agents.roadmap import fits_education

    title = "국가장학금 II유형(대학자체노력연계형)"
    assert not fits_education(title, "대학원")
    assert fits_education(title, "대학 재학·휴학")
    assert fits_education(title, None)
    assert fits_education("청년 월세 지원", "대학원")
    # 대졸자는 복학·진학 계획이 없을 때만 뺀다
    assert not fits_education(title, "대학 졸업", ["취업"])
    assert fits_education(title, "대학 졸업", ["복학·진학"])


def test_service_type_filter_drops_programs_for_other_service_types():
    from jeonyeok_helper.agents.roadmap import fits_service_text

    assert not fits_service_text("전직지원금 신청 (5년 이상 복무하셨다면)", "conscript")
    assert not fits_service_text("장기복무 제대군인 주택 특별공급", "conscript")
    assert fits_service_text("군복무 크레딧 신청", "conscript")
    assert fits_service_text("전직지원금 신청", "long_term")
    assert not fits_service_text("장병내일준비적금 가입", "long_term")
    assert fits_service_text("전직지원금 신청", None)  # 모르면 걸러 내지 않는다


def test_gather_cached_reuses_evidence_for_the_same_conditions():
    from jeonyeok_helper.agents import roadmap as rm

    rm._evidence_cache.clear()
    svc = services()
    first = rm.gather_cached(svc, RoadmapProfile(service_type="conscript", region="서울"))
    calls = len(svc.retriever.calls)
    # 전역일이 달라도 자료 모으기 조건은 같다 → 다시 모으지 않는다
    again = rm.gather_cached(
        svc, RoadmapProfile(service_type="conscript", region="서울", discharge_date="2025-08")
    )
    assert again is first and len(svc.retriever.calls) == calls
    # 지역이 다르면 새로 모은다
    rm.gather_cached(svc, RoadmapProfile(service_type="conscript", region="부산"))
    assert len(svc.retriever.calls) > calls
    rm._evidence_cache.clear()


def test_discharged_users_are_not_offered_in_service_only_programs():
    from jeonyeok_helper.agents.roadmap import fits_discharge_status

    assert not fits_discharge_status("장병내일준비적금 정부지원금", "2020-04")  # 이미 전역
    assert fits_discharge_status("장병내일준비적금 정부지원금", "2099-04")  # 아직 복무 중
    assert fits_discharge_status("장병내일준비적금 정부지원금", None)  # 모르면 걸러 내지 않는다
    assert fits_discharge_status("국민연금 군복무 크레딧", "2020-04")


def test_assemble_drops_policy_bodies_that_are_not_actionable():
    evidence = [{"id": "E1", "kind": "benefit", "title": "x", "url": "", "text": ""}]
    draft = RoadmapDraft(
        intro="",
        stages=[
            RoadmapStageDraft(
                key="job",
                items=[
                    RoadmapItemDraft(
                        title="청년정책조정위원회 전문위원회 참여", action="참여", source_ids=["E1"]
                    ),
                    RoadmapItemDraft(title="국민취업지원제도", action="신청", source_ids=["E1"]),
                ],
            )
        ],
    )
    titles = [i["title"] for s in assemble(draft, evidence)["stages"] for i in s["items"]]
    assert titles == ["국민취업지원제도"]


def test_roadmap_profile_text_names_the_cadre():
    from jeonyeok_helper.agents.roadmap import _profile_text

    text = _profile_text(RoadmapProfile(service_type="long_term", cadre="부사관", service_years=9))
    assert text.startswith("중·장기복무 간부(부사관)")
