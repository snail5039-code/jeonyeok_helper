"""전역도우미 MCP 서버.

에이전트(3단계)와 Claude Desktop 같은 MCP 클라이언트가 같은 도구를 표준 방식으로 쓰게 한다.

    uv run jeonyeok-mcp            # stdio로 실행

도구
- search_regulations : 법령·보훈부 자료 검색 (RAG)
- search_benefits    : 공공서비스(혜택) 조회
- get_benefit_detail : 혜택 상세
- search_jobs        : 제대군인지원센터 채용공고
- search_veteran_jobs : 보훈관서 채용정보 (보훈특별고용, 공무원 특별채용)
- find_stores        : 병무청 나라사랑가게 (병역이행자 할인)
- search_youth_policies : 온통청년 청년정책
- find_veterans_office : 관할 지방보훈청·보훈지청
- find_hospitals     : 지역별 보훈 위탁병원
- find_institutions  : 관련 기관 링크·연락처

외부 API가 실패하면 예외 대신 error와 대체 안내(fallback 기관 링크)를 돌려준다.
"""

from __future__ import annotations

import asyncio
import functools
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mcp.server.fastmcp import FastMCP

from jeonyeok_helper.benefits.common import CLOSED_NOTE, BenefitApiError, period_closed
from jeonyeok_helper.benefits.gov24 import Gov24Client
from jeonyeok_helper.benefits.hospitals import HospitalClient
from jeonyeok_helper.benefits.institutions import Institution, InstitutionDirectory
from jeonyeok_helper.benefits.jobs import NATIONWIDE, VnetJobClient
from jeonyeok_helper.benefits.offices import find_offices, load_offices
from jeonyeok_helper.benefits.stores import StoreClient
from jeonyeok_helper.benefits.veteran_jobs import VeteranJobClient
from jeonyeok_helper.benefits.youth import YouthPolicyClient
from jeonyeok_helper.config import get_settings

# 병무청 나라사랑가게 안내 (대상, 이용 방법)
STORE_INFO_URL = "https://www.mma.go.kr/contents.do?mc=mma0003356"

# 혜택 조회가 안 될 때 직접 찾아볼 수 있는 곳
FALLBACK_INSTITUTION_IDS = ["gov24", "youth", "vnet"]


def _with_key(client_cls: Callable[[str], Any], setting: str) -> Callable[[], Any]:
    """설정의 키로 클라이언트를 만드는 팩토리. 키는 처음 쓸 때 읽는다."""
    return lambda: client_cls(getattr(get_settings(), setting))


def _default_retriever():
    from jeonyeok_helper.rag.retriever import build_default_retriever

    return build_default_retriever()


def _default_directory() -> InstitutionDirectory:
    from jeonyeok_helper.benefits.institutions import get_directory

    return get_directory()


@dataclass
class Services:
    """도구가 쓰는 의존성. 처음 쓸 때 만들어서 키가 없어도 서버는 뜬다. 테스트에서 교체 가능."""

    gov24_factory: Callable[[], Gov24Client] = _with_key(Gov24Client, "data_go_kr_service_key")
    retriever_factory: Callable[[], Any] = _default_retriever
    directory_factory: Callable[[], InstitutionDirectory] = _default_directory
    hospitals_factory: Callable[[], HospitalClient] = _with_key(
        HospitalClient, "data_go_kr_service_key"
    )
    jobs_factory: Callable[[], VnetJobClient] = VnetJobClient
    veteran_jobs_factory: Callable[[], VeteranJobClient] = VeteranJobClient
    stores_factory: Callable[[], StoreClient] = _with_key(StoreClient, "data_go_kr_service_key")
    youth_factory: Callable[[], YouthPolicyClient] = _with_key(
        YouthPolicyClient, "youthcenter_api_key"
    )
    _cache: dict[str, Any] = field(default_factory=dict)

    def _get(self, name: str, factory: Callable[[], Any]) -> Any:
        if name not in self._cache:
            self._cache[name] = factory()
        return self._cache[name]

    @property
    def gov24(self) -> Gov24Client:
        return self._get("gov24", self.gov24_factory)

    @property
    def youth(self) -> YouthPolicyClient:
        return self._get("youth", self.youth_factory)

    @property
    def stores(self) -> StoreClient:
        return self._get("stores", self.stores_factory)

    @property
    def jobs(self) -> VnetJobClient:
        return self._get("jobs", self.jobs_factory)

    @property
    def veteran_jobs(self) -> VeteranJobClient:
        return self._get("veteran_jobs", self.veteran_jobs_factory)

    @property
    def hospitals(self) -> HospitalClient:
        return self._get("hospitals", self.hospitals_factory)

    @property
    def retriever(self):
        return self._get("retriever", self.retriever_factory)

    @property
    def directory(self) -> InstitutionDirectory:
        return self._get("directory", self.directory_factory)


# 5년 이상 복무자 전용 혜택. 병사·단기 간부에게 안내하면 틀린 안내가 된다.
_LONG_TERM_ONLY = re.compile(r"중\s?[.·ㆍ]?\s?장기|장기\s?복무")
# 보훈대상자(국가유공자·보훈가족 등) 전용 혜택. 이름에 있으면 보훈대상자가 아닌 사람에게는 빼고,
# 이름에 '제대군인'이 같이 있으면(제대군인도 대상) 남긴다.
_MERIT_ONLY = re.compile(
    r"보훈\s?(가족|대상자|명예|수당|급여)|국가유공|참전|독립유공|고엽제|유족|상이(군경|자)"
)


def fits_service_type(benefit: Any, service_type: str | None) -> bool:
    """대상이 사용자 복무 형태와 다른 혜택이면 False. 모르면 모두 통과."""
    if service_type is None or service_type == "merit":
        return True
    if service_type in ("conscript", "short_term_officer") and _LONG_TERM_ONLY.search(
        f"{benefit.name} {benefit.target}"
    ):
        return False
    return not (_MERIT_ONLY.search(benefit.name) and "제대군인" not in benefit.name)


def threaded(fn: Callable[..., dict]) -> Callable[..., Any]:
    """도구 본문(HTTP 호출, 벡터 검색, LLM 호출)은 동기 코드라 이벤트 루프를 막는다.
    스레드에서 돌려야 동시에 실행된 워커들(규정 + 혜택)이 서로를 기다리지 않는다."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> dict:
        return await asyncio.to_thread(fn, *args, **kwargs)

    return wrapper


def _institution_dict(inst: Institution) -> dict:
    return inst.model_dump(include={"name", "url", "phone", "description"}, exclude_none=True)


def create_server(services: Services | None = None) -> FastMCP:
    svc = services or Services()
    server = FastMCP(
        name="jeonyeok_helper",
        # 기본(INFO)은 도구를 부를 때마다 로그를 남겨 대화 출력이 지저분해진다.
        log_level="WARNING",
        instructions=(
            "군 전역자의 혜택, 근거 규정, 신청 기관을 찾는 도구 모음입니다. "
            "답변에는 반드시 도구가 돌려준 출처(citation, url)를 붙이세요."
        ),
    )

    def fallback(topic: str = "", limit: int = 4) -> list[dict]:
        """직접 찾아볼 수 있는 기관. 질문 주제에 맞는 기관(취업 → 고용24)을 앞에 둔다."""
        by_id = {i.id: i for i in svc.directory.institutions}
        picked = svc.directory.find(topic, limit=2) if topic else []
        picked += [by_id[i] for i in FALLBACK_INSTITUTION_IDS if i in by_id]
        unique = list({i.id: i for i in picked}.values())
        return [_institution_dict(i) for i in unique[:limit]]

    @server.tool()
    @threaded
    def search_regulations(question: str, k: int = 5, region: str | None = None) -> dict:
        """전역자 관련 법령, 시행령, 국가보훈부 자료에서 질문의 근거가 되는 조문·문단을 찾는다.

        region(예: '부산', '경기 포천')을 주면 그 지역 지자체 조례도 함께 찾는다.
        """
        try:
            docs = svc.retriever.retrieve(question, k=k, region=region)
        except RuntimeError as e:  # API 키 누락 등
            return {"results": [], "error": str(e)}
        return {
            "results": [
                {
                    "citation": d.metadata.get("citation", ""),
                    "url": d.metadata.get("url", ""),
                    "enforced_at": d.metadata.get("enforced_at", ""),
                    "text": d.page_content,
                }
                for d in docs
            ]
        }

    @server.tool()
    @threaded
    def search_benefits(
        keywords: list[str] | None = None,
        region: str | None = None,
        limit: int = 10,
        service_type: str | None = None,
    ) -> dict:
        """정부24 공공서비스(혜택)에서 전역자 관련 혜택을 찾는다.

        keywords를 비우면 제대군인, 전역, 장병, 군복무, 국가유공자, 보훈으로 검색한다.
        region(예: '서울', '경기도')을 주면 다른 지역 지자체 혜택은 뺀다.
        service_type(conscript, short_term_officer, long_term, merit)을 주면 대상이
        다른 혜택(예: 병사에게 중·장기복무 전용)은 뺀다.
        """
        try:
            benefits = svc.gov24.search(
                keywords=keywords,
                region=region,
                limit=limit * 2,
                prefer_youth=service_type in (None, "conscript", "short_term_officer"),
            )
        except BenefitApiError as e:
            return {"benefits": [], "error": str(e), "fallback": fallback(" ".join(keywords or []))}
        benefits = [b for b in benefits if fits_service_type(b, service_type)][:limit]

        results = []
        for b in benefits:
            item = b.model_dump(
                include={
                    "service_id",
                    "name",
                    "summary",
                    "target",
                    "content",
                    "how_to_apply",
                    "deadline",
                    "agency",
                    "contact",
                    "url",
                }
            )
            if inst := svc.directory.for_agency(b.agency):
                item["institution"] = _institution_dict(inst)
            if period_closed(b.deadline):
                item["deadline"] += CLOSED_NOTE
            results.append(item)
        return {"benefits": results}

    @server.tool()
    @threaded
    def get_benefit_detail(service_id: str) -> dict:
        """search_benefits로 찾은 혜택의 선정기준, 구비서류, 신청방법 등 상세 정보."""
        try:
            benefit = svc.gov24.get_detail(service_id)
        except BenefitApiError as e:
            return {"error": str(e), "fallback": fallback()}
        if benefit is None:
            return {"error": f"서비스ID {service_id}를 찾지 못했습니다."}
        return benefit.model_dump(exclude={"agency_type"})

    @server.tool()
    @threaded
    def search_jobs(region: str | None = None, keyword: str | None = None, limit: int = 10) -> dict:
        """제대군인지원센터(브이넷)의 마감 전 채용공고. region은 시도(예: '부산'),
        keyword는 공고 제목·회사명에서 찾을 단어(예: '경비', '시설', '공사')."""
        try:
            jobs = svc.jobs.search(region=region, keyword=keyword, limit=limit)
        except BenefitApiError as e:
            return {"jobs": [], "error": str(e), "fallback": fallback("취업")}
        # 전국 공고는 따로 둔다: 목록 끝에 섞어 두면 답변에서 빠지는 일이 많았다
        nationwide = [j.model_dump() for j in jobs if NATIONWIDE.search(f"{j.area} {j.title}")]
        local = [j.model_dump() for j in jobs if not NATIONWIDE.search(f"{j.area} {j.title}")]
        out: dict = {"jobs": local}
        if nationwide:
            out["nationwide_jobs"] = nationwide
            out["nationwide_note"] = "지역과 관계없이 어디서나 지원할 수 있는 전국 공고"
        return out

    @server.tool()
    @threaded
    def search_veteran_jobs(
        region: str | None = None,
        section: str | None = None,
        keyword: str | None = None,
        limit: int = 10,
    ) -> dict:
        """국가보훈부 보훈관서 채용정보의 마감 전 공고.

        section: '보훈특별고용'(국가유공자·10년 이상 장기복무 제대군인 등 취업지원대상자를
        공기업·기업체에 특별고용) 또는 '특별채용'(일반직공무원·군무원 특별채용). 비우면 둘 다.
        region은 근무지 시도(예: '부산'), keyword는 제목·회사명에서 찾을 단어(예: '경비').
        """
        try:
            jobs = svc.veteran_jobs.search(
                region=region, section=section, keyword=keyword, limit=limit
            )
        except BenefitApiError as e:
            return {"vacancies": [], "error": str(e), "fallback": fallback("취업")}
        return {
            "vacancies": [j.model_dump() for j in jobs],
            "note": "보훈특별고용은 취업지원대상자로 등록된 사람만 지원할 수 있다 (관할 보훈관서).",
        }

    @server.tool()
    @threaded
    def search_youth_policies(
        keyword: str | None = None,
        region: str | None = None,
        age: int | None = None,
        limit: int = 8,
    ) -> dict:
        """온통청년 청년정책(취업·주거·금융·교육 등). 병사 전역자 대부분이 청년이라 유용하다.

        keyword: 정책 이름·설명에서 찾을 단어(예: '주거', '취업', '월세'), 비우면 전체
        region: 사용자 지역(예: '부산'), age: 사용자 나이.
        군 복무 관련 조건이 있는 정책이 앞에 온다.
        """
        try:
            policies = svc.youth.search(keyword=keyword, region=region, age=age, limit=limit)
        except BenefitApiError as e:
            return {"policies": [], "error": str(e), "fallback": fallback("청년")}
        found = []
        for p in policies:
            item = p.model_dump(exclude={"sido_codes", "business_end", "policy_id"})
            if period_closed(p.apply_period):
                item["apply_period"] += CLOSED_NOTE
            found.append(item)
        return {"policies": found}

    @server.tool()
    @threaded
    def find_stores(region: str, keyword: str | None = None, limit: int = 10) -> dict:
        """병무청 나라사랑가게: 예비군 동원훈련 이수자, 현역병·사회복무요원, 병역명문가에게
        할인 등을 주는 가게. region은 필수(예: '부산 해운대'), keyword는 가게 이름(예: '안경')."""
        try:
            stores = svc.stores.find(region, keyword=keyword, limit=limit)
        except BenefitApiError as e:
            return {"stores": [], "error": str(e), "fallback": fallback("병역")}
        return {
            "stores": [s.model_dump() for s in stores],
            "info_url": STORE_INFO_URL,
        }

    @server.tool()
    @threaded
    def find_veterans_office(region: str) -> dict:
        """사용자 지역을 관할하는 지방보훈청·보훈지청의 주소, 전화, 누리집.
        보훈대상자 등록, 보훈급여, 제대군인 지원 상담은 관할 관서에서 한다.
        region 예: '부산 해운대'."""
        offices = find_offices(load_offices(), region)
        return {
            "offices": [o.model_dump(exclude={"regions"}) for o in offices],
            "note": "대표 상담전화 1577-0606 (국가보훈부 보훈상담센터)",
        }

    @server.tool()
    @threaded
    def find_hospitals(region: str, limit: int = 10) -> dict:
        """지역(예: '부산 해운대', '전남 강진')의 보훈 위탁병원(국가유공자 진료비 감면) 목록."""
        try:
            hospitals = svc.hospitals.find(region, limit=limit)
        except BenefitApiError as e:
            return {"hospitals": [], "error": str(e), "fallback": fallback("의료")}
        return {
            "hospitals": [
                {
                    "name": h.name,
                    "type": h.type,
                    "address": h.address,
                    "phone": h.phone,
                    "map_url": h.map_url,
                }
                for h in hospitals
            ]
        }

    @server.tool()
    @threaded
    def find_institutions(query: str, target: str | None = None) -> dict:
        """주제(예: '취업', '연금', '예비군')로 관련 기관의 사이트와 연락처를 찾는다.

        target: veteran_conscript(의무복무 전역자), short_term_officer(단기 간부),
        long_term(중·장기 제대군인), merit(보훈대상자)
        """
        found = svc.directory.find(query, target=target)
        return {"institutions": [_institution_dict(i) for i in found] or fallback()}

    return server


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
