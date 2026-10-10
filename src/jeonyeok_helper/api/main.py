"""FastAPI 앱. 지금은 상태 확인만 있고, /chat 등은 4단계에서 추가한다."""

import uvicorn
from fastapi import FastAPI

from jeonyeok_helper import __version__
from jeonyeok_helper.config import get_settings

app = FastAPI(title="전역도우미", version=__version__)


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        # 키 값은 노출하지 않고 설정 여부만 알려준다.
        "keys": {
            "gemini": bool(s.google_api_key),
            "law_api": bool(s.law_api_oc),
            "data_go_kr": bool(s.data_go_kr_service_key),
        },
    }


def run() -> None:
    uvicorn.run("jeonyeok_helper.api.main:app", host="127.0.0.1", port=8000, reload=True)
