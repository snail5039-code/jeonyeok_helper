"""외부 공공 API 클라이언트가 같이 쓰는 것: 오류 타입, 캐시, 페이지 넘기기."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Hashable
from datetime import date
from typing import Any

log = logging.getLogger(__name__)

DATA_GO_KR_KEY_MISSING = "공공데이터포털 서비스키(DATA_GO_KR_SERVICE_KEY)가 설정되지 않았습니다."


class BenefitApiError(RuntimeError):
    """외부 API 실패. 도구는 이걸 받아 예외 대신 error와 대체 안내를 돌려준다."""


class TimedCache:
    """키별로 받아 온 값을 ttl초 동안 다시 쓴다. 실패한 호출은 저장하지 않는다.

    namespace를 주면 Postgres(cache_entry 표)에도 저장해서 서버를 다시 켜도 ttl 안이면
    API를 다시 부르지 않는다 (db/cache.py). DB가 없거나 실패하면 메모리 캐시로만 돈다.
    """

    def __init__(self, ttl: float, namespace: str | None = None):
        self.ttl = ttl
        self.namespace = namespace
        self._entries: dict[Hashable, tuple[float, Any]] = {}

    def get[T](self, key: Hashable, load: Callable[[], T]) -> T:
        hit = self._entries.get(key)
        if hit and time.monotonic() - hit[0] < self.ttl:
            return hit[1]
        saved = self._saved()
        if saved is not None:
            from jeonyeok_helper.db.cache import MISSING

            try:
                found = saved.get_with_age(self.namespace, key, self.ttl)
            except Exception:
                log.warning("저장 캐시 읽기 실패: %s", self.namespace, exc_info=True)
                found = MISSING
            if found is not MISSING:
                value, age = found
                # 저장한 시각 기준으로 ttl을 센다 (다시 켰다고 ttl이 늘어나지 않게)
                self._entries[key] = (time.monotonic() - age, value)
                return value
        value = load()
        self._entries[key] = (time.monotonic(), value)
        if saved is not None:
            try:
                saved.put(self.namespace, key, value)
            except Exception:
                log.warning("저장 캐시 쓰기 실패: %s", self.namespace, exc_info=True)
        return value

    def _saved(self):
        if not self.namespace:
            return None
        from jeonyeok_helper.db.cache import get_saved_cache

        return get_saved_cache()


# '20250306 ~ 20250313', '2025.05.01~2025.05.20', '2025-03-13까지' 같은 날짜
_DATE = re.compile(r"(20\d{2})[.\-/]?\s?(\d{1,2})[.\-/]?\s?(\d{1,2})")


def period_closed(text: str, today: date | None = None) -> bool:
    """신청 기간 문구의 날짜가 모두 오늘 이전이면 True (지난 공고). 날짜가 없으면('상시') False."""
    days = []
    for y, m, d in _DATE.findall(text or ""):
        try:
            days.append(date(int(y), int(m), int(d)))
        except ValueError:
            continue
    return bool(days) and max(days) < (today or date.today())


CLOSED_NOTE = " (지난 공고로 신청 기간이 끝났음. 올해 일정은 기관에 확인)"


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
