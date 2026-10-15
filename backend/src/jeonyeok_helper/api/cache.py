"""같은 질문을 같은 조건으로 다시 물으면 저장해 둔 답을 바로 보낸다.

질문 하나에 모델을 여러 번 불러 15~25초가 걸린다. 많이 묻는 질문('군복무 크레딧이 뭐예요?')은
사람마다 조건(내 정보·작전도)이 같으면 답도 같아서, 한 시간 동안 다시 쓴다.
'그거', '그럼'처럼 앞 대화에 기대는 질문은 대화마다 뜻이 달라 저장하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import re
import time

# 앞 대화를 가리키는 말 (이런 질문은 같은 글자라도 대화마다 뜻이 다르다)
CONTEXTUAL = re.compile(r"그거|그건|그것|이거|이건|그럼|거기|위에|방금|아까|그 중|그중|다음 거")


class AnswerCache:
    def __init__(self, ttl: float = 3600, size: int = 500):
        self.ttl = ttl
        self.size = size
        self._items: dict[str, tuple[float, dict]] = {}

    @staticmethod
    def key(message: str, profile: dict, journey: list[dict]) -> str | None:
        """저장 열쇠. 앞 대화에 기대는 질문이면 None (저장하지 않음)."""
        text = re.sub(r"\s+", " ", message).strip()
        if not text or CONTEXTUAL.search(text):
            return None
        tasks = sorted(f"{i.get('title')}:{bool(i.get('done'))}" for i in journey)
        raw = json.dumps([text, profile, tasks], ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def get(self, key: str | None, now: float | None = None) -> dict | None:
        if key is None or (hit := self._items.get(key)) is None:
            return None
        if (now if now is not None else time.monotonic()) - hit[0] >= self.ttl:
            self._items.pop(key, None)
            return None
        return hit[1]

    def put(self, key: str | None, value: dict, now: float | None = None) -> None:
        if key is None:
            return
        if len(self._items) >= self.size:  # 가장 오래된 것부터 버린다
            oldest = min(self._items, key=lambda k: self._items[k][0])
            self._items.pop(oldest, None)
        self._items[key] = (now if now is not None else time.monotonic(), value)
