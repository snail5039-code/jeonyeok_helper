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
