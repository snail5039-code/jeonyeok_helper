# 전역도우미 서버 이미지
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# 의존성만 먼저 설치해서, 코드만 바뀌었을 때는 이 층을 다시 쓰게 한다.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY data/*.yaml ./data/
COPY data/eval ./data/eval
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# 실행 중 생기는 데이터(대화 기록)는 볼륨으로 뺀다. 벡터 검색과 피드백은 PostgreSQL(DATABASE_URL).
RUN useradd --create-home --uid 1000 app \
    && mkdir -p data/raw data/state \
    && chown -R app:app data
USER app
ENV STATE_DB=/app/data/state/state.sqlite

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "jeonyeok_helper.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
