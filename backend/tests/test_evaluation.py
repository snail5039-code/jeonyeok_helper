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
    tools_used,
)

KNOWN_KEYS = {
    "id",
    "category",
    "question",
    "sources_any",
    "answer_any",
    "answer_all",
    "tools_any",
    "profile",
    "should_ask",
    "should_talk",
    "answer_none",
}


def test_question_set_is_valid():
    questions = load_questions()
    assert len(questions) >= 200
    assert len({q["id"] for q in questions}) == len(questions)
    for q in questions:
        assert set(q) <= KNOWN_KEYS, q["id"]
        assert q["category"] in CATEGORY_NAMES
        # 채점할 거리가 하나 이상 있어야 한다.
        checks = {"sources_any", "answer_any", "answer_all", "tools_any"}
        checks |= {"profile", "should_ask", "should_talk", "answer_none"}
        assert checks & set(q), q["id"]
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


def test_grade_checks_which_tools_ran():
    evidence = ['[find_stores] {"stores": []}', "[search_regulations] {}", "도구 결과 없음"]
    tools = tools_used(evidence)
    assert tools == ["find_stores", "search_regulations"]

    case = {"tools_any": ["find_stores"]}
    assert grade(case, "a", False, [], {}, tools)[0].passed
    missed = grade({"tools_any": ["search_jobs"]}, "a", False, [], {}, tools)[0]
    assert not missed.passed and "find_stores" in missed.detail


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
            "question": "병사로 전역했는데 군복무 크레딧이 뭐예요?",
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
    # 문항마다 단계별 사용량이 붙고, 요약에 평균이 나온다 (가짜 모델이라 토큰은 0일 수 있음)
    assert all(isinstance(r.usage, dict) for r in results)
    assert {"avg_cost", "avg_input", "by_step"} <= summary["usage"].keys()

    report = save(results, summary, out_dir=tmp_path)
    text = report.read_text(encoding="utf-8")
    assert "의무복무 병사" in text and "`c99`" in text
    assert "토큰·비용" in text
    assert report.with_suffix(".json").exists()


# ---------- 규정 검색 골든셋 ----------


def test_retrieval_grading_counts_groups_rank_and_leaks():
    from jeonyeok_helper.retrieval_eval import RetrievalResult, grade_retrieval, load_golden

    case = {
        "expect": [["국민연금법 제18조"], ["국민연금법 시행령 제24조의3", "크레딧 안내"]],
        "forbid": ["경기도"],
    }
    cites = ["병역법 제1조", "국민연금법 제18조(군 복무기간)", "경기도 조례 제1조"]
    found, first, leaked = grade_retrieval(case, cites)
    assert found == [True, False] and first == 2 and leaked == ["경기도 조례 제1조"]

    r = RetrievalResult("x", "c", "q", cites, found, first, leaked)
    assert r.recall == 0.5 and not r.hit and r.rr == 0  # 다른 지역 출처가 섞이면 실패

    golden = load_golden()
    assert len({c["id"] for c in golden}) == len(golden) >= 50
    # YAML에서 '안내: …'처럼 콜론이 있으면 문자열이 아니라 dict로 읽힌다
    alts = [a for c in golden for g in c["expect"] for a in g] + [
        f for c in golden for f in c.get("forbid", [])
    ]
    assert all(isinstance(a, str) and a for a in alts)


def test_retrieval_eval_runs_with_fake_retriever():
    from langchain_core.documents import Document

    from jeonyeok_helper.retrieval_eval import run_retrieval_eval, summarize_retrieval

    class Fake:
        def retrieve(self, question, k=6, region=None):
            return [Document(page_content="", metadata={"citation": f"{question} 제1조"})]

    cases = [
        {"id": "a", "category": "x", "question": "예비군법", "expect": [["예비군법"]]},
        {"id": "b", "category": "x", "question": "병역법", "expect": [["군인연금법"]]},
    ]
    s = summarize_retrieval(run_retrieval_eval(Fake(), cases))["overall"]
    assert s["hit"] == 0.5 and s["mrr"] == 0.5


def test_grade_checks_whether_guide_talked_or_searched():
    case = {"should_talk": True}
    assert grade(case, answer="안녕!", asked=True, sources=[], profile={}, talked=True)[0].passed
    assert not grade(case, answer="", asked=False, sources=[], profile={}, talked=False)[0].passed


def test_answer_none_fails_when_forbidden_words_appear_even_in_a_question_back():
    case = {"answer_none": ["1234567"]}
    leaked = grade(case, answer="990101-1234567 확인했어요", asked=True, sources=[], profile={})
    clean = grade(case, answer="[주민등록번호 가림]", asked=True, sources=[], profile={})
    assert not leaked[0].passed and clean[0].passed


# ---------- 단계별 모델 교체 실험 ----------


def test_sample_cases_keeps_every_category_and_is_repeatable():
    from jeonyeok_helper.evaluation import sample_cases

    cases = [{"id": f"{cat}{i}", "category": cat} for cat in "abc" for i in range(20)]
    picked = sample_cases(cases, 12)
    assert len(picked) == 12 and {c["category"] for c in picked} == {"a", "b", "c"}
    assert picked == sample_cases(cases, 12)


def test_agreement_counts_same_routing_profile_and_ask_back():
    from jeonyeok_helper.evaluation import agreement

    def row(i, tools, profile, asked=False, score=1.0):
        return {"id": i, "question": i, "asked": asked, "tools": tools, "profile": profile,
                "score": score}  # fmt: skip

    base = [row("a", ["search_regulations"], {"service_type": "conscript"}),
            row("b", ["search_benefits"], {})]  # fmt: skip
    other = [row("a", ["search_regulations"], {"service_type": "conscript", "region": None}),
             row("b", ["search_regulations"], {}, score=0.5)]  # fmt: skip
    ag = agreement(base, other)
    assert ag["cases"] == 2
    assert ag["routing"] == 0.5 and ag["profile"] == 1.0 and ag["asked"] == 1.0
    assert {d["what"] for d in ag["diffs"]} == {"라우팅", "점수"}


def test_build_components_rejects_unknown_step():
    import pytest

    from jeonyeok_helper.agents.runtime import build_components

    with pytest.raises(ValueError, match="모르는 단계"):
        build_components(object(), [], step_llms={"answer": object()})


def test_retrieval_grading_does_not_count_branch_articles():
    from jeonyeok_helper.retrieval_eval import GOLDEN_FILE, cites, load_golden

    assert cites("예비군법 제10조(직장 보장)", "예비군법 제10조")
    assert cites("예비군법 제10조", "예비군법 제10조")
    assert not cites("예비군법 제10조의2(학생 예비군)", "예비군법 제10조")
    assert cites("예비군법 제10조의2(학생 예비군)", "예비군법 제10조의2")
    assert cites("국방부 전직지원 안내서 12쪽", "전직지원 안내서")  # 조문이 아니면 그대로

    # 처음 보는 문항 파일도 같은 형식
    holdout = load_golden(GOLDEN_FILE.with_name("retrieval_holdout.yaml"))
    assert len({c["id"] for c in holdout}) == len(holdout) >= 20
