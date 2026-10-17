"""환경변수(.env) 기반 설정."""

from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

# 라이브러리가 os.environ에서 직접 읽는 값도 .env에서 불러온다.
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 한 사용자가 1분에 보낼 수 있는 질문·작전도 생성 횟수 (0 = 제한 없음)
    chat_rate_limit_per_minute: int = 20

    # Gemini
    google_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    # 답변 작성의 생각 예산 (None = 모델 기본값, 0 = 끔). 평가 30문항 비교 (2026-10-12):
    #   기본값 30/30 27.1초, 1024 30/30 21.4초, 0 29/30 18.4초 ('혜택 다 알려줘'에 답이 좁아짐)
    gemini_thinking_budget: int | None = 1024
    gemini_embedding_model: str = "models/gemini-embedding-001"
    # 프로필 추출·라우팅·근거 검증용 빠른 모델 (생각 예산 0 = 생각 단계 끔)
    gemini_fast_model: str = "gemini-2.5-flash"
    gemini_fast_thinking_budget: int | None = 0

    # 국가법령정보센터 Open API (https://open.law.go.kr) 신청 시 받는 OC 값
    law_api_oc: str = ""

    # 공공데이터포털(data.go.kr) 서비스키 — '행정안전부_대한민국 공공서비스(혜택) 정보'
    data_go_kr_service_key: str = ""

    # 온통청년(youthcenter.go.kr) 청년정책 OPEN API 인증키 — 마이페이지 > OPEN API에서 신청
    youthcenter_api_key: str = ""

    # PostgreSQL(pgvector): 규정 검색 벡터와 서비스 테이블(피드백). 로컬은 docker compose up -d db
    database_url: str = "postgresql+psycopg://jeonyeok:jeonyeok@localhost:5432/jeonyeok"

    # 실시간 API 응답과 BM25 색인을 Postgres(cache_entry 표)에도 저장해 서버를 다시 켜도 쓴다.
    # 테스트에서는 끈다.
    persist_cache: bool = True

    # RAG
    vector_collection: str = "regulations"
    raw_docs_dir: Path = DATA_DIR / "raw"
    retrieval_k: int = 6

    # 예전에 대화 기록과 사용자 프로필을 저장하던 SQLite 파일. 지금은 Postgres에 저장하고,
    # 이 파일이 남아 있으면 서버가 켜질 때 프로필을 Postgres로 한 번 옮긴다.
    state_db: Path = DATA_DIR / "state.sqlite"

    # 슈퍼바이저가 한 질문에서 워커를 호출할 수 있는 최대 횟수 (무한 루프 방지)
    max_worker_calls: int = 4


def load_yaml(path: Path, key: str) -> list[dict]:
    """data/의 YAML 목록 파일(laws, institutions, questions)에서 key 아래 목록을 읽는다."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))[key]


@lru_cache
def get_settings() -> Settings:
    return Settings()
