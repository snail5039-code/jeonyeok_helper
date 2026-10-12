"""온통청년 청년정책 OPEN API 클라이언트.

- GET https://www.youthcenter.go.kr/go/ythip/getPlcy?apiKeyNm=&pageNum=&pageSize=&rtnType=json
- 전체(약 3,000건)를 1,000건씩 받아 캐시하고, 지역(zipCd)·나이·키워드로 거른다.
- 병사 전역자는 대부분 20대라 청년정책이 실제로 가장 많이 쓰인다. 군 복무자 연령 연장 같은
  조건(addAplyQlfcCndCn)에 군 관련 내용이 있는 정책은 앞에 둔다.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel

from jeonyeok_helper.benefits.common import BenefitApiError, TimedCache, fetch_all_pages
from jeonyeok_helper.benefits.regions import region_keys, short_province

BASE_URL = "https://www.youthcenter.go.kr/go/ythip/getPlcy"
PAGE_SIZE = 1000
DETAIL_URL = "https://www.youthcenter.go.kr/youthPolicy/ythPlcyTotalSearch/ythPlcyDetail/{}"
RETRY_STATUS = {400, 429, 500, 502, 503, 504}

# zipCd(시군구 법정동 코드)의 앞 두 자리 → 시도. 강원·전북은 특별자치도 전환 전후 코드,
# 광주·전남은 2026년 전남광주통합특별시 코드(12)도 본다 (2026-10 실제 응답으로 확인).
SIDO_CODES: dict[str, tuple[str, ...]] = {
    "서울": ("11",),
    "부산": ("26",),
    "대구": ("27",),
    "인천": ("28",),
    "광주": ("29", "12"),
    "대전": ("30",),
    "울산": ("31",),
    "세종": ("36",),
    "경기": ("41",),
    "강원": ("42", "51"),
    "충북": ("43",),
    "충남": ("44",),
    "전북": ("45", "52"),
    "전남": ("46", "12"),
    "전남광주통합": ("12",),
    "경북": ("47",),
    "경남": ("48",),
    "제주": ("50",),
}
# 시도 코드가 이만큼 넘게 걸쳐 있으면 전국 정책으로 본다.
NATIONWIDE_SIDO_COUNT = 10
# '병역필 또는 면제자'는 흔한 자격 요건일 뿐이라 '병역'은 넣지 않는다
# (넣으면 청년농업인 지원 같은 정책이 전역자 맞춤인 것처럼 앞에 온다).
MILITARY_WORDS = ("군 복무", "군복무", "복무기간", "제대군인", "전역", "장병", "군인")


class YouthPolicy(BaseModel):
    policy_id: str
    name: str
    summary: str = ""
    support: str = ""
    category: str = ""
    agency: str = ""
    min_age: int | None = None
    max_age: int | None = None
    apply_period: str = ""
    business_end: str = ""
    condition: str = ""  # 추가 신청 자격 (군 복무자 연령 연장 등)
    how_to_apply: str = ""
    url: str = ""
    sido_codes: list[str] = []

    @property
    def nationwide(self) -> bool:
        return len(self.sido_codes) >= NATIONWIDE_SIDO_COUNT

    @property
    def military_related(self) -> bool:
        text = f"{self.name} {self.summary} {self.condition}"
        return any(w in text for w in MILITARY_WORDS)

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> YouthPolicy:
        def s(key: str) -> str:
            return str(item.get(key) or "").strip()

        def age(key: str) -> int | None:
            try:
                value = int(item.get(key) or 0)
            except (TypeError, ValueError):
                return None
            return value or None

        zips = [z.strip() for z in s("zipCd").split(",") if z.strip()]
        policy_id = s("plcyNo")
        url = s("aplyUrlAddr") or s("refUrlAddr1") or DETAIL_URL.format(policy_id)
        return cls(
            policy_id=policy_id,
            name=s("plcyNm"),
            summary=s("plcyExplnCn"),
            support=s("plcySprtCn")[:500],
            category=" > ".join(p for p in (s("lclsfNm"), s("mclsfNm")) if p),
            agency=s("sprvsnInstCdNm") or s("rgtrInstCdNm"),
            # 나이 제한이 없는 정책은 0으로 온다 (sprtTrgtAgeLmtYn=Y면 제한 없음)
            min_age=None if s("sprtTrgtAgeLmtYn") == "Y" else age("sprtTrgtMinAge"),
            max_age=None if s("sprtTrgtAgeLmtYn") == "Y" else age("sprtTrgtMaxAge"),
            apply_period=s("aplyYmd"),
            business_end=s("bizPrdEndYmd"),
            condition=s("addAplyQlfcCndCn")[:300],
            how_to_apply=s("plcyAplyMthdCn")[:300],
            url=url,
            sido_codes=sorted({z[:2] for z in zips}),
        )


def _sido_codes(region: str) -> set[str]:
    return {c for key in region_keys(region) for c in SIDO_CODES.get(short_province(key), ())}


class YouthPolicyClient:
    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
        cache_ttl: float = 12 * 3600,
        retry_wait: float = 1.0,
    ):
        self.api_key = api_key
        self.retry_wait = retry_wait
        # 기본 User-Agent(python-httpx)는 403으로 막힌다.
        self.client = client or httpx.Client(timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        self._cache = TimedCache(cache_ttl)

    def all(self) -> list[YouthPolicy]:
        if not self.api_key:
            raise BenefitApiError("온통청년 인증키(YOUTHCENTER_API_KEY)가 설정되지 않았습니다.")
        return self._cache.get("all", self._load)

    def _load(self) -> list[YouthPolicy]:
        def page(n: int) -> tuple[list[YouthPolicy], int]:
            params = {
                "apiKeyNm": self.api_key,
                "pageNum": n,
                "pageSize": PAGE_SIZE,
                "rtnType": "json",
            }
            # 동시에 여러 번 부르면 가끔 400·500이 나고 곧 다시 된다 (2026-10 확인). 두 번 더 시도.
            for attempt in range(3):
                resp = self.client.get(BASE_URL, params=params)
                if resp.status_code not in RETRY_STATUS or attempt == 2:
                    break
                time.sleep(self.retry_wait * (attempt + 1))
            resp.raise_for_status()
            data = resp.json()
            if data.get("resultCode") not in (200, "200"):
                raise BenefitApiError(f"온통청년 API 오류: {data.get('resultMessage')}")
            result = data.get("result") or {}
            items = result.get("youthPolicyList") or []
            total = int((result.get("pagging") or {}).get("totCount") or 0)
            return [YouthPolicy.from_api(i) for i in items], total

        try:
            return fetch_all_pages(page, PAGE_SIZE)
        except httpx.HTTPStatusError as e:
            # 예외 문자열에는 인증키가 든 URL이 있어 상태 코드만 남긴다.
            raise BenefitApiError(
                f"온통청년 API 호출 실패 (HTTP {e.response.status_code})"
            ) from None
        except (httpx.HTTPError, ValueError) as e:
            raise BenefitApiError(f"온통청년 API 호출 실패: {type(e).__name__}") from None

    def search(
        self,
        keyword: str | None = None,
        region: str | None = None,
        age: int | None = None,
        limit: int = 10,
        today: date | None = None,
    ) -> list[YouthPolicy]:
        """사업이 끝나지 않은 정책 중 지역·나이·키워드에 맞는 것.

        순서: 군 복무 관련 조건이 있는 정책 → 사용자 지역 정책 → 전국 정책.
        """
        today_str = (today or date.today()).strftime("%Y%m%d")
        codes = _sido_codes(region or "")
        words = keyword.split() if keyword else []

        def ok(p: YouthPolicy) -> bool:
            if p.business_end and p.business_end < today_str:
                return False
            if codes and p.sido_codes and not codes & set(p.sido_codes):
                return False
            if age is not None:
                if p.min_age and age < p.min_age:
                    return False
                if p.max_age and age > p.max_age:
                    return False
            text = f"{p.name} {p.summary} {p.category} {p.condition}"
            return all(w in text for w in words)

        # 같은 정책이 연도·차수별로 여러 건 올라온 경우가 있어 이름·기관이 같으면 하나만.
        unique = {(p.name, p.agency): p for p in self.all() if ok(p)}
        found = sorted(unique.values(), key=lambda p: (not p.military_related, p.nationwide))
        return found[:limit]
