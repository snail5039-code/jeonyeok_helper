"""국가보훈부 제대군인지원센터(브이넷) 채용정보. 인증키 없이 XML로 공개된다.

- GET https://vnet.go.kr/empn/jobsearchxml.do?location=<코드>
- 공식 안내 페이지의 지역 코드는 실제 응답과 다르다. 아래 LOCATION_CODES는 실제 호출로 확인한 값.
- 한 번에 해당 지역 공고 전체(수백 건)가 오므로 캐시하고, 마감 안 된 공고를 최신순으로 거른다.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date

import httpx
from pydantic import BaseModel

from jeonyeok_helper.benefits.common import BenefitApiError, TimedCache
from jeonyeok_helper.benefits.regions import region_keys, short_province

BASE_URL = "https://vnet.go.kr/empn/jobsearchxml.do"

# 2026-10 실제 응답으로 확인 (안내 페이지의 코드표와 다름)
LOCATION_CODES = {
    "서울": "1",
    "부산": "2",
    "대구": "3",
    "인천": "4",
    "광주": "5",
    "대전": "6",
    "울산": "7",
    "세종": "8",
    "경기": "9",
    "강원": "10",
    "충북": "11",
    "충남": "12",
    "전북": "13",
    "전남": "14",
    "전남광주통합": "14",  # 2026년 통합특별시. 브이넷은 아직 광주(5)·전남(14)을 따로 둔다
    "경북": "15",
    "경남": "16",
    "제주": "17",
    "해외": "18",
}


# 지역과 관계없이 지원할 수 있는 공고 (area가 '전국'이거나 제목에 [전국])
NATIONWIDE = re.compile(r"전국")


class Job(BaseModel):
    company: str
    title: str
    area: str = ""
    pay: str = ""
    posted: str = ""
    deadline: str = ""
    url: str = ""


def parse_jobs(xml_text: str) -> list[Job]:
    root = ET.fromstring(xml_text)

    def text(item: ET.Element, tag: str) -> str:
        return (item.findtext(tag) or "").strip()

    return [
        Job(
            company=text(item, "company"),
            title=text(item, "contents"),
            area=text(item, "area"),
            pay=text(item, "pay"),
            posted=text(item, "regdate"),
            deadline=text(item, "enddate"),
            url=text(item, "link"),
        )
        for item in root.iter("item")
    ]


class VnetJobClient:
    def __init__(self, client: httpx.Client | None = None, cache_ttl: float = 3600):
        self.client = client or httpx.Client(timeout=30)
        self._cache = TimedCache(cache_ttl)

    def _fetch(self, code: str) -> list[Job]:
        def load() -> list[Job]:
            try:
                resp = self.client.get(BASE_URL, params={"location": code} if code else {})
                resp.raise_for_status()
                return parse_jobs(resp.text)
            except (httpx.HTTPError, ET.ParseError) as e:
                raise BenefitApiError(f"제대군인지원센터 채용정보 호출 실패: {e}") from e

        return self._cache.get(code, load)

    def search(
        self,
        region: str | None = None,
        keyword: str | None = None,
        limit: int = 10,
        today: date | None = None,
    ) -> list[Job]:
        """마감이 안 지난 공고를 최신순으로. region은 시도 단위(예: '부산', '경기도 포천').

        지역을 주면 그 지역 공고에 '전국' 공고(정부청사 방호직, 군무원 등 어디서나 지원하는
        공고)를 몇 개 붙인다. 지역 코드로만 조회하면 전국 공고 대부분이 빠진다."""
        codes = (LOCATION_CODES.get(short_province(k)) for k in region_keys(region))
        code = next((c for c in codes if c), "")
        today_str = (today or date.today()).isoformat()

        def alive(found: list[Job]) -> list[Job]:
            return sorted(
                (j for j in found if not j.deadline or j.deadline >= today_str),
                key=lambda j: j.posted,
                reverse=True,
            )

        def matching(jobs: list[Job]) -> list[Job]:
            # 검색어로 하나도 안 남으면 검색어 없이 보여 준다 (모델이 사용자가 말하지 않은
            # 직종이나 '수원' 같은 지명을 검색어로 넣어 '공고 없음'이 된 적이 있다)
            if not keyword:
                return jobs
            return [j for j in jobs if keyword in j.title or keyword in j.company] or jobs

        jobs = matching(alive(self._fetch(code)))
        if not code:
            return jobs[:limit]
        try:
            everywhere = alive(self._fetch(""))
        except BenefitApiError:
            everywhere = []  # 전국 조회가 실패해도 지역 공고는 보여 준다
        seen = {(j.company, j.title) for j in jobs}
        national = matching(
            [
                j
                for j in everywhere
                if NATIONWIDE.search(f"{j.area} {j.title}") and (j.company, j.title) not in seen
            ]
        )[: max(1, limit // 3)]
        return jobs[: limit - len(national)] + national
