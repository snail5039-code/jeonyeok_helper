"""단계별 모델 사용량: 그래프 노드마다 호출 수·토큰·시간을 모으고 비용을 계산한다.

평가(evaluation.py)가 문항마다 붙여, 어느 단계가 토큰과 시간을 쓰는지 보고서에 남긴다.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

# 100만 토큰당 달러 (입력, 출력). 출력에는 생각(thinking) 토큰이 포함된다.
# 2026-10 기준 Gemini API 유료 등급 공개 가격. 바뀌면 여기만 고친다.
PRICES: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),
}
UNKNOWN_STEP = "기타"


def cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """토큰 수를 달러로. 가격표에 없는 모델은 0으로 본다."""
    price_in, price_out = PRICES.get(model.removeprefix("models/"), (0.0, 0.0))
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


class StepUsage(BaseCallbackHandler):
    """모델 호출을 그래프 노드(langgraph_node)별로 모은다.

    도구 안에서 부른 모델(HyDE·재정렬)은 그 도구를 부른 워커 노드로 잡힌다.
    """

    def __init__(self) -> None:
        self.steps: dict[str, dict[str, Any]] = defaultdict(
            lambda: (
                dict.fromkeys(("calls", "input", "output", "reasoning"), 0)
                | {"seconds": 0.0, "cost": 0.0}
            )
        )
        self._runs: dict[UUID, tuple[str, float]] = {}

    def on_chat_model_start(self, serialized, messages, *, run_id: UUID, metadata=None, **kwargs):
        step = (metadata or {}).get("langgraph_node") or UNKNOWN_STEP
        self._runs[run_id] = (step, time.perf_counter())

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs) -> None:
        step, started = self._runs.pop(run_id, (UNKNOWN_STEP, time.perf_counter()))
        s = self.steps[step]
        s["calls"] += 1
        s["seconds"] += time.perf_counter() - started
        for generations in response.generations:
            for g in generations:
                message = getattr(g, "message", None)
                usage = getattr(message, "usage_metadata", None) or {}
                model = (getattr(message, "response_metadata", None) or {}).get("model_name", "")
                tokens_in = usage.get("input_tokens", 0)
                tokens_out = usage.get("output_tokens", 0)
                s["input"] += tokens_in
                s["output"] += tokens_out
                s["reasoning"] += (usage.get("output_token_details") or {}).get("reasoning", 0)
                s["cost"] += cost(model, tokens_in, tokens_out)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs) -> None:
        self._runs.pop(run_id, None)

    def report(self) -> dict[str, dict[str, Any]]:
        return {
            step: s | {"seconds": round(s["seconds"], 2), "cost": round(s["cost"], 6)}
            for step, s in self.steps.items()
        }


def total(steps: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """단계별 사용량을 한 줄로 합친다."""
    keys = ("calls", "input", "output", "reasoning", "cost")
    return {k: sum(s.get(k, 0) for s in steps.values()) for k in keys}
