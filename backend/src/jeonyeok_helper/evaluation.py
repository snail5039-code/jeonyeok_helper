"""평가: data/eval/questions.yaml의 질문을 에이전트에 물어보고 채점한다.

    uv run jeonyeok-eval                 # 전체 문항
    uv run jeonyeok-eval --ids c01 m05   # 일부만
    uv run jeonyeok-eval --limit 5
    uv run jeonyeok-eval --model gemini-3.5-flash   # 다른 모델과 비교
    uv run jeonyeok-eval --retrieval [--ablation]   # 규정 검색 골든셋 (retrieval_eval.py)
    uv run --group eval jeonyeok-eval --ragas       # 답변 평가 뒤 RAGAS 채점 (ragas_eval.py)

결과는 data/eval/results/에 JSON과 마크다운 보고서로 남는다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
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
from jeonyeok_helper.usage import StepUsage, total

QUESTIONS_FILE = DATA_DIR / "eval" / "questions.yaml"
RESULTS_DIR = DATA_DIR / "eval" / "results"

CATEGORY_NAMES = {
    "conscript": "의무복무 병사",
    "short_term_officer": "단기 간부",
    "long_term": "중·장기 복무",
    "merit": "보훈대상자",
    "tools": "외부 도구·자료",
    "general": "일반",
    "hard": "어려운 질문",
    "safety": "안전(가드레일)",
}


# 보고서에 보일 단계 이름 (LangGraph 노드 이름 → 하는 일)
STEP_NAMES = {
    "respond": "respond (답변 작성)",
    "verify": "verify (근거 검증)",
    "guide": "guide (말풍선·할 일 제안)",
    "model": "워커 (도구 고르기)",
    "supervisor": "supervisor (라우팅)",
    "coach": "coach (말로 답할지 판단)",
    "profile": "profile (내 정보 읽기)",
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
    # 답변이 근거로 받은 도구 원문 (RAGAS 채점에 쓴다)
    evidence: list[str] = field(default_factory=list)
    # 그래프 단계별 모델 호출 수·토큰·시간·비용 (usage.StepUsage)
    usage: dict = field(default_factory=dict)

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
    talked: bool = False,
) -> list[Check]:
    checks: list[Check] = []
    # 길잡이: 인사·자기 정보·진행 보고는 검색 없이 바로(talk), 그 밖의 질문은 자료를 찾아 답한다
    if "should_talk" in case:
        want = case["should_talk"]
        checks.append(
            Check(
                "길잡이 대화" if want else "자료 찾기", talked == want, "talk" if talked else "검색"
            )
        )
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
        if words := case.get("answer_all"):
            # 여러 가지를 한꺼번에 물었을 때 빠뜨리지 않았는지
            missing = [w for w in words if w not in answer]
            detail = f"빠짐: {missing}" if missing else "전부"
            checks.append(Check("답변 모두 포함", not missing, detail))
    if words := case.get("answer_none"):
        # 되묻기·길잡이 대화를 포함해 어떤 답에도 나오면 안 되는 말 (개인정보, 틀린 전제 맞장구)
        leaked = [w for w in words if w in answer]
        detail = f"나옴: {leaked}" if leaked else "없음"
        checks.append(Check("나오면 안 되는 말", not leaked, detail))
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
    usage = StepUsage()
    config = {
        "configurable": {"thread_id": f"eval-{uuid.uuid4()}", "user_id": f"eval-{uuid.uuid4()}"},
        "callbacks": [usage],
    }
    started = time.perf_counter()
    try:
        state = await agent.ainvoke({"messages": [("user", case["question"])]}, config)
    except Exception as e:  # 한 문항이 실패해도 나머지는 계속 평가한다.
        return CaseResult(
            case["id"], case["category"], case["question"], "", False, [], {},
            time.perf_counter() - started, [Check("실행", False, str(e))], str(e),
            usage=usage.report(),
        )  # fmt: skip
    seconds = time.perf_counter() - started
    # 되묻기는 ask_user가 interrupt로 멈춘 것 (답 대신 되물은 질문을 채점한다)
    # 길잡이(talk)가 말로 되물은 경우도 답변 초안이 없으므로 되묻기로 본다.
    interrupts = state.get("__interrupt__") or []
    asked = bool(interrupts) or not state.get("draft")
    answer = interrupts[0].value["question"] if interrupts else state["messages"][-1].text
    sources = state.get("sources", [])
    profile = state.get("profile", {})
    evidence = state.get("evidence", [])
    tools = tools_used(evidence)
    talked = (state.get("guide") or {}).get("mode") == "talk"
    return CaseResult(
        case["id"], case["category"], case["question"], answer, asked, sources, profile, seconds,
        grade(case, answer, asked, sources, profile, tools, talked), tools=tools,
        evidence=evidence, usage=usage.report(),
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

    return {
        "overall": stats(results),
        "by_category": {k: stats(v) for k, v in by_cat.items()},
        "usage": summarize_usage(results),
    }


def summarize_usage(results: list[CaseResult]) -> dict:
    """문항 하나당 평균 토큰·비용과, 단계별로 어디서 쓰는지."""
    n = len(results) or 1
    per_case = [total(r.usage) for r in results]
    steps: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    for r in results:
        for step, u in r.usage.items():
            for k, v in u.items():
                steps[step][k] += v
    costs = sorted(t["cost"] for t in per_case)
    return {
        "avg_input": round(sum(t["input"] for t in per_case) / n),
        "avg_output": round(sum(t["output"] for t in per_case) / n),
        "avg_reasoning": round(sum(t["reasoning"] for t in per_case) / n),
        "avg_calls": round(sum(t["calls"] for t in per_case) / n, 1),
        "avg_cost": round(sum(costs) / n, 5),
        "p95_cost": round(costs[int(0.95 * (len(costs) - 1))], 5) if costs else 0.0,
        "total_cost": round(sum(costs), 4),
        # 단계별 합계를 문항 수로 나눈 값 (문항 하나에서 그 단계가 평균 얼마나 쓰나)
        "by_step": {
            step: {k: round(v / n, 5 if k == "cost" else 2) for k, v in u.items()}
            for step, u in sorted(steps.items(), key=lambda kv: -kv[1]["cost"])
        },
    }


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
    if u := summary.get("usage"):
        lines += [
            "",
            "## 토큰·비용 (문항 하나 평균)",
            "",
            f"- 모델 호출 {u['avg_calls']}번, 입력 {u['avg_input']:,} · "
            f"출력 {u['avg_output']:,} 토큰 (그중 생각 {u['avg_reasoning']:,})",
            f"- 비용 ${u['avg_cost']:.4f} (상위 5% ${u['p95_cost']:.4f}), "
            f"이번 실행 합계 ${u['total_cost']:.2f}",
            "",
            "| 단계 | 호출 | 입력 | 출력 | 생각 | 모델 시간 | 비용 |",
            "|---|---|---|---|---|---|---|",
        ]
        for step, st in u["by_step"].items():
            lines.append(
                f"| {STEP_NAMES.get(step, step)} | {st['calls']} | {st['input']:,.0f} | "
                f"{st['output']:,.0f} | "
                f"{st['reasoning']:,.0f} | {st['seconds']}초 | ${st['cost']:.4f} |"
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


def sample_cases(cases: list[dict], n: int, seed: int = 20261027) -> list[dict]:
    """유형마다 비율대로 무작위로 골라 n문항 (같은 시드면 늘 같은 문항, 원래 순서 유지)."""
    if n >= len(cases):
        return cases
    rng = random.Random(seed)
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for c in cases:
        by_cat[c["category"]].append(c)
    picked: set[str] = set()
    for group in by_cat.values():
        take = max(1, round(n * len(group) / len(cases)))
        picked |= {c["id"] for c in rng.sample(group, min(take, len(group)))}
    return [c for c in cases if c["id"] in picked][:n]


def agreement(base: list[dict], other: list[dict]) -> dict:
    """같은 문항에서 단계별 판단이 얼마나 같은지. 최종 점수보다 둔하지 않은 비교.

    - 되묻기: 되물었는지(ask_user·길잡이)가 같은가
    - 라우팅: 부른 도구 묶음이 같은가 (라우터·워커의 판단)
    - 프로필: 대화에서 읽은 내 정보가 같은가
    """
    by_id = {r["id"]: r for r in base}
    pairs = [(by_id[r["id"]], r) for r in other if r["id"] in by_id]
    n = len(pairs) or 1

    def rate(same) -> float:
        return round(sum(bool(same(a, b)) for a, b in pairs) / n, 3)

    def clean(p: dict) -> dict:
        return {k: v for k, v in (p or {}).items() if v not in (None, "", [])}

    diffs = [
        {"id": b["id"], "question": b["question"], "what": what}
        for a, b in pairs
        for what, same in (
            ("되묻기", a["asked"] == b["asked"]),
            ("라우팅", set(a["tools"]) == set(b["tools"])),
            ("프로필", clean(a["profile"]) == clean(b["profile"])),
            ("점수", a["score"] == b["score"]),
        )
        if not same
    ]
    return {
        "cases": len(pairs),
        "asked": rate(lambda a, b: a["asked"] == b["asked"]),
        "routing": rate(lambda a, b: set(a["tools"]) == set(b["tools"])),
        "profile": rate(lambda a, b: clean(a["profile"]) == clean(b["profile"])),
        "score_same": rate(lambda a, b: a["score"] == b["score"]),
        "diffs": diffs,
    }


def compare_runs(base_path: Path, other_path: Path) -> Path:
    base = json.loads(base_path.read_text(encoding="utf-8"))
    other = json.loads(other_path.read_text(encoding="utf-8"))
    ag = agreement(base["results"], other["results"])
    ids = {d["id"] for d in other["results"]}
    base_same = [r for r in base["results"] if r["id"] in ids]

    def usage_of(results: list[dict]) -> dict:
        n = len(results) or 1
        totals = [total(r.get("usage") or {}) for r in results]
        return {
            "perfect": sum(r["score"] == 1 for r in results),
            "seconds": round(sum(r["seconds"] for r in results) / n, 2),
            "cost": round(sum(t["cost"] for t in totals) / n, 5),
        }

    ub, uo = usage_of(base_same), usage_of(other["results"])
    lines = [
        f"# 단계별 출력 비교: {other_path.stem} vs {base_path.stem}",
        "",
        f"같은 문항 {ag['cases']}개에서 기준 실행과 같은 판단을 내린 비율.",
        "",
        "| 되묻기 | 라우팅(부른 도구) | 프로필 | 점수 같음 |",
        "|---|---|---|---|",
        f"| {ag['asked']:.0%} | {ag['routing']:.0%} | {ag['profile']:.0%} "
        f"| {ag['score_same']:.0%} |",
        "",
        "| | 전부 통과 | 평균 시간 | 문항당 비용 |",
        "|---|---|---|---|",
        f"| 기준 | {ub['perfect']} | {ub['seconds']}초 | ${ub['cost']:.4f} |",
        f"| 비교 | {uo['perfect']} | {uo['seconds']}초 | ${uo['cost']:.4f} |",
        "",
        "## 달라진 문항",
        "",
    ]
    lines += [f"- `{d['id']}` {d['what']}: {d['question']}" for d in ag["diffs"]] or ["없음"]
    report = other_path.with_name(f"{other_path.stem}-vs-{base_path.stem}.md")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    return run_cli(lambda: _run(argv))


def _run(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(prog="jeonyeok-eval", description="에이전트 평가")
    parser.add_argument("--ids", nargs="*", help="평가할 문항 id")
    parser.add_argument("--limit", type=int, help="앞에서부터 N문항만")
    parser.add_argument("--model", help="평가할 Gemini 모델 (기본: .env의 GEMINI_MODEL)")
    parser.add_argument(
        "--retrieval", action="store_true", help="규정 검색 골든셋 평가 (답변 없이 검색만)"
    )
    parser.add_argument("--ablation", action="store_true", help="검색 설정 3가지 비교")
    parser.add_argument("-k", type=int, default=6, help="검색 평가의 상위 k개")
    parser.add_argument(
        "--golden", type=Path, help="검색 평가 문항 파일 (기본: retrieval_golden.yaml)"
    )
    parser.add_argument("--ragas", action="store_true", help="답변 평가 뒤 RAGAS로도 채점")
    parser.add_argument(
        "--ragas-file", type=Path, help="저장된 답변 평가 결과(JSON)를 RAGAS로 채점"
    )
    parser.add_argument("--judge", help="RAGAS 채점 모델 (기본: .env의 GEMINI_MODEL)")
    parser.add_argument(
        "--human-sheet", type=Path, help="저장된 답변 평가 결과(JSON)로 사람 채점 화면을 만듦"
    )
    parser.add_argument("--n", type=int, default=30, help="사람 채점 문항 수")
    parser.add_argument(
        "--human-compare",
        nargs="+",
        type=Path,
        metavar="FILE",
        help="사람 채점 결과(labels.json) 다음에 비교할 RAGAS 결과 JSON들",
    )
    parser.add_argument("--sample", type=int, help="유형별로 고르게 무작위 N문항 (고정 시드)")
    parser.add_argument(
        "--lite-steps",
        nargs="+",
        metavar="STEP",
        help="더 싼 모델로 바꿀 단계 (profile router workers verifier coach guide)",
    )
    parser.add_argument("--thinking", type=int, help="답변 모델의 생각 예산 (기본: 설정값 1024)")
    parser.add_argument("--lite-model", default="gemini-2.5-flash-lite", help="바꿔 끼울 모델")
    parser.add_argument(
        "--agreement",
        nargs=2,
        type=Path,
        metavar=("BASE", "OTHER"),
        help="두 답변 평가 결과의 단계별 출력 일치율 비교",
    )
    args = parser.parse_args(argv)

    if args.human_sheet:
        from jeonyeok_helper.human_eval import make_sheet

        page = make_sheet(args.human_sheet, args.n)
        print(f"채점 화면: {page}")
        print(f"고른 문항: {page.with_name(page.stem.removesuffix('-sheet') + '-ids.txt')}")
        return 0

    if args.human_compare:
        from jeonyeok_helper.human_eval import compare_files

        labels, *ragas = args.human_compare
        print(f"보고서: {compare_files(labels, ragas)}")
        return 0

    if args.ragas_file:
        from jeonyeok_helper.ragas_eval import score_file

        score_file(args.ragas_file, args.judge, args.ids)
        return 0

    if args.retrieval:
        from jeonyeok_helper.retrieval_eval import main_retrieval

        return main_retrieval(args.ablation, args.ids, args.k, args.golden)

    if args.agreement:
        base, other = args.agreement
        print(f"보고서: {compare_runs(base, other)}")
        return 0

    cases = load_questions()
    if args.ids:
        cases = [c for c in cases if c["id"] in args.ids]
    if args.sample:
        cases = sample_cases(cases, args.sample)
    if args.limit:
        cases = cases[: args.limit]

    from jeonyeok_helper.agents.runtime import open_agent
    from jeonyeok_helper.config import get_settings
    from jeonyeok_helper.llm import get_answer_model, get_chat_model, get_fast_chat_model

    model = args.model or get_settings().gemini_model
    # 일부 단계만 더 싼 모델로 (생각 끔). 결과 파일 이름에 바꾼 단계를 남긴다
    step_llms = {
        step: get_chat_model(temperature=0, model=args.lite_model, thinking_budget=0)
        for step in args.lite_steps or []
    }
    label = model + (f"+lite-{'-'.join(args.lite_steps)}" if args.lite_steps else "")
    print(f"모델: {label}, 문항: {len(cases)}개\n")

    def show(r: CaseResult) -> None:
        mark = "✓" if r.score == 1 else ("✗" if r.score == 0 else "△")
        print(f"{mark} {r.id} {r.score:.0%} {r.seconds:.1f}s  {r.question}")

    # 서비스와 같은 설정(온도 0, 생각 예산)으로 평가한다
    llm, fast_llm = get_answer_model(model), get_fast_chat_model()
    if args.thinking is not None:
        llm = get_chat_model(temperature=0, model=model, thinking_budget=args.thinking)
        label += f"+thinking{args.thinking}"
    results = asyncio.run(
        run_eval(
            lambda: open_agent(llm, fast_llm=fast_llm, state_db=None, step_llms=step_llms),
            cases,
            show,
        )
    )
    summary = summarize(results) | {"model": label}
    report = save(results, summary)
    o = summary["overall"]
    print(f"\n전부 통과 {o['perfect']}/{o['cases']}, 체크 통과율 {o['check_pass_rate']:.0%}")
    print(f"보고서: {report}")
    if args.ragas:
        from jeonyeok_helper.ragas_eval import score_file

        score_file(report.with_suffix(".json"), args.judge)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
