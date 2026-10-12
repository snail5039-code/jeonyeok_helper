"""지역 이름 맞추기. 사용자 말('경기도 포천'), API 응답('전남 강진군'), 조례 기관명('부산광역시')이
표기가 제각각이라 모두 region_keys로 같은 비교 값으로 바꿔서 비교한다."""

from __future__ import annotations

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

# 주소·코드표는 '전남'처럼 줄여 쓴다. normalize_region은 '전라남'으로 바꾸므로 짧은 이름으로도 본다.
SHORT_PROVINCE = {
    "충청북": "충북",
    "충청남": "충남",
    "전라남": "전남",
    "경상북": "경북",
    "경상남": "경남",
}


def normalize_region(region: str) -> str:
    """'서울', '서울시', '서울특별시' → '서울' / '충북', '충청북도' → '충청북'."""
    region = region.strip()
    if region in _REGION_ALIASES:
        return _REGION_ALIASES[region]
    for suffix in _REGION_SUFFIXES:
        if region.endswith(suffix) and len(region) > len(suffix) + 1:
            return region.removesuffix(suffix)
    return region


def region_keys(region: str | None) -> list[str]:
    """'경기도 가평군' → ['경기', '가평'], '부산광역시' → ['부산']. 지역 필터의 비교 값."""
    keys = []
    for part in (region or "").split():
        part = normalize_region(part)
        if len(part) > 2 and part[-1] in "시군구":
            part = part[:-1]
        keys.append(part)
    return [k for k in keys if k]


def short_province(key: str) -> str:
    """'전라남' → '전남'. 시도 코드표(청년정책, 채용정보)는 짧은 이름으로 찾는다."""
    return SHORT_PROVINCE.get(key, key)


# 2026년 통합특별시. 자료마다 통합 전 이름('(구)광주')과 통합 후 이름이 섞여 있다.
MERGED_PROVINCES = {"전남광주통합": ("전라남", "광주")}


def province_variants(key: str) -> list[str]:
    """시도 키로 저장된 자료를 찾을 때 볼 이름들. '광주' → 광주, (구)광주, 전남광주통합
    (통합 전 전라남도 자료는 광주 사용자에게 맞지 않으니 넣지 않는다)."""
    names = {key, short_province(key), f"(구){key}"}
    for merged, parts in MERGED_PROVINCES.items():
        if key in parts:
            names.add(merged)
        elif key == merged:
            names.update(parts)
            names.update(f"(구){p}" for p in parts)
    return sorted(names)


def address_in_region(address: str, keys: list[str]) -> bool:
    """주소에 지역 키(region_keys)가 모두 들어 있는지. '전남'·'전라남도' 표기를 둘 다 본다."""
    return all(k in address or short_province(k) in address for k in keys)


def same_province(a: str, b: str) -> bool:
    """'전라남'·'전남'·'전남광주통합'(전남광주통합특별시)처럼 표기가 달라도 같은 시도로 본다."""
    a, b = short_province(a), short_province(b)
    return a == b or (len(min(a, b, key=len)) >= 2 and (a in b or b in a))
