"""외부 공공 API 클라이언트가 같이 쓰는 것: 오류 타입, 캐시, 페이지 넘기기."""

from __future__ import annotations

import time
from collections.abc import Callable, Hashable
from typing import Any

DATA_GO_KR_KEY_MISSING = "공공데이터포털 서비스키(DATA_GO_KR_SERVICE_KEY)가 설정되지 않았습니다."


class BenefitApiError(RuntimeError):
    """외부 API 실패. 도구는 이걸 받아 예외 대신 error와 대체 안내를 돌려준다."""


class TimedCache:
    """키별로 받아 온 값을 ttl초 동안 다시 쓴다. 실패한 호출은 저장하지 않는다."""

    def __init__(self, ttl: float):
        self.ttl = ttl
        self._entries: dict[Hashable, tuple[float, Any]] = {}

    def get[T](self, key: Hashable, load: Callable[[], T]) -> T:
        hit = self._entries.get(key)
        if hit and time.monotonic() - hit[0] < self.ttl:
            return hit[1]
        value = load()
        self._entries[key] = (time.monotonic(), value)
        return value


def fetch_all_pages[T](fetch_page: Callable[[int], tuple[list[T], int]], page_size: int) -> list[T]:
    """지역 조건 검색이 없는 API에서 전체 목록을 받는다. fetch_page(page) → (목록, 전체 수)."""
    items: list[T] = []
    page = 1
    while True:
        batch, total = fetch_page(page)
        items += batch
        if not batch or page * page_size >= total:
            return items
        page += 1
