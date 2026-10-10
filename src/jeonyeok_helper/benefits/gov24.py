"""공공데이터포털 '행정안전부_대한민국 공공서비스(혜택) 정보' API 클라이언트.

정부24·보조금24에 올라온 중앙부처·지자체·공공기관 혜택을 조회한다.

- 목록: GET https://api.odcloud.kr/api/gov24/v3/serviceList
- 상세: GET https://api.odcloud.kr/api/gov24/v3/serviceDetail
- 조건 검색: cond[필드명::LIKE]=값 (한 요청에 조건을 여러 개 주면 AND라서 키워드마다 따로 요청)

서비스키는 공공데이터포털의 '일반 인증키(Decoding)' 값을 쓴다.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel

log = logging.getLogger(__name__)

BASE_URL = "https://api.odcloud.kr/api/gov24/v3"

# 전역자 관련 혜택을 찾을 때 기본으로 쓰는 키워드
DEFAULT_KEYWORDS = ["제대군인", "전역", "장병", "군복무", "국가유공자", "보훈"]
SEARCH_FIELDS = ["서비스명", "지원대상"]

# 목록과 상세 응답의 필드 이름이 조금씩 달라서 후보를 순서대로 본다.
_FIELDS: dict[str, tuple[str, ...]] = {
    "service_id": ("서비스ID",),
    "name": ("서비스명",),
    "summary": ("서비스목적요약", "서비스목적"),
    "target": ("지원대상",),
    "criteria": ("선정기준",),
    "content": ("지원내용",),
    "how_to_apply": ("신청방법",),
    "deadline": ("신청기한",),
    "documents": ("구비서류",),
    "agency": ("소관기관명",),
    "agency_type": ("소관기관유형",),
    "reception": ("접수기관", "접수기관명"),
    "contact": ("전화문의", "문의처"),
    "url": ("상세조회URL", "온라인신청사이트URL"),
    "category": ("서비스분야",),
}


class Benefit(BaseModel):
    service_id: str
    name: str
    summary: str = ""
    target: str = ""
    criteria: str = ""
    content: str = ""
    how_to_apply: str = ""
    deadline: str = ""
    documents: str = ""
    agency: str = ""
    agency_type: str = ""
    reception: str = ""
    contact: str = ""
    url: str = ""
    category: str = ""

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> Benefit:
        values = {}
        for field, keys in _FIELDS.items():
            for key in keys:
                if item.get(key):
                    values[field] = str(item[key]).strip()
                    break
        if not values.get("url") and values.get("service_id"):
            values["url"] = f"https://www.gov.kr/portal/rcvfvrSvc/dtlEx/{values['service_id']}"
        return cls(**values)

    @property
    def is_local(self) -> bool:
        return "지방" in self.agency_type or "지자체" in self.agency_type


_REGION_ALIASES = {
    "충북": "충청북",
    "충남": "충청남",
    "전북": "전북",  # 2024년부터 전북특별자치도
    "전라북도": "전북",
    "전남": "전라남",
    "경북": "경상북",
    "경남": "경상남",
}
_REGION_SUFFIXES = ("특별자치시", "특별자치도", "특별시", "광역시", "도", "시")


def normalize_region(region: str) -> str:
    """'서울', '서울시', '서울특별시' → '서울' / '충북', '충청북도' → '충청북'."""
    region = region.strip()
    if region in _REGION_ALIASES:
        return _REGION_ALIASES[region]
    for suffix in _REGION_SUFFIXES:
        if region.endswith(suffix) and len(region) > len(suffix) + 1:
            return region.removesuffix(suffix)
    return region


class BenefitApiError(RuntimeError):
    pass


class Gov24Client:
    def __init__(
        self,
        service_key: str,
        client: httpx.Client | None = None,
        cache_ttl: float = 6 * 3600,
    ):
        self.service_key = service_key
        self.client = client or httpx.Client(timeout=20)
        self.cache_ttl = cache_ttl
        self._cache: dict[tuple, tuple[float, Any]] = {}

    def _get(self, path: str, params: dict[str, Any]) -> dict:
        if not self.service_key:
            raise BenefitApiError(
                "공공데이터포털 서비스키(DATA_GO_KR_SERVICE_KEY)가 설정되지 않았습니다."
            )
        key = (path, tuple(sorted(params.items())))
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < self.cache_ttl:
            return hit[1]
        try:
            resp = self.client.get(
                f"{BASE_URL}/{path}", params={**params, "serviceKey": self.service_key}
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            raise BenefitApiError(f"공공서비스 API 호출 실패: {e}") from e
        self._cache[key] = (time.monotonic(), data)
        return data

    def list_services(self, field: str, keyword: str, per_page: int = 100) -> list[Benefit]:
        data = self._get(
            "serviceList", {"page": 1, "perPage": per_page, f"cond[{field}::LIKE]": keyword}
        )
        return [Benefit.from_api(item) for item in data.get("data", [])]

    def get_detail(self, service_id: str) -> Benefit | None:
        data = self._get("serviceDetail", {"cond[서비스ID::EQ]": service_id})
        items = data.get("data", [])
        return Benefit.from_api(items[0]) if items else None

    def search(
        self,
        keywords: list[str] | None = None,
        region: str | None = None,
        limit: int = 20,
    ) -> list[Benefit]:
        """키워드별로 조회해 합치고, 관련도 순으로 정렬한다.

        region을 주면 다른 지역 지자체의 혜택은 뺀다 (중앙부처·공공기관 혜택은 유지).
        일부 요청만 실패하면 나머지 결과로 진행하고, 전부 실패하면 예외를 낸다.
        """
        keywords = keywords or DEFAULT_KEYWORDS
        found: dict[str, Benefit] = {}
        errors: list[BenefitApiError] = []
        for keyword in keywords:
            for field in SEARCH_FIELDS:
                try:
                    for b in self.list_services(field, keyword):
                        found.setdefault(b.service_id, b)
                except BenefitApiError as e:
                    errors.append(e)
        if errors and not found:
            raise errors[0]
        if errors:
            log.warning("공공서비스 API 일부 요청 실패: %d건", len(errors))

        results = list(found.values())
        if region:
            key = normalize_region(region)
            results = [b for b in results if not b.is_local or key in b.agency]

        def relevance(b: Benefit) -> int:
            return sum(3 * (k in b.name) + (k in b.target) + (k in b.content) for k in keywords)

        results.sort(key=lambda b: -relevance(b))
        return results[:limit]
