"""Alembic 실행 환경.

- 서버 시작 시: Database.migrate()가 연결(connection)을 넘겨준다.
- 명령줄(uv run alembic ...): 설정(.env)의 DB로 연결한다.
"""

from alembic import context
from sqlalchemy import create_engine

from jeonyeok_helper.db.models import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    if url := config.get_main_option("sqlalchemy.url"):
        return url
    from jeonyeok_helper.config import get_settings

    return get_settings().app_db_url


def _run(connection) -> None:
    # SQLite는 ALTER TABLE이 제한적이라 batch 모드로 컬럼 변경을 처리한다.
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif (conn := config.attributes.get("connection")) is not None:
    _run(conn)
else:
    with create_engine(_url()).connect() as conn:
        _run(conn)
