import asyncio
from contextlib import asynccontextmanager

from helpers import make_components
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from jeonyeok_helper.agents.graph import build_graph
from jeonyeok_helper.agents.state import Profile, Route
from jeonyeok_helper.evaluation import (
    CATEGORY_NAMES,
    grade,
    load_questions,
    run_eval,
    save,
    summarize,
)

KNOWN_KEYS = {"id", "category", "question", "sources_any", "answer_any", "profile", "should_ask"}


def test_question_set_is_valid():
    questions = load_questions()
    assert len(questions) == 30
    assert len({q["id"] for q in questions}) == 30
    for q in questions:
        assert set(q) <= KNOWN_KEYS, q["id"]
        assert q["category"] in CATEGORY_NAMES
        # 채점할 거리가 하나 이상 있어야 한다.
        assert {"sources_any", "answer_any", "profile", "should_ask"} & set(q), q["id"]
    # 유형마다 고르게 들어 있다.
    counts = {c: sum(q["category"] == c for q in questions) for c in CATEGORY_NAMES}
    assert min(counts.values()) >= 3


def test_grade_passes_matching_answer():
    case = {
        "sources_any": ["국민연금법"],
        "answer_any": ["가입기간"],
        "profile": {"region": "서울", "service_years": 4},
        "should_ask": False,
    }
    checks = grade(
        case,
        answer="군 복무기간을 가입기간으로 인정해요",
        asked=False,
        sources=[{"title": "국민연금법 제18조"}],
        profile={"region": "서울특별시", "service_years": 4.0},
    )
    assert all(c.passed for c in checks), [(c.name, c.detail) for c in checks]


def test_grade_reports_what_failed():
    case = {"sources_any": ["예비군법"], "answer_any": ["예비군"], "should_ask": False}
    checks = grade(case, answer="잘 모르겠어요", asked=False, sources=[], profile={})
    assert [(c.name, c.passed) for c in checks] == [
        ("바로 답변", True),
        ("근거 출처", False),
        ("답변 내용", False),
    ]


def test_grade_ask_back_skips_answer_checks():
    checks = grade(
        {"should_ask": True, "answer_any": ["x"]}, answer="복무 형태가?", asked=True,
        sources=[], profile={},
    )  # fmt: skip
    assert [(c.name, c.passed) for c in checks] == [("되묻기", True)]


def test_run_eval_end_to_end_with_fake_agent(tmp_path):
    components, _ = make_components(
        [Route(next="regulation"), Route(next="answer")],
        profile=Profile(service_type="conscript"),
    )
    graph = build_graph(components, checkpointer=InMemorySaver(), store=InMemoryStore())

    @asynccontextmanager
    async def factory():
        yield graph

    cases = [
        {
            "id": "c01",
            "category": "conscript",
            "question": "군복무 크레딧이 뭐예요?",
            "sources_any": ["국민연금법"],
            "answer_any": ["최종 답변"],
            "profile": {"service_type": "conscript"},
        },
        {
            "id": "c99",
            "category": "conscript",
            "question": "예비군?",
            "sources_any": ["예비군법"],
        },
    ]
    results = asyncio.run(run_eval(factory, cases))

    assert [r.score for r in results] == [1.0, 0.0]
    summary = summarize(results)
    assert summary["overall"]["perfect"] == 1
    assert summary["by_category"]["conscript"]["cases"] == 2

    report = save(results, summary, out_dir=tmp_path)
    text = report.read_text(encoding="utf-8")
    assert "의무복무 병사" in text and "`c99`" in text
    assert report.with_suffix(".json").exists()
