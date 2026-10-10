"""명령어(jeonyeok-rag, jeonyeok-chat, jeonyeok-eval) 공통 실행기."""

import sys
from collections.abc import Callable


def run_cli(command: Callable[[], int | None]) -> int:
    """한글 출력을 맞추고, API 키 누락 같은 설정 오류는 한 줄 안내로 끝낸다."""
    # Windows 콘솔(cp949)에서도 한글이 깨지지 않게 한다.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        return command() or 0
    except RuntimeError as e:
        print(f"오류: {e}")
        return 2
    except KeyboardInterrupt:
        return 130
