"""요청 제한: 한 사용자가 짧은 시간에 너무 많이 물으면 모델 호출 비용과 쿼터가 바닥난다."""

from __future__ import annotations

import time
from collections import deque


class RateLimiter:
    """키(사용자 ID 등)마다 최근 window초 동안 limit번까지만 허용한다. limit이 0이면 끈다."""

    def __init__(self, limit: int, window: float = 60.0):
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str, now: float | None = None) -> bool:
        if self.limit <= 0:
            return True
        now = time.monotonic() if now is None else now
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        if len(self._hits) > 10_000:  # 오래 안 온 키를 정리해 메모리가 계속 늘지 않게
            self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < self.window}
        return True
