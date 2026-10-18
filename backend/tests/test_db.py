from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from jeonyeok_helper.db import Base, Database, Feedback
from jeonyeok_helper.db.session import sqlite_url


def test_migration_creates_tables_and_matches_models(tmp_path: Path):
    db = Database(sqlite_url(tmp_path / "app.sqlite"))
    db.migrate()
    db.migrate()  # 두 번 돌려도 그대로

    assert "feedback" in inspect(db.engine).get_table_names()
    # 모델을 바꾸고 마이그레이션을 안 만들면 여기서 차이가 잡힌다.
    with db.engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_session_commits_and_rolls_back(tmp_path: Path):
    db = Database(sqlite_url(tmp_path / "app.sqlite"))
    db.migrate()
    with db.session() as session:
        session.add(Feedback(rating="up", question="q", answer="a"))

    try:
        with db.session() as session:
            session.add(Feedback(rating="down", question="q", answer="a"))
            raise RuntimeError("중간에 실패")
    except RuntimeError:
        pass

    with db.session() as session:
        assert [f.rating for f in session.query(Feedback).all()] == ["up"]


def test_saved_cache_keeps_api_results_across_restarts(tmp_path):
    """TimedCache에 namespace를 주면 DB에도 저장해, 새로 만든(=서버를 다시 켠) 캐시가 API를
    다시 부르지 않는다. ttl이 지나면 다시 부른다."""
    from jeonyeok_helper.benefits.common import TimedCache
    from jeonyeok_helper.db.cache import SavedCache, set_saved_cache

    db = Database(sqlite_url(tmp_path / "app.sqlite"))
    db.migrate()
    set_saved_cache(SavedCache(db))
    calls = []

    def load():
        calls.append(1)
        return [{"name": "청년 월세 지원"}]

    try:
        assert TimedCache(3600, namespace="t").get(("목록", 1), load) == [
            {"name": "청년 월세 지원"}
        ]
        assert TimedCache(3600, namespace="t").get(("목록", 1), load) == [
            {"name": "청년 월세 지원"}
        ]
        assert len(calls) == 1  # 두 번째는 DB에서
        TimedCache(0, namespace="t").get(("목록", 1), load)  # ttl이 지났으면 다시 받는다
        assert len(calls) == 2
    finally:
        set_saved_cache(None)


def test_journey_keeps_only_source_name_and_link(tmp_path: Path):
    """답변 출처의 원문 발췌는 작전도에 저장하지 않는다 (작전도가 커지지 않게)."""
    from jeonyeok_helper import journey

    db = Database(sqlite_url(tmp_path / "app.sqlite"))
    db.migrate()
    source = {"type": "regulation", "title": "국민연금법 제18조", "url": "u", "excerpt": "원문"}
    added = journey.add_items(
        db, "u1", [{"stage": "job", "title": "연금 크레딧 확인", "sources": [source]}], "chat"
    )
    assert added[0]["sources"] == [{"type": "regulation", "title": "국민연금법 제18조", "url": "u"}]
