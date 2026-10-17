"""테스트 공통 설정."""

import os

# 테스트가 실제 Postgres의 저장 캐시(cache_entry)에 쓰지 않게 끈다 (설정을 읽기 전에)
os.environ["PERSIST_CACHE"] = "false"

from jeonyeok_helper.cli import use_selector_loop_on_windows  # noqa: E402

# Postgres 체크포인터(psycopg 비동기)는 Windows 기본 이벤트 루프에서 돌지 않는다
use_selector_loop_on_windows()
