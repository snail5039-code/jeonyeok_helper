"""평가: data/eval/questions.yaml의 질문을 에이전트에 물어보고 채점한다.

    uv run jeonyeok-eval                 # 전체 40문항
    uv run jeonyeok-eval --ids c01 m05   # 일부만
    uv run jeonyeok-eval --limit 5
    uv run jeonyeok-eval --model gemini-3.5-flash   # 다른 모델과 비교

결과는 data/eval/results/에 JSON과 마크다운 보고서로 남는다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from jeonyeok_helper.cli import run_cli
from jeonyeok_helper.config import DATA_DIR, load_yaml

QUESTIONS_FILE = DATA_DIR / "eval" / "questions.yaml"
RESULTS_DIR = DATA_DIR / "eval" / "results"

CATEGORY_NAMES = {
    "conscript": "의무복무 병사",
    "short_term_officer": "단기 간부",
    "long_term": "중·장기 복무",
    "merit": "보훈대상자",
    "tools": "외부 도구·자료",
    "general": "일반",
}


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class CaseResult:
    id: str
    category: str
    question: str
    answer: str
    asked: bool
    sources: list[dict]
    profile: dict
    seconds: float
    checks: list[Check] = field(default_factory=list)
    error: str = ""
    tools: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        return sum(c.passed for c in self.checks) / len(self.checks) if self.checks else 0.0


def load_questions(path: Path = QUESTIONS_FILE) -> list[dict]:
    return load_yaml(path, "questions")


def _profile_matches(expected, actual) -> bool:
    if actual is None:
        return False
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            return abs(float(actual) - float(expected)) < 0.5
        except (TypeError, ValueError):
            return False
    # '서울'과 '서울특별시', '경기'와 '경기도'를 같은 지역으로 본다.
    return str(expected) in str(actual) or str(actual) in str(expected)


def tools_used(evidence: list[str]) -> list[str]:
    """도구 원문은 '[도구이름] 내용'으로 쌓인다. 실제로 부른 도구 이름 목록."""
    return sorted({m[1] for e in evidence if (m := re.match(r"\[(\w+)\]", e))})


def grade(
    case: dict,
    answer: str,
    asked: bool,
    sources: list[dict],
    profile: dict,
    tools: list[str] | None = None,
) -> list[Check]:
    checks: list[Check] = []
    if (words := case.get("tools_any")) and not asked:
        hit = next((w for w in words if w in (tools or [])), None)
        checks.append(Check("도구 사용", hit is not None, hit or f"쓴 도구: {tools or '없음'}"))
    if "should_ask" in case:
        want = case["should_ask"]
        checks.append(
            Check("되묻기" if want else "바로 답변", asked == want, "되물음" if asked else "답변함")
        )
    if not asked:
        if words := case.get("sources_any"):
            titles = [s.get("title", "") for s in sources]
            hit = next((w for w in words if any(w in t for t in titles)), None)
            checks.append(
                Check("근거 출처", hit is not None, hit or f"출처 {len(titles)}건에 없음")
            )
        if words := case.get("answer_any"):
            hit = next((w for w in words if w in answer), None)
            checks.append(Check("답변 내용", hit is not None, hit or "핵심 단어 없음"))
    for key, expected in (case.get("profile") or {}).items():
        actual = profile.get(key)
        checks.append(
            Check(
                f"프로필 {key}",
                _profile_matches(expected, actual),
                f"{actual!r} (기대 {expected!r})",
            )
        )
    return checks


async def run_case(agent, case: dict) -> CaseResult:
    config = {
        "configurable": {"thread_id": f"eval-{uuid.uuid4()}", "user_id": f"eval-{uuid.uuid4()}"},
    }
    started = time.perf_counter()
    try:
        state = await agent.ainvoke({"messages": [("user", case["question"])]}, config)
    except Exception as e:  # 한 문항이 실패해도 나머지는 계속 평가한다.
        return CaseResult(
            case["id"], case["category"], case["question"], "", False, [], {},
            time.perf_counter() - started, [Check("실행", False, str(e))], str(e),
        )  # fmt: skip
    seconds = time.perf_counter() - started
    answer = state["messages"][-1].text
    asked = not state.get("draft")
    sources = state.get("sources", [])
    profile = state.get("profile", {})
    tools = tools_used(state.get("evidence", []))
    return CaseResult(
        case["id"], case["category"], case["question"], answer, asked, sources, profile, seconds,
        grade(case, answer, asked, sources, profile, tools), tools=tools,
    )  # fmt: skip


async def run_eval(
    agent_factory: Callable[[], AbstractAsyncContextManager],
    cases: list[dict],
    on_result: Callable[[CaseResult], None] | None = None,
) -> list[CaseResult]:
    results = []
    async with agent_factory() as agent:
        for case in cases:
            result = await run_case(agent, case)
            results.append(result)
            if on_result:
                on_result(result)
    return results


def summarize(results: list[CaseResult]) -> dict:
    by_cat: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        by_cat[r.category].append(r)

    def stats(rs: list[CaseResult]) -> dict:
        checks = [c for r in rs for c in r.checks]
        return {
            "cases": len(rs),
            "perfect": sum(r.score == 1 for r in rs),
            "check_pass_rate": round(sum(c.passed for c in checks) / len(checks), 3)
            if checks
            else 0.0,
            "avg_seconds": round(sum(r.seconds for r in rs) / len(rs), 2) if rs else 0.0,
            "errors": sum(bool(r.error) for r in rs),
        }

    return {"overall": stats(results), "by_category": {k: stats(v) for k, v in by_cat.items()}}


def to_markdown(results: list[CaseResult], summary: dict, started_at: str) -> str:
    o = summary["overall"]
    lines = [
        f"# 평가 결과 ({started_at}, {summary.get('model', '모델 미상')})",
        "",
        f"- 문항 {o['cases']}개 중 전부 통과 **{o['perfect']}개**",
        f"- 체크 통과율 **{o['check_pass_rate']:.0%}**, 평균 응답 시간 {o['avg_seconds']}초, "
        f"실행 오류 {o['errors']}건",
        "",
        "| 유형 | 문항 | 전부 통과 | 체크 통과율 | 평균 시간 |",
        "|---|---|---|---|---|",
    ]
    for cat, s in summary["by_category"].items():
        lines.append(
            f"| {CATEGORY_NAMES.get(cat, cat)} | {s['cases']} | {s['perfect']} | "
            f"{s['check_pass_rate']:.0%} | {s['avg_seconds']}초 |"
        )
    lines += ["", "## 실패한 체크", ""]
    failed = [(r, c) for r in results for c in r.checks if not c.passed]
    if not failed:
        lines.append("없음")
    for r, c in failed:
        lines.append(f"- `{r.id}` {r.question} — **{c.name}**: {c.detail}")
    return "\n".join(lines) + "\n"


def save(results: list[CaseResult], summary: dict, out_dir: Path = RESULTS_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{started_at}-{summary['model']}" if summary.get("model") else started_at
    payload = {"summary": summary, "results": [asdict(r) | {"score": r.score} for r in results]}
    (out_dir / f"{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = out_dir / f"{name}.md"
    report.write_text(to_markdown(results, summary, started_at), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    return run_cli(lambda: _run(argv))


def _run(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(prog="jeonyeok-eval", description="에이전트 평가")
    parser.add_argument("--ids", nargs="*", help="평가할 문항 id")
    parser.add_argument("--limit", type=int, help="앞에서부터 N문항만")
    parser.add_argument("--model", help="평가할 Gemini 모델 (기본: .env의 GEMINI_MODEL)")
    args = parser.parse_args(argv)

    cases = load_questions()
    if args.ids:
        cases = [c for c in cases if c["id"] in args.ids]
    if args.limit:
        cases = cases[: args.limit]

    from jeonyeok_helper.agents.runtime import open_agent
    from jeonyeok_helper.config import get_settings
    from jeonyeok_helper.llm import get_answer_model, get_fast_chat_model

    model = args.model or get_settings().gemini_model
    print(f"모델: {model}, 문항: {len(cases)}개\n")

    def show(r: CaseResult) -> None:
        mark = "✓" if r.score == 1 else ("✗" if r.score == 0 else "△")
        print(f"{mark} {r.id} {r.score:.0%} {r.seconds:.1f}s  {r.question}")

    # 서비스와 같은 설정(온도 0, 생각 예산)으로 평가한다
    llm, fast_llm = get_answer_model(model), get_fast_chat_model()
    results = asyncio.run(
        run_eval(lambda: open_agent(llm, fast_llm=fast_llm, state_db=None), cases, show)
    )
    summary = summarize(results) | {"model": model}
    report = save(results, summary)
    o = summary["overall"]
    print(f"\n전부 통과 {o['perfect']}/{o['cases']}, 체크 통과율 {o['check_pass_rate']:.0%}")
    print(f"보고서: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
