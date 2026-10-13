import asyncio
import json
from datetime import date

import httpx
import pytest
import respx
from langchain_core.documents import Document

from jeonyeok_helper.benefits.common import BenefitApiError
from jeonyeok_helper.benefits.gov24 import BASE_URL, Benefit, Gov24Client, agency_in_region
from jeonyeok_helper.benefits.hospitals import BASE_URL as HOSPITAL_URL
from jeonyeok_helper.benefits.hospitals import HospitalClient
from jeonyeok_helper.benefits.institutions import InstitutionDirectory
from jeonyeok_helper.benefits.jobs import BASE_URL as JOBS_URL
from jeonyeok_helper.benefits.jobs import VnetJobClient
from jeonyeok_helper.benefits.mcp_server import Services, create_server, fits_service_type
from jeonyeok_helper.benefits.offices import VeteransOffice, find_offices, load_offices
from jeonyeok_helper.benefits.regions import normalize_region, region_keys
from jeonyeok_helper.benefits.stores import BASE_URL as STORES_URL
from jeonyeok_helper.benefits.stores import StoreClient
from jeonyeok_helper.benefits.youth import BASE_URL as YOUTH_URL
from jeonyeok_helper.benefits.youth import YouthPolicyClient


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

    detail = Benefit.from_api({"서비스ID": "1", "서비스명": "a", "법령": "제대군인지원법"})
    assert detail.laws == "제대군인지원법"  # 상세 응답의 근거 법령


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
            # 소관기관유형은 실제 API 값
            api_item("s", "전역 서울", "서울특별시 노원구", "시군구"),
            api_item("b", "전역 부산", "부산광역시", "광역시도"),
            api_item("p", "전역 포천", "경기도 포천시", "시군구"),
            api_item("u", "전역 공사", "부산교통공사", "지방공기업"),
            api_item("k", "전역 공단", "국민연금공단", "공공기관"),
        )
    )
    results = Gov24Client("KEY").search(keywords=["전역"], region="서울시")
    assert {b.service_id for b in results} == {"c", "s", "k"}


@respx.mock
def test_without_region_nationwide_benefits_come_first():
    respx.get(f"{BASE_URL}/serviceList").mock(
        return_value=page(
            api_item("s", "학자금 학자금 지원", "경기도 성남시", "시군구"),
            api_item("c", "학자금 대출", "교육부"),
        )
    )
    results = Gov24Client("KEY").search(keywords=["학자금"])
    assert [b.service_id for b in results] == ["c", "s"]


@pytest.mark.parametrize(
    "agency, region, expected",
    [
        ("부산광역시 해운대구", "부산", True),
        ("부산광역시 해운대구", "부산 해운대", True),  # 시군구까지 말해도 남는다
        ("부산광역시 해운대구", "부산광역시 해운대구", True),
        ("부산광역시 동래구", "부산 해운대", False),  # 같은 시도의 다른 구는 뺀다
        ("부산광역시", "부산 해운대", True),  # 시도 혜택은 남긴다
        ("부산교통공사", "부산 해운대", True),
        ("전남광주통합특별시 여수시", "전남", True),  # 2026 통합 후 표기
        ("전남광주통합특별시 여수시", "전라남도 여수시", True),
        ("경기도 포천시", "포천", True),  # 시군구만 말한 경우
        ("경기도 포천시", "서울", False),
        ("경상북도 포항시", "경북", True),
    ],
)
def test_agency_in_region(agency, region, expected):
    assert agency_in_region(agency, region_keys(region)) is expected


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

    def search(self, keywords=None, region=None, limit=10, prefer_youth=False):
        if self.fail:
            raise BenefitApiError("서비스키가 설정되지 않았습니다")
        return [Benefit.from_api(api_item("1", "제대군인 전직지원금", "국가보훈부 제대군인정책과"))]

    def get_detail(self, service_id):
        return None


class FakeRetriever:
    def retrieve(self, question, k=5, region=None):
        return [Document(page_content="본문", metadata={"citation": "병역법 제1조", "url": "u"})]


def make_server(fail: bool = False):
    return create_server(
        Services(
            gov24_factory=lambda: FakeGov24(fail),
            retriever_factory=FakeRetriever,
            directory_factory=InstitutionDirectory.from_yaml,
        )
    )


def test_server_exposes_all_tools():
    names = {t.name for t in asyncio.run(make_server().list_tools())}
    assert names == {
        "search_regulations",
        "search_benefits",
        "get_benefit_detail",
        "find_veterans_office",
        "find_hospitals",
        "search_jobs",
        "search_veteran_jobs",
        "find_stores",
        "search_youth_policies",
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


# ---------- 보훈 위탁병원 ----------


def hospital(name: str, addr1: str, use_yn: str = "Y") -> dict:
    return {
        "name": name,
        "addr1": addr1,
        "addr2": "1번길",
        "tel": "000",
        "type": "병원",
        "latitude": "35.1",
        "longitude": "129.0",
        "use_yn": use_yn,
    }


@respx.mock
def test_hospitals_are_fetched_once_and_filtered_by_region():
    route = respx.get(HOSPITAL_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "totalCount": 4,
                "data": [
                    hospital("해운대병원", "부산 해운대구"),
                    hospital("강진의료원", "전남 강진군"),
                    hospital("폐업병원", "부산 해운대구", use_yn="N"),
                    hospital("서울병원", "서울 강남구"),
                ],
            },
        )
    )
    client = HospitalClient("KEY")

    assert [h.name for h in client.find("부산광역시 해운대구")] == ["해운대병원"]  # 폐업 제외
    assert [h.name for h in client.find("전라남도")] == ["강진의료원"]  # '전남'으로 줄여 쓴 주소
    assert client.find("") == []
    assert route.call_count == 1  # 전체 목록은 캐시
    assert client.find("부산")[0].map_url.startswith("https://map.kakao.com/link/map/해운대병원,")


# ---------- 제대군인지원센터 채용정보 ----------

JOBS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<root><total_count>3</total_count><articles>
<item><company>A공사</company><link>https://vnet.go.kr/1</link><contents>시설 경비원</contents>
<area>부산</area><pay/><regdate>2026-10-01</regdate><enddate>2026-10-20</enddate></item>
<item><company>B</company><link>https://vnet.go.kr/2</link><contents>사무직</contents>
<area>부산</area><pay>월 250만원</pay><regdate>2026-10-05</regdate>
<enddate>2026-10-30</enddate></item>
<item><company>C</company><link>https://vnet.go.kr/3</link><contents>마감된 공고</contents>
<area>부산</area><pay/><regdate>2026-09-01</regdate><enddate>2026-09-30</enddate></item>
</articles></root>"""


@respx.mock
def test_jobs_use_verified_location_code_and_hide_closed():
    route = respx.get(JOBS_URL).mock(return_value=httpx.Response(200, text=JOBS_XML))
    client = VnetJobClient()
    today = date(2026, 10, 12)

    jobs = client.search(region="부산광역시", today=today)

    assert route.calls[0].request.url.params["location"] == "2"  # 안내 페이지 표로는 4
    assert [j.company for j in jobs] == ["B", "A공사"]  # 마감 제외, 최신순
    assert [j.company for j in client.search(region="부산", keyword="경비", today=today)] == [
        "A공사"
    ]
    assert route.call_count == 1  # 지역별 캐시


# ---------- 나라사랑가게 ----------


def stores_page(*items: tuple[str, str], total: int) -> str:
    rows = "".join(
        f"<item><udaeGgm>{n}</udaeGgm><gtcdNm>할인</gtcdNm><juso>{a}</juso>"
        f"<udgigwanTelno>000</udgigwanTelno></item>"
        for n, a in items
    )
    return (
        "<response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>"
        f"<body><items>{rows}</items><totalCount>{total}</totalCount></body></response>"
    )


@respx.mock
def test_stores_are_paged_cached_and_filtered(monkeypatch):
    monkeypatch.setattr("jeonyeok_helper.benefits.stores.PAGE_SIZE", 2)
    route = respx.get(STORES_URL).mock(
        side_effect=[
            httpx.Response(
                200,
                text=stores_page(
                    ("다비치안경 해운대점", "부산광역시해운대구 1"),
                    ("포항 영화관", "경상북도포항시 북구"),
                    total=3,
                ),
            ),
            httpx.Response(200, text=stores_page(("해운대 식당", "부산광역시해운대구 2"), total=3)),
        ]
    )
    client = StoreClient("KEY")

    assert [s.name for s in client.find("부산 해운대")] == ["다비치안경 해운대점", "해운대 식당"]
    assert [s.name for s in client.find("경북")] == ["포항 영화관"]  # '경상북도' 표기
    assert [s.name for s in client.find("부산", keyword="안경")] == ["다비치안경 해운대점"]
    assert route.call_count == 2  # 두 페이지를 받은 뒤 캐시


@respx.mock
def test_stores_api_error_code_raises():
    respx.get(STORES_URL).mock(
        return_value=httpx.Response(
            200,
            text="<response><header><resultCode>30</resultCode>"
            "<resultMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</resultMsg></header></response>",
        )
    )
    with pytest.raises(BenefitApiError, match="SERVICE_KEY"):
        StoreClient("KEY").all()


# ---------- 온통청년 청년정책 ----------

ALL_SIDO = ",".join(f"{c}110" for c in ("11", "26", "27", "28", "29", "30", "31", "36", "41", "43"))


def policy(no, name, zips, *, condition="", end="", min_age=19, max_age=34, explain="지원"):
    return {
        "plcyNo": no,
        "plcyNm": name,
        "plcyExplnCn": explain,
        "zipCd": zips,
        "addAplyQlfcCndCn": condition,
        "bizPrdEndYmd": end,
        "sprtTrgtMinAge": str(min_age),
        "sprtTrgtMaxAge": str(max_age),
        "sprtTrgtAgeLmtYn": "N",
        "sprvsnInstCdNm": "기관",
    }


@respx.mock
def test_youth_policies_filter_by_region_age_and_put_military_first():
    route = respx.get(YOUTH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "resultCode": 200,
                "result": {
                    "pagging": {"totCount": 6},
                    "youthPolicyList": [
                        policy("1", "전국 주거 지원", ALL_SIDO, explain="월세 주거"),
                        policy("2", "부산 주거 지원", "26110,26140", explain="월세 주거"),
                        policy("3", "서울 주거 지원", "11110", explain="월세 주거"),
                        policy("4", "끝난 주거 사업", "26110", end="20260101", explain="주거"),
                        policy("5", "중년 주거", "26110", min_age=40, max_age=49, explain="주거"),
                        policy("6", "청년 취업", ALL_SIDO, condition="군 복무자는 연령 연장"),
                    ],
                },
            },
        )
    )
    client = YouthPolicyClient("KEY")
    today = date(2026, 10, 12)

    found = client.search(keyword="주거", region="부산광역시", age=25, today=today)
    # 서울 정책·끝난 사업·나이 안 맞는 정책은 빼고, 지역 정책이 전국 정책보다 앞
    assert [p.name for p in found] == ["부산 주거 지원", "전국 주거 지원"]
    # 키워드가 없으면 군 복무 조건이 있는 정책이 가장 앞
    assert client.search(region="부산", age=25, today=today)[0].name == "청년 취업"
    assert route.call_count == 1  # 전체 목록은 캐시
    assert route.calls[0].request.headers["User-Agent"] == "Mozilla/5.0"


@respx.mock
def test_youth_api_error_does_not_leak_key():
    respx.get(YOUTH_URL).mock(return_value=httpx.Response(403))
    with pytest.raises(BenefitApiError) as err:
        YouthPolicyClient("SECRET-KEY").all()
    assert "SECRET-KEY" not in str(err.value) and "403" in str(err.value)


@respx.mock
def test_youth_api_retries_temporary_errors():
    ok = {
        "resultCode": 200,
        "result": {"pagging": {"totCount": 1}, "youthPolicyList": [{"plcyNo": "1", "plcyNm": "a"}]},
    }
    route = respx.get(YOUTH_URL).mock(
        side_effect=[httpx.Response(500), httpx.Response(400), httpx.Response(200, json=ok)]
    )
    assert [p.name for p in YouthPolicyClient("KEY", retry_wait=0).all()] == ["a"]
    assert route.call_count == 3


# ---------- 지방보훈관서 ----------


def test_veterans_offices_file_is_complete():
    offices = load_offices()
    assert len(offices) == 27
    assert all(o.address and o.phone and o.regions for o in offices)


@pytest.mark.parametrize(
    "region, expected",
    [
        ("부산 해운대구", ["부산청"]),  # 시도 전체 관할
        ("경기 포천", ["경기북부"]),
        ("포천시", ["경기북부"]),  # 시군구만 말해도
        ("광주 광산구", ["광주청"]),  # '경기 광주시'에 걸리면 안 됨
        ("경기 광주시", ["경기동부"]),
        ("전남 순천", ["전남동부"]),  # 전남광주통합특별시 표기
        ("경기", ["경기북부", "경기동부"]),  # 시도만 알면 그 시도 관서 모두
        ("", []),
    ],
)
def test_find_offices_by_region(region, expected):
    offices = [
        VeteransOffice(name="부산청", regions=["부산"]),
        VeteransOffice(name="경기북부", regions=["경기 포천시", "경기 의정부시"]),
        VeteransOffice(name="경기동부", regions=["경기 광주시", "경기 용인시"]),
        VeteransOffice(
            name="광주청", regions=["전남광주통합특별시 광산구", "전남광주통합특별시 북구"]
        ),
        VeteransOffice(name="전남동부", regions=["전남광주통합특별시 순천시"]),
    ]
    assert [o.name for o in find_offices(offices, region)] == expected


@pytest.mark.parametrize(
    "name, target, service_type, expected",
    [
        ("중.장기복무 전역예정군인 전직교육서비스", "", "conscript", False),
        ("전직지원금", "중장기복무 제대군인", "short_term_officer", False),
        ("장기복무 제대군인 대부", "", "conscript", False),
        ("중.장기복무 전역예정군인 전직교육서비스", "", "long_term", True),
        ("전역예정장병 취업활동지원", "전역 예정 장병", "conscript", True),
        ("중.장기복무 전역예정군인 전직교육서비스", "", None, True),  # 모르면 그대로
        ("보훈가족 심리재활서비스 지원", "", "conscript", False),  # 보훈대상자 전용
        ("국가유공자 차량취득세 감면", "", "long_term", False),
        ("국가유공자 차량취득세 감면", "", "merit", True),
        ("제대군인 및 국가유공자 취업지원", "", "conscript", True),  # 제대군인도 대상
        ("국가유공상이자 등 교통시설 이용지원", "", "conscript", False),  # '국가유공상이자' 표기
    ],
)
def test_benefits_for_other_service_types_are_dropped(name, target, service_type, expected):
    benefit = Benefit(service_id="1", name=name, target=target)
    assert fits_service_type(benefit, service_type) is expected


# ---------- 보훈관서 채용정보 ----------

VACANCIES_XML = """<?xml version="1.0" encoding="euc-kr"?>
<vacancies><total_count>2</total_count>
<vacancy><r_company>부산교통공사</r_company><r_title>도시철도 보안관 보훈특별고용</r_title>
<r_section>보훈특별고용</r_section><r_work_place>
  부산
</r_work_place><reg_date>2026-10-08</reg_date><end_date>2026-10-22</end_date>
<link>https://job.mpva.go.kr/govRecurit/speclEmpmnView.do?rIdx=1&amp;menuKey=147</link></vacancy>
<vacancy><r_company>지난회사</r_company><r_title>마감된 공고</r_title>
<r_section>보훈특별고용</r_section><end_date>2026-10-01</end_date></vacancy>
</vacancies>"""


@respx.mock
def test_veteran_jobs_use_place_codes_and_drop_closed():
    from jeonyeok_helper.benefits.veteran_jobs import BASE_URL as VJ_URL
    from jeonyeok_helper.benefits.veteran_jobs import VeteranJobClient

    route = respx.get(VJ_URL).mock(
        return_value=httpx.Response(200, content=VACANCIES_XML.encode("euc-kr"),
                                    headers={"content-type": "text/xml;charset=euc-kr"})
    )  # fmt: skip
    jobs = VeteranJobClient().search(
        region="부산 해운대", section="보훈특별고용", today=date(2026, 10, 12)
    )
    assert [j.company for j in jobs] == ["부산교통공사"]  # 마감 지난 공고는 뺀다
    assert jobs[0].area == "부산" and "rIdx=1" in jobs[0].url
    params = route.calls[0].request.url.params
    assert params["place"] == "d" and params["section"] == "a"

    VeteranJobClient().search(today=date(2026, 10, 12))  # 지역을 모르면 전국
    assert route.calls[-1].request.url.params["place"] == "z"


@respx.mock
def test_search_puts_youth_programs_first_on_ties_for_young_users():
    respx.get(f"{BASE_URL}/serviceList").mock(
        return_value=page(api_item("loan", "주택 월세대출"), api_item("youth", "청년월세 지원"))
    )
    client = Gov24Client("KEY")
    assert [b.service_id for b in client.search(keywords=["월세"])] == ["loan", "youth"]
    young = client.search(keywords=["월세"], prefer_youth=True)
    assert [b.service_id for b in young] == ["youth", "loan"]
