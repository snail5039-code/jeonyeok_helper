"""공공데이터포털 '한국보훈복지의료공단_보훈병원 위탁병원 정보(위도 경도 포함)' 클라이언트.

- 목록: GET https://api.odcloud.kr/api/witak2/v1/witak2?page=&perPage=&serviceKey=
- 지역 조건 검색이 없어서 전체(약 1,000곳)를 한 번 받아 캐시하고 주소로 거른다.

국가유공자 등은 가까운 위탁병원에서 진료비 감면을 받을 수 있다.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel

from jeonyeok_helper.benefits.common import (
    DATA_GO_KR_KEY_MISSING,
    BenefitApiError,
    TimedCache,
    fetch_all_pages,
)
from jeonyeok_helper.benefits.regions import address_in_region, region_keys

BASE_URL = "https://api.odcloud.kr/api/witak2/v1/witak2"
PAGE_SIZE = 500


class Hospital(BaseModel):
    name: str
    type: str = ""
    address: str = ""
    phone: str = ""
    latitude: float | None = None
    longitude: float | None = None

    @property
    def map_url(self) -> str:
        if self.latitude is None or self.longitude is None:
            return ""
        return f"https://map.kakao.com/link/map/{self.name},{self.latitude},{self.longitude}"

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> Hospital:
        def number(key: str) -> float | None:
            try:
                return float(item[key])
            except (KeyError, TypeError, ValueError):
                return None

        address = " ".join(p for p in (item.get("addr1"), item.get("addr2")) if p)
        return cls(
            name=str(item.get("name", "")).strip(),
            type=item.get("type") or "",
            address=address,
            phone=item.get("tel") or "",
            latitude=number("latitude"),
            longitude=number("longitude"),
        )


class HospitalClient:
    def __init__(
        self,
        service_key: str,
        client: httpx.Client | None = None,
        cache_ttl: float = 24 * 3600,
    ):
        self.service_key = service_key
        self.client = client or httpx.Client(timeout=30)
        self._cache = TimedCache(cache_ttl)

    def all(self) -> list[Hospital]:
        if not self.service_key:
            raise BenefitApiError(DATA_GO_KR_KEY_MISSING)
        return self._cache.get("all", self._load)

    def _load(self) -> list[Hospital]:
        def page(n: int) -> tuple[list[dict], int]:
            resp = self.client.get(
                BASE_URL, params={"page": n, "perPage": PAGE_SIZE, "serviceKey": self.service_key}
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", []), data.get("totalCount", 0)

        try:
            items = fetch_all_pages(page, PAGE_SIZE)
        except (httpx.HTTPError, ValueError) as e:
            raise BenefitApiError(f"위탁병원 API 호출 실패: {e}") from e
        return [Hospital.from_api(i) for i in items if i.get("use_yn", "Y") == "Y"]

    def find(self, region: str, limit: int = 10) -> list[Hospital]:
        """주소에 지역 이름이 모두 들어간 병원. '경기 포천' → 경기·포천이 다 있는 곳."""
        keys = region_keys(region)
        if not keys:
            return []
        return [h for h in self.all() if address_in_region(h.address, keys)][:limit]
