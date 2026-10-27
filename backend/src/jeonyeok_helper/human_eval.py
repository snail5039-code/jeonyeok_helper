"""사람 채점: 자동 채점(키워드 규칙·RAGAS)이 사람 판단과 맞는지 확인한다.

    # 1) 답변 평가 결과에서 무작위 30문항을 골라 채점 화면(HTML)을 만든다
    uv run jeonyeok-eval --human-sheet data/eval/results/<결과>.json [--n 30]
    # 2) 브라우저에서 채점하고 '결과 저장'으로 받은 JSON을 넣어, RAGAS 채점들과 비교한다
    uv run jeonyeok-eval --human-compare <labels.json> <결과>-ragas.json <결과>-ragas-by-<모델>.json

사람 점수는 문항마다 두 가지 (0 틀림 · 1 일부 · 2 맞음):
- grounded: 답의 사실(혜택·금액·기한·대상)이 근거 원문에 있고 틀린 말이 없는가
  (RAGAS 근거 충실도와 비교)
- answered: 질문에 실제로 답했는가 (RAGAS 답변 관련성과 비교)
"""

from __future__ import annotations

import html
import json
import random
from pathlib import Path

from jeonyeok_helper.config import DATA_DIR

HUMAN_DIR = DATA_DIR / "eval" / "human"
PAIRS = (
    ("grounded", "faithfulness", "근거 충실도"),
    ("answered", "answer_relevancy", "답변 관련성"),
)


def pick_cases(results: list[dict], n: int, seed: int = 20261027) -> list[dict]:
    """RAGAS가 채점할 수 있는 문항(되묻기가 아니고 근거 원문이 있음) 중 무작위 n개."""
    pool = [r for r in results if r.get("evidence") and not r.get("asked")]
    return sorted(random.Random(seed).sample(pool, min(n, len(pool))), key=lambda r: r["id"])


def make_sheet(result_path: Path, n: int = 30, out_dir: Path = HUMAN_DIR) -> Path:
    """채점 화면 HTML과 고른 문항 id 목록을 만든다."""
    results = json.loads(result_path.read_text(encoding="utf-8"))["results"]
    cases = pick_cases(results, n)
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = [c["id"] for c in cases]
    (out_dir / f"{result_path.stem}-ids.txt").write_text(" ".join(ids), encoding="utf-8")
    page = out_dir / f"{result_path.stem}-sheet.html"
    page.write_text(_sheet_html(result_path.stem, cases), encoding="utf-8")
    return page


def _sheet_html(source: str, cases: list[dict]) -> str:
    def radios(case_id: str, key: str) -> str:
        return "".join(
            f'<label><input type="radio" name="{case_id}-{key}" value="{v}"> {v} {t}</label>'
            for v, t in ((0, "틀림"), (1, "일부"), (2, "맞음"))
        )

    items = []
    for i, c in enumerate(cases, 1):
        cid = html.escape(c["id"])
        evidence = "\n\n---\n\n".join(c.get("evidence") or [])
        items.append(
            f'<section data-id="{cid}">'
            f"<h2>{i}. <code>{cid}</code> {html.escape(c['question'])}</h2>"
            f'<pre class="answer">{html.escape(c.get("answer", ""))}</pre>'
            f"<details><summary>근거 원문 ({len(evidence):,}자)</summary>"
            f"<pre>{html.escape(evidence)}</pre></details>"
            f'<div class="rate"><b>근거대로 맞나</b>{radios(cid, "grounded")}</div>'
            f'<div class="rate"><b>질문에 답했나</b>{radios(cid, "answered")}</div>'
            f'<input class="memo" name="{cid}-memo" placeholder="메모 (틀린 부분 등)">'
            "</section>"
        )
    template = (Path(__file__).parent / "human_sheet.html").read_text(encoding="utf-8")
    return template.replace("__SOURCE__", html.escape(source)).replace(
        "__ITEMS__", "\n".join(items)
    )


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):  # 같은 값은 평균 순위
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(a: list[float], b: list[float]) -> float | None:
    """순위 상관. 한쪽 값이 모두 같으면 계산할 수 없어 None."""
    if len(a) < 3:
        return None
    ra, rb = _ranks(a), _ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb, strict=True))
    va = sum((x - ma) ** 2 for x in ra) ** 0.5
    vb = sum((y - mb) ** 2 for y in rb) ** 0.5
    return round(cov / (va * vb), 3) if va and vb else None


def compare(labels: dict[str, dict], judges: dict[str, dict[str, dict]]) -> dict:
    """사람 점수(0~2 → 0~1)와 채점 모델별 RAGAS 점수를 문항 단위로 비교한다.

    judges: {채점 모델: {문항 id: {faithfulness, answer_relevancy, ...}}}
    """
    out: dict = {"cases": 0, "judges": {}}
    for judge, scores in judges.items():
        row = {}
        for human_key, metric, _ in PAIRS:
            ids = [
                i
                for i, lab in labels.items()
                if lab.get(human_key) not in (None, "")
                and scores.get(i, {}).get(metric) is not None
            ]
            human = [int(labels[i][human_key]) / 2 for i in ids]
            model = [float(scores[i][metric]) for i in ids]
            n = len(ids)
            row[metric] = {
                "n": n,
                "human_avg": round(sum(human) / n, 3) if n else None,
                "judge_avg": round(sum(model) / n, 3) if n else None,
                # 양수면 채점 모델이 사람보다 후하게 줬다는 뜻
                "inflation": round((sum(model) - sum(human)) / n, 3) if n else None,
                "spearman": spearman(human, model),
                # 사람은 틀렸다(0)고 했는데 채점 모델은 0.7 이상 준 문항
                "missed": [
                    i for i, h, m in zip(ids, human, model, strict=True) if h == 0 and m >= 0.7
                ],
            }
            out["cases"] = max(out["cases"], n)
        out["judges"][judge] = row
    return out


def compare_files(labels_path: Path, ragas_paths: list[Path]) -> Path:
    labels = json.loads(labels_path.read_text(encoding="utf-8"))["labels"]
    judges = {}
    for p in ragas_paths:
        payload = json.loads(p.read_text(encoding="utf-8"))
        judges[payload["judge_model"]] = {s["id"]: s for s in payload["scores"]}
    result = compare(labels, judges)
    lines = [
        f"# 사람 채점 vs 자동 채점 ({labels_path.stem})",
        "",
        "사람 점수 0·1·2를 0·0.5·1로 바꿔 RAGAS 점수와 같은 문항끼리 비교했다.",
        "부풀림 = 채점 모델 평균 − 사람 평균 (양수면 후하게 줌).",
        "순위 상관은 1에 가까울수록 사람과 같은 문항을 낮게 봄.",
        "",
        "| 채점 모델 | 지표 | 문항 | 사람 평균 | 모델 평균 | 부풀림 | 순위 상관 "
        "| 사람은 틀림·모델은 0.7↑ |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for judge, row in result["judges"].items():
        for _, metric, name in PAIRS:
            r = row[metric]
            missed = ", ".join(f"`{i}`" for i in r["missed"]) or "없음"
            lines.append(
                f"| {judge} | {name} | {r['n']} | {r['human_avg']} | {r['judge_avg']} | "
                f"{r['inflation']} | {r['spearman']} | {missed} |"
            )
    report = labels_path.with_name(f"{labels_path.stem}-compare.md")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    labels_path.with_name(f"{labels_path.stem}-compare.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report
