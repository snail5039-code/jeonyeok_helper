"""규정 검색 골든셋 평가: 질문마다 정해 둔 근거가 상위 k개 안에 나오는지.

    uv run jeonyeok-eval --retrieval              # HyDE + 재정렬 (서비스 설정)
    uv run jeonyeok-eval --retrieval --ablation   # 벡터만 / +HyDE / +HyDE+재정렬 비교

답변 전체를 채점하는 평가(questions.yaml)와 달리 LLM 답변 없이 검색 단계만 잰다.
검색을 바꾸거나 자료를 늘렸을 때 근거가 밀려나지 않았는지 빠르게 확인하는 용도.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from jeonyeok_helper.config import DATA_DIR, load_yaml

GOLDEN_FILE = DATA_DIR / "eval" / "retrieval_golden.yaml"
RESULTS_DIR = DATA_DIR / "eval" / "results"

# (이름, HyDE, 재정렬)
SETUPS = {
    "vector": ("벡터 검색만", False, False),
    "hyde": ("+ HyDE", True, False),
    "full": ("+ HyDE + 재정렬 (서비스)", True, True),
}


@dataclass
class RetrievalResult:
    id: str
    category: str
    question: str
    citations: list[str]
    found: list[bool]  # expect 묶음별로 찾았는지
    first_rank: int | None  # 처음 근거가 나온 순위 (1부터)
    leaked: list[str] = field(default_factory=list)  # forbid에 걸린 출처
    seconds: float = 0.0
    error: str = ""

    @property
    def hit(self) -> bool:
        return any(self.found) and not self.leaked

    @property
    def recall(self) -> float:
        return sum(self.found) / len(self.found) if self.found else 0.0

    @property
    def rr(self) -> float:
        return 1 / self.first_rank if self.first_rank and not self.leaked else 0.0


def load_golden(path: Path = GOLDEN_FILE) -> list[dict]:
    return load_yaml(path, "cases")


def grade_retrieval(case: dict, citations: list[str]) -> tuple[list[bool], int | None, list[str]]:
    """(묶음별 찾음, 첫 근거 순위, 걸린 금지 출처)."""
    groups = case["expect"]

    def matches(cite: str, group: list[str]) -> bool:
        return any(alt in cite for alt in group)

    found = [any(matches(c, g) for c in citations) for g in groups]
    first = next(
        (i for i, c in enumerate(citations, 1) if any(matches(c, g) for g in groups)), None
    )
    leaked = [c for c in citations if any(f in c for f in case.get("forbid", []))]
    return found, first, leaked


def run_retrieval_eval(retriever, cases: list[dict], k: int = 6, workers: int = 4):
    def one(case: dict) -> RetrievalResult:
        started = time.perf_counter()
        for attempt in range(3):  # 임베딩·LLM API 일시 오류는 다시 시도
            try:
                docs = retriever.retrieve(case["question"], k=k, region=case.get("region"))
                break
            except Exception as e:
                if attempt == 2:
                    return RetrievalResult(
                        case["id"], case["category"], case["question"], [],
                        [False] * len(case["expect"]), None, error=str(e),
                    )  # fmt: skip
                time.sleep(2 * (attempt + 1))
        cites = [d.metadata.get("citation") or d.metadata.get("source", "") for d in docs]
        found, first, leaked = grade_retrieval(case, cites)
        return RetrievalResult(
            case["id"], case["category"], case["question"], cites, found, first, leaked,
            time.perf_counter() - started,
        )  # fmt: skip

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, cases))


def summarize_retrieval(results: list[RetrievalResult]) -> dict:
    def stats(rs: list[RetrievalResult]) -> dict:
        n = len(rs) or 1
        return {
            "cases": len(rs),
            "hit": round(sum(r.hit for r in rs) / n, 3),
            "recall": round(sum(r.recall for r in rs) / n, 3),
            "mrr": round(sum(r.rr for r in rs) / n, 3),
            "avg_seconds": round(sum(r.seconds for r in rs) / n, 2),
            "errors": sum(bool(r.error) for r in rs),
        }

    by_cat: dict[str, list[RetrievalResult]] = defaultdict(list)
    for r in results:
        by_cat[r.category].append(r)
    return {"overall": stats(results), "by_category": {c: stats(v) for c, v in by_cat.items()}}


def to_markdown(runs: dict[str, tuple[list[RetrievalResult], dict]], k: int, at: str) -> str:
    lines = [f"# 규정 검색 골든셋 평가 ({at}, 상위 {k}개)", ""]
    lines += [
        "| 검색 설정 | 문항 | Hit@k | Recall@k | MRR | 평균 시간 |",
        "|---|---|---|---|---|---|",
    ]
    for key, (_, s) in runs.items():
        o = s["overall"]
        lines.append(
            f"| {SETUPS[key][0]} | {o['cases']} | {o['hit']:.0%} | {o['recall']:.0%} | "
            f"{o['mrr']:.2f} | {o['avg_seconds']}초 |"
        )
    key = "full" if "full" in runs else next(iter(runs))
    results, summary = runs[key]
    lines += ["", f"## 분야별 ({SETUPS[key][0]})", "", "| 분야 | 문항 | Hit | Recall | MRR |",
              "|---|---|---|---|---|"]  # fmt: skip
    for cat, s in summary["by_category"].items():
        lines.append(
            f"| {cat} | {s['cases']} | {s['hit']:.0%} | {s['recall']:.0%} | {s['mrr']:.2f} |"
        )
    lines += ["", f"## 놓친 근거 ({SETUPS[key][0]})", ""]
    missed = [r for r in results if r.recall < 1 or r.leaked or r.error]
    if not missed:
        lines.append("없음")
    for r in missed:
        why = r.error or (f"다른 지역 출처: {', '.join(r.leaked)}" if r.leaked else "")
        lines.append(f"- `{r.id}` {r.question} — 찾음 {sum(r.found)}/{len(r.found)} {why}")
        lines += [f"  - {i}. {c}" for i, c in enumerate(r.citations, 1)]
    return "\n".join(lines) + "\n"


def save_retrieval(runs: dict, k: int, out_dir: Path = RESULTS_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    at = datetime.now().strftime("%Y%m%d-%H%M%S")
    payload = {
        key: {
            "summary": s,
            "results": [asdict(r) | {"hit": r.hit, "recall": r.recall, "rr": r.rr} for r in rs],
        }
        for key, (rs, s) in runs.items()
    }
    (out_dir / f"{at}-retrieval.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = out_dir / f"{at}-retrieval.md"
    report.write_text(to_markdown(runs, k, at), encoding="utf-8")
    return report


def main_retrieval(ablation: bool, ids: list[str] | None, k: int) -> int:
    from jeonyeok_helper.llm import get_fast_chat_model
    from jeonyeok_helper.rag.retriever import RegulationRetriever
    from jeonyeok_helper.rag.store import RegulationStore

    cases = load_golden()
    if ids:
        cases = [c for c in cases if c["id"] in ids]
    store, llm = RegulationStore(), get_fast_chat_model()
    runs = {}
    for key in SETUPS if ablation else ["full"]:
        name, hyde, rerank = SETUPS[key]
        retriever = RegulationRetriever(store, llm=llm, use_hyde=hyde, use_rerank=rerank)
        results = run_retrieval_eval(retriever, cases, k=k)
        runs[key] = (results, summarize_retrieval(results))
        o = runs[key][1]["overall"]
        print(
            f"{name}: Hit@{k} {o['hit']:.0%}, Recall@{k} {o['recall']:.0%}, "
            f"MRR {o['mrr']:.2f}, {o['avg_seconds']}초, 오류 {o['errors']}"
        )
    print(f"보고서: {save_retrieval(runs, k)}")
    return 0
