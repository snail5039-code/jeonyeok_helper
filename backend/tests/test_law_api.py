import httpx
import pytest
import respx

from jeonyeok_helper.rag.law_api import (
    BASE_URL,
    LawApiClient,
    admin_rule_json_to_documents,
    interpretation_json_to_document,
    law_json_to_documents,
    ordinance_json_to_documents,
    region_keys,
)

SAMPLE_LAW = {
    "법령": {
        "기본정보": {
            "법령명_한글": "제대군인지원에 관한 법률",
            "법령ID": "001234",
            "시행일자": "20260101",
        },
        "조문": {
            "조문단위": [
                {"조문여부": "전문", "조문내용": "제1장 총칙"},
                {
                    "조문여부": "조문",
                    "조문번호": "1",
                    "조문제목": "목적",
                    "조문내용": "제1조(목적) 이 법은 제대군인의 사회복귀를 지원한다.",
                },
                {
                    "조문여부": "조문",
                    "조문번호": "2",
                    "조문제목": "정의",
                    "조문내용": "제2조(정의)",
                    # 항이 하나면 list가 아니라 dict로 오는 경우
                    "항": {
                        "항번호": "①",
                        "항내용": "① 이 법에서 사용하는 용어의 뜻은 다음과 같다.",
                        "호": [
                            {"호내용": '1. "제대군인"이란 ...'},
                            {
                                "호내용": '2. "장기복무 제대군인"이란 ...',
                                "목": {"목내용": "가. 10년 이상"},
                            },
                        ],
                    },
                },
                {
                    "조문여부": "조문",
                    "조문번호": "2",
                    "조문가지번호": "2",
                    "조문제목": "국가의 책무",
                    "조문내용": "제2조의2(국가의 책무) 국가는 ...",
                },
            ]
        },
    }
}


def test_law_json_to_documents_splits_by_article():
    docs = law_json_to_documents(SAMPLE_LAW)

    # '전문'(장 제목)은 문서가 아니라 메타데이터로만 쓰인다.
    assert [d.metadata["article"] for d in docs] == ["제1조", "제2조", "제2조의2"]
    assert all(d.metadata["chapter"] == "제1장 총칙" for d in docs)

    second = docs[1]
    assert second.metadata["law_name"] == "제대군인지원에 관한 법률"
    assert second.metadata["doc_id"] == "law:001234:제2조"
    # 항 → 호 → 목까지 순서대로 본문에 들어간다.
    assert "① 이 법에서" in second.page_content
    assert second.page_content.index('1. "제대군인"') < second.page_content.index("가. 10년 이상")


@respx.mock
def test_load_law_picks_current_exact_match():
    respx.get(f"{BASE_URL}/lawSearch.do").mock(
        return_value=httpx.Response(
            200,
            json={
                "LawSearch": {
                    "law": [
                        {"법령명한글": "제대군인지원에 관한 법률 시행령", "법령일련번호": "1"},
                        {
                            "법령명한글": "제대군인지원에 관한 법률",
                            "법령일련번호": "2",
                            "현행연혁코드": "현행",
                        },
                    ]
                }
            },
        )
    )
    service = respx.get(f"{BASE_URL}/lawService.do").mock(
        return_value=httpx.Response(200, json=SAMPLE_LAW)
    )

    docs = LawApiClient(oc="test").load_law("제대군인지원에 관한 법률")

    assert service.calls.last.request.url.params["MST"] == "2"
    assert len(docs) == 3


@respx.mock
def test_load_law_filters_articles():
    respx.get(f"{BASE_URL}/lawSearch.do").mock(
        return_value=httpx.Response(
            200, json={"LawSearch": {"law": {"법령명한글": "국민연금법", "법령일련번호": "9"}}}
        )
    )
    respx.get(f"{BASE_URL}/lawService.do").mock(return_value=httpx.Response(200, json=SAMPLE_LAW))

    docs = LawApiClient(oc="test").load_law("국민연금법", articles=["제2조의2"])

    assert [d.metadata["article"] for d in docs] == ["제2조의2"]
    assert docs[0].metadata["citation"].endswith("제2조의2(국가의 책무)")


def test_client_requires_oc():
    with pytest.raises(RuntimeError):
        LawApiClient(oc="")


# ---------- 자치법규(조례) ----------

SAMPLE_ORDINANCE = {
    "LawService": {
        "자치법규기본정보": {
            "자치법규ID": "2019663",
            "자치법규명": "가평군 국가보훈대상자 예우 및 지원에 관한 조례",
            "지자체기관명": "경기도 가평군",
            "시행일자": "20251231",
            "전화번호": "031-580-2210",
        },
        "조문": {
            "조": [
                {
                    "조문번호": ["000100", "000100"],
                    "조제목": "목적",
                    "조내용": "제1조(목적) 목적",
                    "조문여부": "Y",
                },
                {"조문번호": "000100", "조내용": "추가 내용", "조문여부": "Y"},
                {
                    "조문번호": "001002",
                    "조제목": "수당",
                    "조내용": "제10조의2(수당) 지급",
                    "조문여부": "Y",
                },
                {"조문번호": "000000", "조내용": "제1장 총칙", "조문여부": "N"},
            ]
        },
    }
}


def test_ordinance_json_to_documents_keeps_region():
    docs = ordinance_json_to_documents(SAMPLE_ORDINANCE)

    assert [d.metadata["article"] for d in docs] == ["제1조", "제10조의2"]  # 장 제목은 뺌
    meta = docs[1].metadata
    assert meta["source_type"] == "ordinance"
    assert (meta["sido"], meta["sigungu"]) == ("경기", "가평")
    assert meta["doc_id"] == "ordin:2019663:제10조의2"
    assert "경기도 가평군" in docs[1].page_content
    assert "추가 내용" in docs[0].page_content  # 같은 조문 번호는 하나로 합침


@pytest.mark.parametrize(
    "region, expected",
    [
        ("경기도 가평군", ["경기", "가평"]),
        ("부산광역시", ["부산"]),
        ("서울 중구", ["서울", "중구"]),
        ("포천시", ["포천"]),
        ("", []),
    ],
)
def test_region_keys(region, expected):
    assert region_keys(region) == expected


@respx.mock
def test_find_ordinances_filters_by_name_and_kind():
    respx.get(f"{BASE_URL}/lawSearch.do").mock(
        return_value=httpx.Response(
            200,
            json={
                "OrdinSearch": {
                    "law": [
                        {
                            "자치법규일련번호": "1",
                            "자치법규명": "A군 참전유공자 지원 조례",
                            "자치법규종류": "조례",
                        },
                        {
                            "자치법규일련번호": "2",
                            "자치법규명": "A군 보훈회관 운영 조례",
                            "자치법규종류": "조례",
                        },
                        {
                            "자치법규일련번호": "3",
                            "자치법규명": "A군 참전유공자 지원 조례 시행규칙",
                            "자치법규종류": "규칙",
                        },
                    ]
                }
            },
        )
    )
    found = LawApiClient("OC").find_ordinances(["보훈", "참전"], ["참전유공자", "보훈"], ["회관"])
    assert [i["자치법규일련번호"] for i in found] == ["1"]  # 키워드 두 개여도 중복 없이


# ---------- 행정규칙, 법령해석례 ----------


def test_admin_rule_json_to_documents_splits_articles():
    data = {
        "AdmRulService": {
            "행정규칙기본정보": {
                "행정규칙명": "제대군인 법률구조 지원 대상자 고시",
                "행정규칙ID": "9",
                "행정규칙종류": "고시",
                "소관부처명": "국가보훈부",
            },
            "조문내용": ["제1조(목적) 목적", "제2조의2(대상) 대상", "부칙 무시"],
        }
    }
    docs = admin_rule_json_to_documents(data)
    assert [d.metadata["article"] for d in docs] == ["제1조", "제2조의2"]
    assert docs[1].metadata["article_title"] == "대상"
    assert docs[1].metadata["doc_id"] == "admrul:9:제2조의2"


def test_interpretation_json_to_document():
    data = {
        "ExpcService": {
            "안건명": "제대군인 대부시 연금 담보 여부",
            "질의요지": "담보로 할 수 있는지",
            "회답": "담보로 제공할 수 없습니다.",
            "이유": "준용 규정이 없기 때문",
            "해석기관명": "법제처",
        }
    }
    doc = interpretation_json_to_document(data, "expc", "313097")
    assert "회답: 담보로 제공할 수 없습니다." in doc.page_content
    assert doc.metadata["url"].endswith("expcSeq=313097")
    assert doc.metadata["doc_id"] == "interp:expc:313097"
    # 부처 해석례는 공개 링크가 없다
    assert interpretation_json_to_document(data, "mndCgmExpc", "1").metadata["url"] == ""
    # 회답이 없으면 저장하지 않는다
    assert interpretation_json_to_document({"X": {"안건명": "a"}}, "expc", "1") is None
