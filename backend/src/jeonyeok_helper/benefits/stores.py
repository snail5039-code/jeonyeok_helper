"""공공데이터포털 '병무청_나라사랑가게조회서비스' 클라이언트.

나라사랑가게: 예비군 동원훈련 이수자, 현역병·사회복무요원, 병역명문가에게 할인 등을 주는 가게.

- GET https://apis.data.go.kr/1300000/JwctMmaUdhygigwan/getjwctMmaUdhygigwan
  ?serviceKey=&numOfRows=&pageNo=  (XML, 지역 조건 검색 없음)
- 전체(약 2,400곳)를 한 번 받아 캐시하고 주소로 거른다.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx
from pydantic import BaseModel

from jeonyeok_helper.benefits.common import (
    DATA_GO_KR_KEY_MISSING,
    BenefitApiError,
    TimedCache,
    fetch_all_pages,
)
from jeonyeok_helper.benefits.regions import address_in_region, region_keys

BASE_URL = "https://apis.data.go.kr/1300000/JwctMmaUdhygigwan/getjwctMmaUdhygigwan"
PAGE_SIZE = 1000


class Store(BaseModel):
    name: str
    benefit: str = ""  # 할인, 면제, 기타
    address: str = ""
    phone: str = ""


def parse_stores(xml_text: str) -> tuple[list[Store], int]:
    """(가게 목록, 전체 수). 결과 코드가 정상이 아니면 예외."""
    root = ET.fromstring(xml_text)
    code = root.findtext("header/resultCode") or ""
    if code not in ("00", "03"):  # 03 = 데이터 없음
        raise BenefitApiError(f"나라사랑가게 API 오류: {root.findtext('header/resultMsg')}")

    def text(item: ET.Element, tag: str) -> str:
        return (item.findtext(tag) or "").strip()

    stores = [
        Store(
            name=text(item, "udaeGgm"),
            benefit=text(item, "gtcdNm"),
            address=text(item, "juso"),
            phone=text(item, "udgigwanTelno"),
        )
        for item in root.iter("item")
    ]
    return stores, int(root.findtext("body/totalCount") or 0)


class StoreClient:
    def __init__(
        self,
        service_key: str,
        client: httpx.Client | None = None,
        cache_ttl: float = 24 * 3600,
    ):
        self.service_key = service_key
        self.client = client or httpx.Client(timeout=30)
        self._cache = TimedCache(cache_ttl, namespace="stores")

    def all(self) -> list[Store]:
        if not self.service_key:
            raise BenefitApiError(DATA_GO_KR_KEY_MISSING)
        return self._cache.get("all", self._load)

    def _load(self) -> list[Store]:
        def page(n: int) -> tuple[list[Store], int]:
            resp = self.client.get(
                BASE_URL,
                params={"serviceKey": self.service_key, "numOfRows": PAGE_SIZE, "pageNo": n},
            )
            resp.raise_for_status()
            return parse_stores(resp.text)

        try:
            return fetch_all_pages(page, PAGE_SIZE)
        except (httpx.HTTPError, ET.ParseError) as e:
            raise BenefitApiError(f"나라사랑가게 API 호출 실패: {e}") from e

    def find(self, region: str, keyword: str | None = None, limit: int = 10) -> list[Store]:
        """지역(필수) 안에서, keyword를 주면 가게 이름에 그 단어가 있는 곳만."""
        keys = region_keys(region)
        if not keys:
            return []
        found = [s for s in self.all() if address_in_region(s.address, keys)]
        if keyword:
            found = [s for s in found if keyword in s.name]
        return found[:limit]
