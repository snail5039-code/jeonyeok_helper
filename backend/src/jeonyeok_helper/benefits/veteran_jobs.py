"""국가보훈부 취업정보시스템의 '보훈관서 채용정보' OPEN API. 인증키 없이 XML로 공개된다.

- GET https://job.mpva.go.kr/govRecurit/openapi.do?place=&category=&section=&page=
  (조건을 하나도 주지 않으면 500. 지역을 모르면 place=z(전국)로 부른다)
- 보훈특별고용: 국가유공자·장기복무 제대군인 등 취업지원대상자를 공기업·기업체에 특별고용
- 일반직공무원등특별채용: 공무원·군무원 특별채용
- 한 쪽에 10건씩 최신 등록순으로 온다. 앞의 몇 쪽만 받아 마감 안 된 공고를 거른다.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date

import httpx
from pydantic import BaseModel

from jeonyeok_helper.benefits.common import BenefitApiError, TimedCache
from jeonyeok_helper.benefits.regions import region_keys, short_province

BASE_URL = "https://job.mpva.go.kr/govRecurit/openapi.do"
PAGES = 5  # 앞쪽 50건까지 (마감 지난 공고가 섞여 있어 30건이면 몇 건 안 남음)
PAGE_SIZE = 10

# 공개 안내(국가보훈부 누리집 OPEN API 페이지)의 근무지역 코드
PLACE_CODES = {
    "서울": "a", "경기": "b", "인천": "c", "부산": "d", "대구": "e", "광주": "f", "대전": "g",
    "울산": "h", "경남": "i", "경북": "j", "전남": "k", "전북": "l", "충남": "m", "충북": "n",
    "제주": "o", "세종": "p", "전남광주통합": "k",
}  # fmt: skip
SECTION_CODES = {"보훈특별고용": "a", "특별채용": "b"}


class VeteranJob(BaseModel):
    company: str
    title: str
    section: str = ""  # 보훈특별고용 / 일반직공무원등특별채용
    area: str = ""
    education: str = ""
    experience: str = ""
    posted: str = ""
    deadline: str = ""
    url: str = ""


def parse_vacancies(xml_text: str) -> list[VeteranJob]:
    # 응답 선언이 euc-kr이라 문자열로 바꾼 뒤에는 선언을 떼고 읽는다
    root = ET.fromstring(re.sub(r"^\s*<\?xml[^>]*\?>", "", xml_text))

    def text(item: ET.Element, tag: str) -> str:
        return " ".join((item.findtext(tag) or "").split())

    return [
        VeteranJob(
            company=text(v, "r_company"),
            title=text(v, "r_title"),
            section=text(v, "r_section"),
            area=text(v, "r_work_place"),
            education=text(v, "r_school"),
            experience=text(v, "experience"),
            posted=text(v, "reg_date"),
            deadline=text(v, "end_date"),
            url=text(v, "link"),
        )
        for v in root.iter("vacancy")
    ]


class VeteranJobClient:
    def __init__(self, client: httpx.Client | None = None, cache_ttl: float = 3600):
        self.client = client or httpx.Client(
            timeout=30, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True
        )
        self._cache = TimedCache(cache_ttl, namespace="veteran_jobs")

    def _page(self, place: str, section: str, page: int) -> list[VeteranJob]:
        params = {"place": place, "page": page} | ({"section": section} if section else {})

        def load() -> list[VeteranJob]:
            try:
                resp = self.client.get(BASE_URL, params=params)
                resp.raise_for_status()
                return parse_vacancies(resp.text)
            except (httpx.HTTPError, ET.ParseError) as e:
                raise BenefitApiError(f"보훈관서 채용정보 호출 실패: {e}") from e

        return self._cache.get((place, section, page), load)

    def search(
        self,
        region: str | None = None,
        section: str | None = None,
        keyword: str | None = None,
        limit: int = 10,
        today: date | None = None,
    ) -> list[VeteranJob]:
        """마감 전 공고를 최신순으로. section은 '보훈특별고용' 또는 '특별채용'."""
        codes = (PLACE_CODES.get(short_province(k)) for k in region_keys(region))
        place = next((c for c in codes if c), "z")
        sec = SECTION_CODES.get(section or "", "")
        today_str = (today or date.today()).isoformat()
        found: dict[str, VeteranJob] = {}
        for p in range(1, PAGES + 1):
            page = self._page(place, sec, p)
            for j in page:
                found.setdefault(j.url or f"{j.company}:{j.title}", j)
            if len(page) < PAGE_SIZE:  # 마지막 쪽
                break
        jobs = [j for j in found.values() if not j.deadline or j.deadline >= today_str]
        if keyword:
            jobs = [j for j in jobs if keyword in j.title or keyword in j.company]
        return jobs[:limit]
