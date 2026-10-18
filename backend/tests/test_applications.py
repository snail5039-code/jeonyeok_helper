"""신청 서류 도우미: 제도 찾기, 내 정보로 채우기, 관할 보훈청, 마감일, API, 길잡이 버튼."""

import pytest
from test_api import make_client

from jeonyeok_helper import applications
from jeonyeok_helper.agents import guide as guide_rules
from jeonyeok_helper.agents.state import Route

FIVE = {
    "transition_allowance",
    "merit_registration",
    "reserve_postpone",
    "military_credit",
    "employment_support",
}


def test_five_programs_with_sources_and_documents():
    programs = applications.load_programs()
    assert {p.id for p in programs} == FIVE
    for p in programs:
        assert p.documents and p.steps and p.sources, p.id
        assert any(d.by == "me" for d in p.documents), p.id
        assert p.submit.office or p.submit.where, p.id


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("전직지원금 신청할래요", "transition_allowance"),
        ("전직 지원금 서류 뭐 필요해요?", "transition_allowance"),
        ("국가유공자 등록 어떻게 해요", "merit_registration"),
        ("예비군 훈련 연기하고 싶어요", "reserve_postpone"),
        ("군복무 크레딧 신청 방법", "military_credit"),
        ("국민취업지원제도 신청하려고요", "employment_support"),
        ("전직지원금 얼마나 줘요?", None),  # 금액만 묻는 말은 신청이 아니다
        ("출산 크레딧 신청", None),  # 군 복무 크레딧이 아니다
        ("전역하면 뭐 받아요?", None),
    ],
)
def test_asked_to_apply(text, expected):
    found = applications.asked_to_apply(text)
    assert (found.id if found else None) == expected


def test_kit_fills_my_profile_and_finds_my_office():
    program = applications.get_program("transition_allowance")
    profile = {
        "service_type": "long_term",
        "service_years": 7.0,  # 저장된 값은 소수
        "discharge_date": "2026-09",
        "region": "부산 해운대",
        "rank": "중사",
    }
    kit = applications.build_kit(program, profile)
    form = {f["label"]: f for f in kit["form"]}
    assert form["복무 형태"]["value"] == "중·장기복무 간부 (5년 이상)"
    assert form["복무 기간"]["value"] == "7년"
    assert form["계급"]["value"] == "중사"
    assert form["군"]["value"] == "" and form["군"]["hint"] == "내 정보에 넣으면 채워져요"
    assert form["이름·주민등록번호·연락처"]["hint"] == "신청서에 직접 적어요"
    assert kit["fit"]["level"] == "ok"
    assert [o["name"] for o in kit["submit"]["offices"]] == ["부산지방보훈청"]
    # 전역 2026-09 + 6개월 → 2027-03 말
    assert kit["deadline"]["date"] == "2027-03-31"
    assert {d["by"] for d in kit["documents"]} == {"me", "office"}


def test_fit_warns_when_service_type_does_not_match():
    program = applications.get_program("transition_allowance")
    assert applications.fit(program, {"service_type": "conscript"})["level"] == "unlikely"
    assert applications.fit(program, {})["level"] == "check"
    merit = applications.get_program("merit_registration")
    assert applications.fit(merit, {"service_type": "conscript"})["level"] == "check"
    hurt = {"service_type": "conscript", "injury": "무릎"}
    assert applications.fit(merit, hurt)["level"] == "ok"


def test_kit_without_profile_still_works():
    kit = applications.build_kit(applications.get_program("reserve_postpone"), None)
    assert kit["deadline"]["date"] is None
    assert kit["submit"]["offices"] == []
    assert kit["submit"]["where"].startswith("소속 예비군부대")


def test_guide_offers_kit_button():
    assert guide_rules.kit_replies("전직지원금 신청할래요") == [
        {"label": "전직지원금 서류 챙기기", "open": "kit:transition_allowance"}
    ]
    assert guide_rules.kit_replies("오늘 날씨 어때요") == []


def test_application_api():
    with make_client([Route(next="answer")]) as client:
        listed = client.get("/applications").json()["programs"]
        client.put("/profile/u1", json={"service_type": "long_term", "region": "서울 송파구"})
        kit = client.get("/applications/transition_allowance", params={"user_id": "u1"}).json()
        missing = client.get("/applications/nothing")
        bad_user = client.get("/applications/transition_allowance", params={"user_id": "a/b"})
    assert {p["id"] for p in listed} == FIVE
    assert kit["fit"]["level"] == "ok"
    assert [o["name"] for o in kit["submit"]["offices"]] == ["서울지방보훈청"]
    assert missing.status_code == 404 and bad_user.status_code == 422
