"""환경변수(.env) 기반 설정."""

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

# 라이브러리가 os.environ에서 직접 읽는 값도 .env에서 불러온다.
load_dotenv(PROJECT_ROOT / ".env")


def default_chroma_dir(data_dir: Path = DATA_DIR, windows: bool = os.name == "nt") -> Path:
    """Windows에서 경로에 한글이 있으면 Chroma가 검색 인덱스(HNSW) 파일을 쓰지 못해
    다음 실행에서 'Error loading hnsw index'가 난다. 그때는 영문 경로(LOCALAPPDATA)에 둔다."""
    local = os.environ.get("LOCALAPPDATA")
    if windows and not str(data_dir).isascii() and local:
        return Path(local) / "jeonyeok_helper" / "chroma"
    return data_dir / "chroma"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

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

    # RAG
    chroma_dir: Path = default_chroma_dir()
    chroma_collection: str = "regulations"
    raw_docs_dir: Path = DATA_DIR / "raw"
    retrieval_k: int = 6

    # 대화 기록과 사용자 프로필을 저장하는 SQLite 파일 (서버를 재시작해도 유지)
    state_db: Path = DATA_DIR / "state.sqlite"

    # 슈퍼바이저가 한 질문에서 워커를 호출할 수 있는 최대 횟수 (무한 루프 방지)
    max_worker_calls: int = 4


def load_yaml(path: Path, key: str) -> list[dict]:
    """data/의 YAML 목록 파일(laws, institutions, questions)에서 key 아래 목록을 읽는다."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))[key]


@lru_cache
def get_settings() -> Settings:
    return Settings()
