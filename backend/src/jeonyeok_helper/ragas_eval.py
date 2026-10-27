"""RAGAS 평가: 답변 평가에서 받은 답변과 도구 원문(evidence)을 RAGAS 지표로 채점한다.

    uv run --group eval jeonyeok-eval --ragas                  # 답변 평가를 돌린 뒤 RAGAS 채점
    uv run --group eval jeonyeok-eval --ragas --ids h01 m04
    # 저장된 결과만 채점
    uv run --group eval jeonyeok-eval --ragas-file data/eval/results/<결과>.json

지표 (정답 문장 없이 쓸 수 있는 것만):
- faithfulness: 답변의 주장 중 도구 원문으로 뒷받침되는 비율 (지어낸 말이 있으면 떨어진다)
- answer_relevancy: 답변이 질문에 맞는 답인지 (답변에서 거꾸로 만든 질문과 원래 질문의 유사도)
- context_relevance: 도구 원문이 질문에 맞는 자료인지 (검색·도구 선택의 질)

되묻기·길잡이 대화(talk)처럼 도구 원문이 없는 문항은 채점하지 않는다.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from jeonyeok_helper.config import get_settings

METRICS = ("faithfulness", "answer_relevancy", "context_relevance")
METRIC_NAMES = {
    "faithfulness": "근거 충실도",
    "answer_relevancy": "답변 관련성",
    "context_relevance": "자료 관련성",
}
# 이 점수 아래인 문항은 보고서에 따로 모은다
LOW = 0.7


def build_metrics(judge_model: str) -> dict:
    import instructor
    from google import genai
    from ragas.embeddings.base import embedding_factory
    from ragas.llms import InstructorLLM
    from ragas.metrics.collections import AnswerRelevancy, ContextRelevance, Faithfulness

    s = get_settings()
    client = genai.Client(api_key=s.google_api_key)
    llm = InstructorLLM(
        client=instructor.from_genai(client, use_async=True), model=judge_model, provider="google"
    )
    embeddings = embedding_factory(
        "google", model=s.gemini_embedding_model.removeprefix("models/"), client=client
    )

    # 묶음 임베딩과 한 건씩 임베딩의 결과가 달라지지 않도록 하나씩 처리한다 (강의 예제와 같음)
    async def embed_one_by_one(texts, **kwargs):
        return [await embeddings.aembed_text(t, **kwargs) for t in texts]

    embeddings.aembed_texts = embed_one_by_one
    return {
        "faithfulness": Faithfulness(llm=llm),
        "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=embeddings),
        "context_relevance": ContextRelevance(llm=llm),
    }


def scorable(case: dict) -> bool:
    return bool(case.get("answer") and case.get("evidence") and not case.get("asked"))


async def score_case(metrics: dict, case: dict, sem: asyncio.Semaphore) -> dict:
    q, a, ctx = case["question"], case["answer"], case["evidence"]
    inputs = {
        "faithfulness": {"user_input": q, "response": a, "retrieved_contexts": ctx},
        "answer_relevancy": {"user_input": q, "response": a},
        "context_relevance": {"user_input": q, "retrieved_contexts": ctx},
    }
    out: dict = {"id": case["id"], "question": q}
    async with sem:
        for name in METRICS:
            try:
                result = await metrics[name].ascore(**inputs[name])
                out[name] = round(float(result.value), 3)
                if reason := getattr(result, "reason", None):
                    out[f"{name}_reason"] = reason
            except Exception as e:  # 한 지표가 실패해도 나머지는 채점한다
                out[name] = None
                out[f"{name}_error"] = str(e)[:300]
    return out


async def score_all(cases: list[dict], judge_model: str, concurrency: int = 4) -> list[dict]:
    metrics = build_metrics(judge_model)
    sem = asyncio.Semaphore(concurrency)
    targets = [c for c in cases if scorable(c)]
    done: list[dict] = []

    async def one(c: dict) -> dict:
        r = await score_case(metrics, c, sem)
        done.append(r)
        marks = " ".join(
            f"{METRIC_NAMES[m]} {r[m]:.2f}" if r.get(m) is not None else f"{METRIC_NAMES[m]} -"
            for m in METRICS
        )
        print(f"  [{len(done)}/{len(targets)}] {r['id']} {marks}")
        return r

    return list(await asyncio.gather(*(one(c) for c in targets)))


def averages(scores: list[dict]) -> dict:
    avg = {}
    for m in METRICS:
        vals = [s[m] for s in scores if s.get(m) is not None]
        avg[m] = round(sum(vals) / len(vals), 3) if vals else None
    return avg


def to_markdown(scores: list[dict], source: str, judge_model: str, cases: dict) -> str:
    avg = averages(scores)
    lines = [
        f"# RAGAS 평가 ({source}, 채점 모델 {judge_model})",
        "",
        f"- 채점한 문항 {len(scores)}개 (되묻기·길잡이 대화처럼 도구 원문이 없는 문항은 제외)",
        "",
        "| 지표 | 평균 |",
        "|---|---|",
    ]
    for m in METRICS:
        lines.append(f"| {METRIC_NAMES[m]} ({m}) | {avg[m] if avg[m] is not None else '-'} |")

    by_cat: dict[str, list[dict]] = {}
    for s in scores:
        by_cat.setdefault(cases[s["id"]].get("category", "-"), []).append(s)
    from jeonyeok_helper.evaluation import CATEGORY_NAMES

    header = " | ".join(METRIC_NAMES[m] for m in METRICS)
    lines += ["", "## 유형별", "", f"| 유형 | 문항 | {header} |"]
    lines.append("|---|---|" + "---|" * len(METRICS))
    for cat, ss in by_cat.items():
        a = averages(ss)
        cells = " | ".join(str(a[m]) if a[m] is not None else "-" for m in METRICS)
        lines.append(f"| {CATEGORY_NAMES.get(cat, cat)} | {len(ss)} | {cells} |")

    lines += ["", f"## 낮은 점수 (< {LOW})", ""]
    low = [s for s in scores if any(s.get(m) is not None and s[m] < LOW for m in METRICS)]
    if not low:
        lines.append("없음")
    for s in sorted(low, key=lambda s: s["id"]):
        marks = ", ".join(
            f"{METRIC_NAMES[m]} {s[m]}" for m in METRICS if s.get(m) is not None and s[m] < LOW
        )
        lines.append(f"- `{s['id']}` {s['question']} — {marks}")
    errors = [(s["id"], m, s[f"{m}_error"]) for s in scores for m in METRICS if f"{m}_error" in s]
    if errors:
        lines += ["", "## 채점 오류", ""]
        lines += [f"- `{i}` {m}: {e}" for i, m, e in errors]
    return "\n".join(lines) + "\n"


def score_file(path: Path, judge_model: str | None = None, ids: list[str] | None = None) -> Path:
    judge = judge_model or get_settings().gemini_model
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload["results"]
    if ids:
        cases = [c for c in cases if c["id"] in ids]
    if not any(c.get("evidence") for c in cases):
        raise RuntimeError(
            f"{path.name}에 도구 원문(evidence)이 없습니다. evidence를 저장하기 전의 결과입니다. "
            "`jeonyeok-eval --ragas`로 다시 돌려 주세요."
        )
    print(f"RAGAS 채점: {path.name}, 채점 모델 {judge}")
    scores = asyncio.run(score_all(cases, judge))
    scores.sort(key=lambda s: s["id"])
    # 이름에 점이 있어(gemini-2.5-flash) with_suffix를 쓰면 이름이 잘린다
    # 답변 모델이 아닌 채점 모델로 다시 채점하면 앞 결과를 덮어쓰지 않게 이름에 채점 모델을 붙인다
    answer_model = payload.get("summary", {}).get("model")
    tag = "ragas" if judge == answer_model or not answer_model else f"ragas-by-{judge}"
    out_json = path.with_name(f"{path.stem}-{tag}.json")
    report = path.with_name(f"{path.stem}-{tag}.md")
    by_id = {c["id"]: c for c in cases}
    out_json.write_text(
        json.dumps(
            {"judge_model": judge, "averages": averages(scores), "scores": scores},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    report.write_text(to_markdown(scores, path.stem, judge, by_id), encoding="utf-8")
    avg = averages(scores)
    print("평균: " + ", ".join(f"{METRIC_NAMES[m]} {avg[m]}" for m in METRICS))
    print(f"보고서: {report}")
    return report
