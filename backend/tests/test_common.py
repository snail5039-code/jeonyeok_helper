import pytest

from jeonyeok_helper.benefits.common import TimedCache, fetch_all_pages
from jeonyeok_helper.benefits.jobs import LOCATION_CODES
from jeonyeok_helper.benefits.regions import (
    address_in_region,
    province_variants,
    region_keys,
    same_province,
    short_province,
)
from jeonyeok_helper.benefits.youth import _sido_codes


def test_timed_cache_reuses_until_ttl_and_skips_failures():
    calls = []
    cache = TimedCache(ttl=60)

    def load():
        calls.append(1)
        return len(calls)

    assert cache.get("a", load) == 1
    assert cache.get("a", load) == 1  # 캐시
    assert cache.get("b", load) == 2  # 키가 다르면 새로

    def fail():
        raise RuntimeError("API 503")

    with pytest.raises(RuntimeError):
        cache.get("c", fail)
    assert cache.get("c", load) == 3  # 실패는 저장하지 않는다

    expired = TimedCache(ttl=0)
    expired.get("a", load)
    assert expired.get("a", load) == 5


def test_fetch_all_pages_stops_at_total_or_empty_page():
    pages = {1: [1, 2], 2: [3, 4], 3: [5]}
    asked = []

    def page(n):
        asked.append(n)
        return pages.get(n, []), 5

    assert fetch_all_pages(page, page_size=2) == [1, 2, 3, 4, 5]
    assert asked == [1, 2, 3]

    asked.clear()
    assert fetch_all_pages(lambda n: (asked.append(n) or [], 100), page_size=2) == []
    assert asked == [1]


@pytest.mark.parametrize("region", ["전남 순천", "전라남도 순천시", "전남"])
def test_long_and_short_province_names_map_to_same_codes(region):
    keys = region_keys(region)
    assert _sido_codes(region) == {"46", "12"}  # 12 = 2026년 전남광주통합특별시
    assert LOCATION_CODES[short_province(keys[0])] == "14"
    assert address_in_region("전남 순천시 중앙로 1", keys)


def test_same_province():
    assert same_province("전라남", "전남")
    assert same_province("전남광주통합", "전남")
    assert not same_province("경기", "경남")


def test_province_variants_cover_merged_province():
    assert "전남광주통합" in province_variants("광주")
    assert "(구)광주" in province_variants("광주")
    assert "(구)전라남" not in province_variants("광주")  # 통합 전 전남 자료는 광주 사용자와 무관
    assert {"전라남", "전남광주통합"} <= set(province_variants("전라남"))
    assert province_variants("부산") == ["(구)부산", "부산"]


def test_region_filter_finds_ordinances_saved_under_merged_name():
    from jeonyeok_helper.rag.store import region_filter

    sido_filters = [f for f in region_filter("전남")["$or"] if "sido" in f]
    assert "전남광주통합" in sido_filters[0]["sido"]["$in"]
