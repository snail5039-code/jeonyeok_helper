"""터미널에서 에이전트와 대화하기 (Gemini 키 필요).

uv run jeonyeok-chat
"""

from __future__ import annotations

import asyncio
import uuid

from jeonyeok_helper.agents.runtime import open_agent
from jeonyeok_helper.cli import run_cli


async def _chat() -> None:
    config = {"configurable": {"thread_id": str(uuid.uuid4()), "user_id": "local"}}
    async with open_agent() as agent:
        print("전역도우미입니다. 무엇이 궁금하세요? (종료: exit)")
        while True:
            try:
                question = await asyncio.to_thread(input, "\n나> ")
            except EOFError:  # 입력이 끝나면(Ctrl+Z, 파이프 종료) 대화를 마친다.
                return
            if question.strip().lower() in {"exit", "quit", "종료"}:
                return
            if not question.strip():
                continue
            # 어떤 워커를 거쳤는지 보여준다.
            async for update in agent.astream(
                {"messages": [("user", question)]}, config, stream_mode="updates"
            ):
                for node, value in update.items():
                    if node == "supervisor" and value:
                        print(f"  · 슈퍼바이저 → {value.get('next')}")
                    if node in {"verify", "ask_user"}:
                        print(f"\n전역도우미> {value['messages'][-1].text}")


def main() -> int:
    return run_cli(lambda: asyncio.run(_chat()))


if __name__ == "__main__":
    raise SystemExit(main())
