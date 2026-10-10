from pathlib import Path

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models import GenericFakeChatModel
from langchain_core.runnables import RunnableLambda

from jeonyeok_helper.rag.ingest import ingest_laws, load_law_list
from jeonyeok_helper.rag.loaders import load_directory, load_file
from jeonyeok_helper.rag.retriever import DocScore, RegulationRetriever, RerankResult
from jeonyeok_helper.rag.store import RegulationStore


def doc(doc_id: str, text: str = "") -> Document:
    return Document(page_content=text or doc_id, metadata={"doc_id": doc_id, "citation": doc_id})


# ---------- 파일 로더 ----------


def test_load_text_file_chunks_with_citation(tmp_path: Path):
    path = tmp_path / "보훈 안내.txt"
    path.write_text("○ 첫째 항목\n" + "가" * 1500 + "\n\n○ 둘째 항목", encoding="utf-8")

    docs = load_file(path)

    assert len(docs) >= 2  # 800자 기준으로 나뉜다
    assert docs[0].metadata["source_type"] == "file"
    assert docs[0].metadata["citation"] == "보훈 안내 (1번째 단락)"
    assert len({d.metadata["doc_id"] for d in docs}) == len(docs)


def test_hwp_is_rejected_with_guidance(tmp_path: Path):
    path = tmp_path / "안내.hwp"
    path.write_bytes(b"x")
    with pytest.raises(ValueError, match="PDF로 변환"):
        load_file(path)


def test_load_directory_skips_unsupported(tmp_path: Path):
    (tmp_path / "a.md").write_text("# 제목\n내용", encoding="utf-8")
    (tmp_path / "b.hwp").write_bytes(b"x")
    (tmp_path / ".gitkeep").write_text("")

    docs, skipped = load_directory(tmp_path)

    assert {d.metadata["source"] for d in docs} == {"a.md"}
    assert len(skipped) == 1 and "b.hwp" in skipped[0]


# ---------- 벡터 저장소 ----------


def test_store_upsert_does_not_duplicate(tmp_path: Path):
    store = RegulationStore(
        embeddings=DeterministicFakeEmbedding(size=32), persist_dir=tmp_path, collection="test-col"
    )
    docs = [doc("law:1:제1조", "목적"), doc("law:1:제2조", "정의")]

    store.upsert(docs, batch_size=1)
    store.upsert(docs)  # 다시 수집해도

    assert store.count() == 2
    assert {d.metadata["doc_id"] for d in store.search("목적", k=2)} == {
        "law:1:제1조",
        "law:1:제2조",
    }


# ---------- 검색기 ----------


class FakeStore:
    """질문별로 정해진 결과를 돌려주고, 어떤 질문으로 검색됐는지 기록한다."""

    def __init__(self, results: dict[str, list[Document]]):
        self.results = results
        self.queries: list[str] = []

    def search(self, query: str, k: int) -> list[Document]:
        self.queries.append(query)
        return self.results.get(query, [])[:k]


def test_hyde_adds_hypothetical_query_and_dedupes():
    store = FakeStore(
        {
            "군대 다녀오면 연금 더 받아?": [doc("A"), doc("B")],
            "군 복무기간은 가입기간에 산입한다": [doc("B"), doc("C")],
        }
    )
    # 실제 체인(프롬프트 | 채팅 모델)처럼 AIMessage를 돌려주는 가짜 체인
    hyde = RunnableLambda(lambda x: x["question"]) | GenericFakeChatModel(
        messages=iter(["군 복무기간은 가입기간에 산입한다"])
    )
    retriever = RegulationRetriever(store, hyde_chain=hyde)

    result = retriever.retrieve("군대 다녀오면 연금 더 받아?", k=5)

    assert store.queries == ["군대 다녀오면 연금 더 받아?", "군 복무기간은 가입기간에 산입한다"]
    assert [d.metadata["doc_id"] for d in result] == ["A", "B", "C"]


def test_rerank_orders_by_score_and_cuts_to_k():
    store = FakeStore({"q": [doc("A"), doc("B"), doc("C")]})
    rerank = RunnableLambda(
        lambda _: RerankResult(
            scores=[
                DocScore(index=0, score=2),
                DocScore(index=1, score=9),
                DocScore(index=2, score=5),
            ]
        )
    )
    retriever = RegulationRetriever(store, rerank_chain=rerank)

    result = retriever.retrieve("q", k=2)

    assert [d.metadata["doc_id"] for d in result] == ["B", "C"]
    assert result[0].metadata["rerank_score"] == 9


def test_llm_failures_fall_back_to_vector_search():
    def boom(_):
        raise RuntimeError("Gemini 오류")

    store = FakeStore({"q": [doc("A"), doc("B"), doc("C")]})
    retriever = RegulationRetriever(
        store, hyde_chain=RunnableLambda(boom), rerank_chain=RunnableLambda(boom)
    )

    result = retriever.retrieve("q", k=2)

    assert store.queries == ["q"]
    assert [d.metadata["doc_id"] for d in result] == ["A", "B"]


def test_retriever_without_llm_is_plain_vector_search():
    store = FakeStore({"q": [doc("A"), doc("B")]})
    assert [d.metadata["doc_id"] for d in RegulationRetriever(store).retrieve("q", k=1)] == ["A"]


# ---------- 수집 ----------


def test_law_list_is_valid():
    laws = load_law_list()
    assert laws and all(law["name"] for law in laws)
    assert len({law["name"] for law in laws}) == len(laws)


def test_ingest_laws_continues_after_failure():
    class FakeClient:
        def load_law(self, name, articles=None):
            if name == "없는 법":
                raise LookupError("현행 법령을 찾지 못했습니다")
            return [doc(f"law:{name}:제1조")]

    class CountingStore:
        def upsert(self, docs):
            return len(docs)

    total, errors = ingest_laws(
        FakeClient(),
        CountingStore(),
        [{"name": "병역법"}, {"name": "없는 법"}, {"name": "군인연금법"}],
    )

    assert total == 2
    assert len(errors) == 1 and errors[0].startswith("없는 법")


def test_empty_store_skips_llm_calls():
    class EmptyStore(FakeStore):
        def count(self):
            return 0

    def boom(_):
        raise AssertionError("빈 저장소에서는 HyDE를 부르지 않아야 한다")

    store = EmptyStore({})
    retriever = RegulationRetriever(store, hyde_chain=RunnableLambda(boom))

    assert retriever.retrieve("군인연금") == []
    assert store.queries == []
