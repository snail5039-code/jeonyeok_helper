"""공공데이터포털 '행정안전부_대한민국 공공서비스(혜택) 정보' API 클라이언트.

정부24·보조금24에 올라온 중앙부처·지자체·공공기관 혜택을 조회한다.

- 목록: GET https://api.odcloud.kr/api/gov24/v3/serviceList
- 상세: GET https://api.odcloud.kr/api/gov24/v3/serviceDetail
- 조건 검색: cond[필드명::LIKE]=값 (한 요청에 조건을 여러 개 주면 AND라서 키워드마다 따로 요청)

서비스키는 공공데이터포털의 '일반 인증키(Decoding)' 값을 쓴다.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel

from jeonyeok_helper.benefits.common import DATA_GO_KR_KEY_MISSING, BenefitApiError, TimedCache
from jeonyeok_helper.benefits.regions import region_keys, same_province

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
    # 상세 응답에만 있는 근거 법령·조례
    "laws": ("법령",),
    "ordinances": ("자치법규",),
}

# 실제 값: 시군구, 광역시도, 지방공기업, 지방출자_출연기관 / 중앙행정기관, 공공기관
_LOCAL_AGENCY_TYPES = {"시군구", "광역시도"}


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
    laws: str = ""
    ordinances: str = ""

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
        return self.agency_type in _LOCAL_AGENCY_TYPES or self.agency_type.startswith("지방")


def agency_in_region(agency: str, keys: list[str]) -> bool:
    """지자체 소관기관명('부산광역시 해운대구', '전남광주통합특별시 여수시', '부산시설공단')이
    사용자 지역(region_keys)에 있는지. 사용자가 시군구까지 말했으면 같은 시군구 것만 남긴다."""
    agency_keys = region_keys(agency)
    if not agency_keys:
        return False
    if not same_province(agency_keys[0], keys[0]):
        # '포천'처럼 시군구만 말한 경우
        return len(keys) == 1 and len(agency_keys) > 1 and agency_keys[1] == keys[0]
    if len(keys) > 1 and len(agency_keys) > 1:
        return agency_keys[1] == keys[1]
    return True


class Gov24Client:
    def __init__(
        self,
        service_key: str,
        client: httpx.Client | None = None,
        cache_ttl: float = 6 * 3600,
    ):
        self.service_key = service_key
        self.client = client or httpx.Client(timeout=20)
        self._cache = TimedCache(cache_ttl)

    def _get(self, path: str, params: dict[str, Any]) -> dict:
        if not self.service_key:
            raise BenefitApiError(DATA_GO_KR_KEY_MISSING)

        def load() -> dict:
            try:
                resp = self.client.get(
                    f"{BASE_URL}/{path}", params={**params, "serviceKey": self.service_key}
                )
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPError, ValueError) as e:
                raise BenefitApiError(f"공공서비스 API 호출 실패: {e}") from e

        return self._cache.get((path, tuple(sorted(params.items()))), load)

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
        if keys := region_keys(region):
            results = [b for b in results if not b.is_local or agency_in_region(b.agency, keys)]

        def relevance(b: Benefit) -> int:
            return sum(3 * (k in b.name) + (k in b.target) + (k in b.content) for k in keywords)

        results.sort(key=lambda b: -relevance(b))
        return results[:limit]
