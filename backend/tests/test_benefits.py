import asyncio
import json

import httpx
import pytest
import respx
from langchain_core.documents import Document

from jeonyeok_helper.benefits.gov24 import (
    BASE_URL,
    Benefit,
    BenefitApiError,
    Gov24Client,
    normalize_region,
)
from jeonyeok_helper.benefits.institutions import InstitutionDirectory
from jeonyeok_helper.benefits.mcp_server import Services, create_server


def api_item(sid: str, name: str, agency: str = "국가보훈부", agency_type: str = "중앙행정기관"):
    return {
        "서비스ID": sid,
        "서비스명": name,
        "서비스목적요약": f"{name} 요약",
        "지원대상": "제대군인",
        "소관기관명": agency,
        "소관기관유형": agency_type,
        "상세조회URL": f"https://www.gov.kr/{sid}",
    }


def page(*items):
    return httpx.Response(200, json={"currentCount": len(items), "data": list(items)})


# ---------- 공공서비스 API ----------


def test_benefit_from_api_maps_fields_and_fills_url():
    b = Benefit.from_api({"서비스ID": "123", "서비스명": "전직지원금", "문의처": "1577-0606"})
    assert b.name == "전직지원금"
    assert b.contact == "1577-0606"  # 상세 응답의 필드 이름도 인식
    assert b.url.endswith("/123")  # 상세 URL이 없으면 정부24 주소로 채움


@respx.mock
def test_search_sends_like_condition_and_dedupes():
    route = respx.get(f"{BASE_URL}/serviceList").mock(
        side_effect=lambda req: page(
            api_item("1", "제대군인 전직지원금"), api_item("2", "보훈 교육 지원")
        )
    )

    results = Gov24Client("KEY").search(keywords=["제대군인"])

    # 키워드 1개 × 검색 필드 2개(서비스명, 지원대상) = 2번 요청
    assert route.call_count == 2
    params = route.calls[0].request.url.params
    assert params["cond[서비스명::LIKE]"] == "제대군인"
    assert params["serviceKey"] == "KEY"
    # 같은 서비스는 한 번만, 서비스명에 키워드가 있는 것이 먼저
    assert [b.service_id for b in results] == ["1", "2"]


@respx.mock
def test_search_uses_cache():
    route = respx.get(f"{BASE_URL}/serviceList").mock(return_value=page(api_item("1", "a")))
    client = Gov24Client("KEY")
    client.search(keywords=["전역"])
    client.search(keywords=["전역"])
    assert route.call_count == 2  # 두 번째 검색은 캐시 사용


@respx.mock
def test_region_filter_keeps_central_and_matching_local():
    respx.get(f"{BASE_URL}/serviceList").mock(
        return_value=page(
            api_item("c", "전역 중앙"),
            api_item("s", "전역 서울", "서울특별시 청년정책과", "지방자치단체"),
            api_item("b", "전역 부산", "부산광역시", "지방자치단체"),
        )
    )
    results = Gov24Client("KEY").search(keywords=["전역"], region="서울시")
    assert {b.service_id for b in results} == {"c", "s"}


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("서울", "서울"),
        ("서울시", "서울"),
        ("서울특별시", "서울"),
        ("경기도", "경기"),
        ("충북", "충청북"),
        ("충청북도", "충청북"),
        ("전라북도", "전북"),
        ("제주특별자치도", "제주"),
    ],
)
def test_normalize_region(raw, expected):
    assert normalize_region(raw) == expected


def test_missing_key_raises_api_error():
    with pytest.raises(BenefitApiError, match="서비스키"):
        Gov24Client("").search()


@respx.mock
def test_partial_failure_returns_rest_but_total_failure_raises():
    respx.get(f"{BASE_URL}/serviceList").mock(
        side_effect=[page(api_item("1", "전역")), httpx.Response(500)]
    )
    assert [b.service_id for b in Gov24Client("KEY").search(keywords=["전역"])] == ["1"]

    respx.get(f"{BASE_URL}/serviceList").mock(return_value=httpx.Response(500))
    with pytest.raises(BenefitApiError):
        Gov24Client("KEY").search(keywords=["전역"])


# ---------- 기관 링크 ----------


def test_institutions_yaml_is_valid():
    d = InstitutionDirectory.from_yaml()
    ids = [i.id for i in d.institutions]
    assert len(ids) == len(set(ids))
    assert all(i.url.startswith("https://") for i in d.institutions)


def test_find_institutions_by_topic_and_target():
    d = InstitutionDirectory.from_yaml()
    assert d.find("군복무 크레딧 연금")[0].id == "nps"
    assert d.find("예비군")[0].id == "mma"
    # 장기 제대군인 대상이 아닌 기관은 빠진다
    assert "nps" not in [i.id for i in d.find("연금", target="long_term")]


def test_for_agency_matches_department_names():
    d = InstitutionDirectory.from_yaml()
    assert d.for_agency("국가보훈부 제대군인정책과").id == "mpva"
    assert d.for_agency("서울특별시 청년정책과") is None


# ---------- MCP 서버 ----------


def call(server, tool: str, args: dict) -> dict:
    content = asyncio.run(server.call_tool(tool, args))
    return json.loads(content[0].text)


class FakeGov24:
    def __init__(self, fail: bool = False):
        self.fail = fail

    def search(self, keywords=None, region=None, limit=10):
        if self.fail:
            raise BenefitApiError("서비스키가 설정되지 않았습니다")
        return [Benefit.from_api(api_item("1", "제대군인 전직지원금", "국가보훈부 제대군인정책과"))]

    def get_detail(self, service_id):
        return None


class FakeRetriever:
    def retrieve(self, question, k=5):
        return [Document(page_content="본문", metadata={"citation": "병역법 제1조", "url": "u"})]


def make_server(fail: bool = False):
    return create_server(
        Services(
            gov24_factory=lambda: FakeGov24(fail),
            retriever_factory=FakeRetriever,
            directory_factory=InstitutionDirectory.from_yaml,
        )
    )


def test_server_exposes_four_tools():
    names = {t.name for t in asyncio.run(make_server().list_tools())}
    assert names == {
        "search_regulations",
        "search_benefits",
        "get_benefit_detail",
        "find_institutions",
    }


def test_search_benefits_attaches_institution_link():
    out = call(make_server(), "search_benefits", {})
    assert out["benefits"][0]["institution"]["name"] == "국가보훈부"


def test_search_benefits_falls_back_to_links_on_api_error():
    out = call(make_server(fail=True), "search_benefits", {"region": "서울"})
    assert out["benefits"] == []
    assert "서비스키" in out["error"]
    assert {i["name"] for i in out["fallback"]} >= {"정부24 (보조금24)", "온통청년"}


def test_search_regulations_returns_citations():
    out = call(make_server(), "search_regulations", {"question": "예비군"})
    assert out["results"][0]["citation"] == "병역법 제1조"


def test_unknown_benefit_detail():
    out = call(make_server(), "get_benefit_detail", {"service_id": "x"})
    assert "찾지 못했습니다" in out["error"]


def test_fallback_puts_topic_institutions_first():
    out = call(make_server(fail=True), "search_benefits", {"keywords": ["취업", "구직"]})
    names = [i["name"] for i in out["fallback"]]
    assert names[0] == "고용24"
    assert "정부24 (보조금24)" in names  # 공통 안내도 함께
    assert len(names) == len(set(names)) <= 4
