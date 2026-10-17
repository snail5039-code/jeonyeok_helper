"""Postgres에 저장하는 캐시 (cache_entry 표).

실시간 API 응답(정부24·온통청년·나라사랑가게·위탁병원·채용)은 메모리 캐시(TimedCache)에만 두면
서버를 다시 켤 때마다 전체 목록을 새로 받아야 했다. BM25 색인도 파일에 두면 Docker 이미지를 새로
만들 때 사라졌다. 둘 다 이 표에 pickle로 넣어 두고, 메모리에 없을 때 여기서 먼저 찾는다.

DB가 없거나 실패해도 서비스는 그대로 돈다 (그때는 저장 없이 매번 받아 온다).
"""

from __future__ import annotations

import hashlib
import logging
import pickle
import threading
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select

from jeonyeok_helper.db.models import CacheEntry

log = logging.getLogger(__name__)

_MISSING = object()


def key_of(key: Any) -> str:
    """튜플 등 어떤 키든 같은 값이면 같은 문자열로 (표의 키 길이를 고정)."""
    return hashlib.md5(repr(key).encode("utf-8")).hexdigest()


class SavedCache:
    def __init__(self, database):
        self.db = database

    def get(self, namespace: str, key: Any, max_age: float | None = None) -> Any:
        """저장한 값. 없거나 max_age초보다 오래됐으면 MISSING."""
        found = self.get_with_age(namespace, key, max_age)
        return found if found is _MISSING else found[0]

    def get_with_age(self, namespace: str, key: Any, max_age: float | None = None):
        """(값, 저장한 지 몇 초) 또는 MISSING."""
        with self.db.session() as session:
            row = session.get(CacheEntry, (namespace, key_of(key)))
            if row is None:
                return _MISSING
            saved_at = row.saved_at if row.saved_at.tzinfo else row.saved_at.replace(tzinfo=UTC)
            age = (datetime.now(UTC) - saved_at).total_seconds()
            if max_age is not None and age > max_age:
                return _MISSING
            return pickle.loads(row.value), age

    def put(self, namespace: str, key: Any, value: Any) -> None:
        blob = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        with self.db.session() as session:
            session.merge(
                CacheEntry(
                    namespace=namespace, key=key_of(key), value=blob, saved_at=datetime.now(UTC)
                )
            )

    def clear(self, namespace: str) -> None:
        with self.db.session() as session:
            session.execute(delete(CacheEntry).where(CacheEntry.namespace == namespace))

    def keys(self, namespace: str) -> list[str]:
        with self.db.session() as session:
            return list(
                session.scalars(select(CacheEntry.key).where(CacheEntry.namespace == namespace))
            )


MISSING = _MISSING
_saved: SavedCache | None | object = _MISSING
_lock = threading.Lock()


def get_saved_cache() -> SavedCache | None:
    """설정의 DB로 만든 저장 캐시. 꺼져 있거나 DB에 붙지 못하면 None (한 번만 시도)."""
    global _saved
    if _saved is _MISSING:
        with _lock:
            if _saved is _MISSING:
                _saved = _connect()
    return _saved  # type: ignore[return-value]


def _connect() -> SavedCache | None:
    from jeonyeok_helper.config import get_settings
    from jeonyeok_helper.db.session import Database

    s = get_settings()
    if not s.persist_cache:
        return None
    try:
        db = Database(s.database_url)
        db.migrate()  # 명령어(평가·수집)에서도 표가 있게
        return SavedCache(db)
    except Exception:
        log.warning("저장 캐시(Postgres)를 쓰지 못해 메모리 캐시만 씁니다.", exc_info=True)
        return None


def set_saved_cache(cache: SavedCache | None) -> None:
    """테스트에서 바꿔 끼운다."""
    global _saved
    _saved = cache
