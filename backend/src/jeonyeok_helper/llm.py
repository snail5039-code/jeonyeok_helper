"""Gemini 채팅 모델 / 임베딩 생성."""

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from jeonyeok_helper.config import get_settings


def _require_key() -> str:
    key = get_settings().google_api_key
    if not key:
        raise RuntimeError("GOOGLE_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return key


def get_chat_model(temperature: float = 0.2, model: str | None = None) -> ChatGoogleGenerativeAI:
    s = get_settings()
    return ChatGoogleGenerativeAI(
        model=model or s.gemini_model, google_api_key=_require_key(), temperature=temperature
    )


def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    s = get_settings()
    return GoogleGenerativeAIEmbeddings(
        model=s.gemini_embedding_model, google_api_key=_require_key()
    )
