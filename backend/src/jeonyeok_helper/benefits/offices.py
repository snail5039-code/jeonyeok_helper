"""지방보훈관서(지방보훈청·보훈지청) 27곳의 주소·전화·관할구역. data/veterans_offices.yaml

공개 API가 없어 국가보훈부 누리집의 관서별 '찾아오시는길'·'관할구역' 페이지에서 정리했다.
보훈대상자 등록, 보훈급여, 제대군인 지원 상담은 사는 곳을 관할하는 관서에서 한다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from jeonyeok_helper.benefits.regions import region_keys, same_province
from jeonyeok_helper.config import DATA_DIR, load_yaml

OFFICES_FILE = DATA_DIR / "veterans_offices.yaml"


class VeteransOffice(BaseModel):
    name: str
    address: str = ""
    phone: str = ""
    url: str = ""
    regions: list[str] = []


def find_offices(offices: list[VeteransOffice], region: str) -> list[VeteransOffice]:
    """사용자 지역을 관할하는 관서.

    '부산 해운대' → 부산지방보훈청(부산 전역), '경기 포천' → 포천시를 맡는 지청.
    시군구를 모르고 '경기'처럼 시도만 알면 그 시도의 관서를 모두 돌려준다.
    """
    user = region_keys(region)
    if not user:
        return []

    def covered(area: str) -> bool:
        area_keys = region_keys(area)
        if not area_keys:
            return False
        if len(area_keys) == 1:  # 시도 전체 관할
            return any(same_province(area_keys[0], k) for k in user)
        sido, sigungu = area_keys[0], area_keys[-1]
        if sigungu not in user:
            return False
        # '광주 광산구'가 '경기 광주시'에 걸리지 않도록, 사용자가 시도도 말했으면 시도까지 맞춘다
        return len(user) == 1 or any(same_province(sido, k) for k in user)

    exact = [o for o in offices if any(covered(a) for a in o.regions)]
    if exact and len(user) > 1:
        return exact
    # 시도만 알거나('경기') 한 단어라 시도인지 시군구인지 모호하면('광주': 광주광역시, 경기 광주시)
    # 그 시도의 관서도 함께 돌려준다.
    province = [
        o
        for o in offices
        if any(
            (ak := region_keys(a)) and any(same_province(ak[0], k) for k in user) for a in o.regions
        )
    ]
    return list({o.name: o for o in [*exact, *province]}.values())


@lru_cache
def load_offices(path: Path = OFFICES_FILE) -> list[VeteransOffice]:
    return [VeteransOffice(**o) for o in load_yaml(path, "offices")]
