"""사람 채점 (human_eval.py)."""

import json

from jeonyeok_helper.human_eval import compare, compare_files, make_sheet, pick_cases, spearman


def _results(n: int) -> list[dict]:
    rows = [
        {"id": f"c{i:02d}", "question": f"질문 {i}", "answer": f"답 {i}", "evidence": ["원문"]}
        for i in range(n)
    ]
    rows.append({"id": "ask", "question": "되묻기", "answer": "?", "evidence": [], "asked": True})
    return rows


def test_pick_cases_skips_unscorable_and_is_repeatable():
    first = pick_cases(_results(50), 30)
    assert len(first) == 30 and all(c["id"] != "ask" for c in first)
    assert [c["id"] for c in first] == [c["id"] for c in pick_cases(_results(50), 30)]


def test_make_sheet_writes_page_and_ids(tmp_path):
    src = tmp_path / "run.json"
    src.write_text(json.dumps({"results": _results(5)}, ensure_ascii=False), encoding="utf-8")
    page = make_sheet(src, 3, out_dir=tmp_path)
    text = page.read_text(encoding="utf-8")
    assert text.count("<section") == 3 and "결과 저장" in text
    assert len((tmp_path / "run-ids.txt").read_text(encoding="utf-8").split()) == 3


def test_spearman():
    assert spearman([0, 0.5, 1], [0.1, 0.5, 0.9]) == 1.0
    assert spearman([0, 0.5, 1], [0.9, 0.5, 0.1]) == -1.0
    assert spearman([1, 1, 1], [0.1, 0.5, 0.9]) is None


def test_compare_reports_inflation_and_cases_the_judge_missed():
    labels = {
        "a": {"grounded": "2", "answered": "2"},
        "b": {"grounded": "0", "answered": "2"},
        "c": {"grounded": "1", "answered": None},
    }
    lenient = {
        "a": {"faithfulness": 1.0, "answer_relevancy": 0.9},
        "b": {"faithfulness": 0.9, "answer_relevancy": 0.9},
        "c": {"faithfulness": 0.8, "answer_relevancy": 0.9},
    }
    r = compare(labels, {"flash": lenient})["judges"]["flash"]
    assert r["faithfulness"]["n"] == 3 and r["faithfulness"]["human_avg"] == 0.5
    assert r["faithfulness"]["inflation"] == 0.4  # 0.9 - 0.5
    assert r["faithfulness"]["missed"] == ["b"]
    assert r["answer_relevancy"]["n"] == 2  # 사람이 안 매긴 c는 뺀다


def test_compare_files_writes_report(tmp_path):
    labels = tmp_path / "run-labels.json"
    labels.write_text(
        json.dumps({"labels": {"a": {"grounded": "2", "answered": "2"}}}), encoding="utf-8"
    )
    ragas = tmp_path / "run-ragas.json"
    ragas.write_text(
        json.dumps(
            {
                "judge_model": "gemini-2.5-flash",
                "scores": [{"id": "a", "faithfulness": 1.0, "answer_relevancy": 1.0}],
            }
        ),
        encoding="utf-8",
    )
    report = compare_files(labels, [ragas])
    assert "gemini-2.5-flash" in report.read_text(encoding="utf-8")
