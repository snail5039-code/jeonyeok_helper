"""전역도우미 MCP 서버.

에이전트(3단계)와 Claude Desktop 같은 MCP 클라이언트가 같은 도구를 표준 방식으로 쓰게 한다.

    uv run jeonyeok-mcp            # stdio로 실행

도구
- search_regulations : 법령·보훈부 자료 검색 (RAG)
- search_benefits    : 공공서비스(혜택) 조회
- get_benefit_detail : 혜택 상세
- find_institutions  : 관련 기관 링크·연락처

외부 API가 실패하면 예외 대신 error와 대체 안내(fallback 기관 링크)를 돌려준다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mcp.server.fastmcp import FastMCP

from jeonyeok_helper.benefits.gov24 import BenefitApiError, Gov24Client
from jeonyeok_helper.benefits.institutions import Institution, InstitutionDirectory

# 혜택 조회가 안 될 때 직접 찾아볼 수 있는 곳
FALLBACK_INSTITUTION_IDS = ["gov24", "youth", "vnet"]


def _default_gov24() -> Gov24Client:
    from jeonyeok_helper.config import get_settings

    return Gov24Client(get_settings().data_go_kr_service_key)


def _default_retriever():
    from jeonyeok_helper.rag.retriever import build_default_retriever

    return build_default_retriever()


def _default_directory() -> InstitutionDirectory:
    from jeonyeok_helper.benefits.institutions import get_directory

    return get_directory()


@dataclass
class Services:
    """도구가 쓰는 의존성. 처음 쓸 때 만들어서 키가 없어도 서버는 뜬다. 테스트에서 교체 가능."""

    gov24_factory: Callable[[], Gov24Client] = _default_gov24
    retriever_factory: Callable[[], Any] = _default_retriever
    directory_factory: Callable[[], InstitutionDirectory] = _default_directory
    _cache: dict[str, Any] = field(default_factory=dict)

    def _get(self, name: str, factory: Callable[[], Any]) -> Any:
        if name not in self._cache:
            self._cache[name] = factory()
        return self._cache[name]

    @property
    def gov24(self) -> Gov24Client:
        return self._get("gov24", self.gov24_factory)

    @property
    def retriever(self):
        return self._get("retriever", self.retriever_factory)

    @property
    def directory(self) -> InstitutionDirectory:
        return self._get("directory", self.directory_factory)


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
    def search_benefits(
        keywords: list[str] | None = None, region: str | None = None, limit: int = 10
    ) -> dict:
        """정부24 공공서비스(혜택)에서 전역자 관련 혜택을 찾는다.

        keywords를 비우면 제대군인, 전역, 장병, 군복무, 국가유공자, 보훈으로 검색한다.
        region(예: '서울', '경기도')을 주면 다른 지역 지자체 혜택은 뺀다.
        """
        try:
            benefits = svc.gov24.search(keywords=keywords, region=region, limit=limit)
        except BenefitApiError as e:
            return {"benefits": [], "error": str(e), "fallback": fallback(" ".join(keywords or []))}

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
            results.append(item)
        return {"benefits": results}

    @server.tool()
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
