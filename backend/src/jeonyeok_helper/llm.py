"""Gemini 채팅 모델 / 임베딩 생성."""

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from jeonyeok_helper.config import get_settings


def _require_key() -> str:
    key = get_settings().google_api_key
    if not key:
        raise RuntimeError("GOOGLE_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return key


def get_chat_model(
    temperature: float = 0.2, model: str | None = None, thinking_budget: int | None = None
) -> ChatGoogleGenerativeAI:
    """thinking_budget=0이면 '생각' 단계를 끄고 바로 답한다 (단순한 분류·추출에 빠름)."""
    s = get_settings()
    return ChatGoogleGenerativeAI(
        model=model or s.gemini_model,
        google_api_key=_require_key(),
        temperature=temperature,
        thinking_budget=thinking_budget,
    )


def get_fast_chat_model() -> ChatGoogleGenerativeAI:
    """프로필 추출, 라우팅, 근거 검증처럼 짧고 정해진 형식의 단계에 쓰는 모델."""
    s = get_settings()
    return get_chat_model(
        temperature=0, model=s.gemini_fast_model, thinking_budget=s.gemini_fast_thinking_budget
    )


def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    s = get_settings()
    return GoogleGenerativeAIEmbeddings(
        model=s.gemini_embedding_model, google_api_key=_require_key()
    )
