from datetime import date

from jeonyeok_helper.agents.guide import (
    GuideDraft,
    PlanItemDraft,
    ask_replies,
    missing_field,
    needs_research,
    next_item,
    pick_items,
    same_task,
    step_replies,
    with_next_step,
    with_question,
)
from jeonyeok_helper.journey import ground_deadline

SOURCES = [
    {"type": "benefit", "title": "국민취업지원제도", "url": "https://gov.kr/1"},
    {"type": "regulation", "title": "구직자 취업촉진법 제6조", "url": "https://law.go.kr/2"},
]


def test_missing_field_asks_service_type_then_region_then_discharge_date():
    assert missing_field({}) == "service_type"
    assert missing_field({"service_type": "unknown"}) == "service_type"
    assert missing_field({"service_type": "conscript"}) == "region"
    assert missing_field({"service_type": "conscript", "region": "서울"}) == "discharge_date"
    full = {"service_type": "conscript", "region": "서울", "discharge_date": "2026"}
    assert missing_field(full) is None


def test_discharge_buttons_carry_years_the_extractor_can_read():
    replies = ask_replies("discharge_date", today=date(2026, 10, 13))
    assert [r["message"] for r in replies] == [
        "2027년 초에 전역 예정이에요",
        "2026년에 전역했어요",
        "2025년에 전역했어요",
        "2024년에 전역했어요",
    ]
    assert len(ask_replies("region")) == 17


def item(id_, stage="job", core=False, due=None, done=False):
    return {"id": id_, "title": id_, "stage": stage, "core": core, "due_months": due, "done": done}


def test_next_item_prefers_core_then_earliest_deadline_then_stage():
    items = [
        item("plain-before", stage="before"),
        item("core-late", core=True, due=36),
        item("core-soon", core=True, due=3),
        item("core-no-due", stage="before", core=True),
        item("core-done", core=True, due=1, done=True),
    ]
    assert next_item(items)["id"] == "core-soon"
    assert next_item(items, skipped=["core-soon"])["id"] == "core-late"
    assert next_item(items, skipped=["core-soon", "core-late"])["id"] == "core-no-due"
    assert next_item([item("x", done=True)]) is None


def test_step_buttons_send_done_and_later_actions():
    done, how, later = step_replies({"id": "i1", "title": "예비군 편성 확인"})
    assert done["action"] == {"type": "done", "item_id": "i1"}
    assert how["message"] == "예비군 편성 확인, 어떻게 신청해요?" and "action" not in how
    assert later["action"]["type"] == "later"


def test_deadline_is_kept_only_when_the_text_says_so():
    text = ["전역 후 3년 이내에 제대군인지원센터에 신청"]
    assert ground_deadline("전역 후 3년이내", 36, text) == ("전역 후 3년이내", 36)  # 띄어쓰기 무시
    assert ground_deadline("전역 후 1년 이내", 12, text) == ("", None)  # 지어낸 기한
    assert ground_deadline("전역 후 3년 이내", 999, text) == ("전역 후 3년 이내", None)
    assert ground_deadline("", 36, text) == ("", None)


def test_pick_items_maps_sources_and_drops_ungrounded_or_known():
    draft = GuideDraft(
        say="",
        items=[
            PlanItemDraft(stage="job", title="국민취업지원제도", action="신청하세요",
                          sources=[1, 2], core=True, deadline="전역 후 1년 이내", due_months=12),
            PlanItemDraft(stage="job", title="근거 없는 할 일", action="x", sources=[]),
            PlanItemDraft(stage="job", title="엉뚱한 번호", action="x", sources=[9]),
            PlanItemDraft(stage="job", title="이미 있는 일", action="x", sources=[1]),
        ],
    )  # fmt: skip
    answer = "고용24에서 신청하세요. 전역 후 1년 이내에 신청해야 해요 [1][2]"
    [picked] = pick_items(draft, answer=answer, sources=SOURCES, existing=["이미 있는 일"])
    assert picked["title"] == "국민취업지원제도" and picked["core"] is True
    assert [s["title"] for s in picked["sources"]] == [s["title"] for s in SOURCES]
    assert (picked["deadline"], picked["due_months"]) == ("전역 후 1년 이내", 12)


def test_guide_lines_end_with_question_and_next_step_once():
    assert with_question("좋아요!", "region") == "좋아요! 지금 어디 살아요?"
    assert with_question("어디 살아요?", "region") == "어디 살아요?"
    assert with_question("좋아요!", None) == "좋아요!"
    step = {"title": "예비군 훈련 참여", "action": "일정을 확인하세요"}
    assert (
        with_next_step("굿!", step) == "굿! 다음은 '예비군 훈련 참여' 차례예요. 일정을 확인하세요"
    )
    # 이미 말했으면 덧붙이지 않는다
    assert with_next_step("이제 예비군 훈련 알아볼까요?", step) == "이제 예비군 훈련 알아볼까요?"


def test_nearly_same_titles_are_one_task():
    assert same_task("장병내일준비적금 수령", "장병내일준비적금 정부지원금 수령")
    assert same_task("국민취업지원제도", "국민취업지원제도 신청")
    assert not same_task("청년 월세 지원", "청년 마음건강 지원")


def test_questions_about_how_or_eligibility_always_search():
    assert needs_research("예비군 훈련, 어떻게 신청해요?")
    assert needs_research("국민취업지원제도 받을 수 있어요?")
    assert needs_research("서류는 뭐가 필요해요?")
    assert needs_research("혜택 알려줘")
    assert needs_research("전역했는데 뭐 받을 수 있어?")
    assert not needs_research("안녕하세요")
    assert not needs_research("서울 살아요")
    assert not needs_research("전역했는데 이제 뭐부터 해야 돼요?")  # 다음 임무 안내 요청
    assert not needs_research("국가유공자·보훈대상자예요")  # 첫 시작 버튼 말
    assert not needs_research("'예비군 훈련' 했어요")


def test_tasks_backed_only_by_portal_guides_are_dropped():
    # '정부24에서 혜택 조회하기'처럼 기관 안내만 근거인 할 일은 구체적인 제도가 아니다
    sources = [
        {"type": "institution", "title": "정부24 (보조금24)", "url": "https://www.gov.kr"},
        *SOURCES,
    ]
    draft = GuideDraft(
        say="",
        items=[
            PlanItemDraft(
                stage="right_after", title="정부24 혜택 조회", action="조회하세요", sources=[1]
            ),
            PlanItemDraft(
                stage="job", title="국민취업지원제도", action="신청하세요", sources=[1, 2]
            ),
        ],
    )
    picked = pick_items(draft, answer="", sources=sources, existing=[])
    assert [p["title"] for p in picked] == ["국민취업지원제도"]


def test_reopen_words_skip_research_and_find_done_item():
    from jeonyeok_helper.agents.guide import find_done, needs_research

    # '신청'이 들어 있어도 완료를 되돌려 달라는 말이면 검색으로 보내지 않는다
    assert not needs_research("실수로 했어요 눌렀어, 아직 신청 안 했어")
    assert needs_research("재취업 지원 어떻게 신청해요?")
    items = [
        {"id": "a", "title": "전역예정군인 재취업 지원", "done": True},
        {"id": "b", "title": "서울시 청년수당", "done": False},
    ]
    assert find_done(items, "전역예정군인 재취업 지원")["id"] == "a"
    assert find_done(items, "서울시 청년수당") is None  # 안 끝낸 일은 되돌릴 게 없다
    assert find_done(items, "") is None


def test_coach_prompt_tells_off_topic_input_apart_from_greeting():
    from jeonyeok_helper.agents.guide import COACH_PROMPT

    system = COACH_PROMPT.messages[0].prompt.template
    assert "인사로 착각하지" in system and "도울 수 없어요" in system


def test_coach_prompt_asks_back_when_the_referent_is_missing():
    from jeonyeok_helper.agents.guide import COACH_PROMPT

    system = COACH_PROMPT.messages[0].prompt.template
    assert "'그거', '이거'" in system and "기관을 지어내지 말 것" in system


def test_vague_first_turn_is_not_sent_to_search():
    from jeonyeok_helper.agents.guide import is_vague_first_turn, needs_research

    assert needs_research("그거 신청 어디서 해요?")  # 낱말만 보면 검색으로 가지만
    assert is_vague_first_turn("그거 신청 어디서 해요?", turns=1)  # 첫 마디면 되물어야 한다
    assert not is_vague_first_turn("그거 신청 어디서 해요?", turns=3)  # 앞 대화가 있으면 아니다
    assert not is_vague_first_turn("군복무 크레딧 신청 어디서 해요?", turns=1)
