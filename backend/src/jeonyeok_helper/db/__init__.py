"""서비스 데이터베이스 (SQLAlchemy 2.0 + Alembic).

대화 기록·프로필은 LangGraph가 자체 SQLite(state.sqlite)에 저장하고,
이 DB는 서비스가 직접 쓰는 테이블(피드백 등)을 담는다.
"""

from jeonyeok_helper.db.models import Base, Feedback, JourneyItem
from jeonyeok_helper.db.session import Database

__all__ = ["Base", "Database", "Feedback", "JourneyItem"]
