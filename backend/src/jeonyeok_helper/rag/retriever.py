"""규정 검색기: 벡터 검색 + HyDE + Re-ranking.

1. HyDE: 사용자 질문("군대 다녀오면 연금 더 받아?")은 법령 문체와 거리가 멀다.
   LLM이 '이 질문에 답하는 조문이라면 이렇게 쓰였을 것'이라는 가상 조문을 만들고,
   원래 질문과 가상 조문 둘 다로 검색해서 후보를 넓힌다.
2. Re-ranking: 넓게 모은 후보를 LLM이 질문과의 관련도로 다시 매겨 상위 k개만 남긴다.

LLM이 없거나 호출에 실패하면 해당 단계만 건너뛰고 벡터 검색 결과를 그대로 쓴다.
"""

from __future__ import annotations

import logging

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

HYDE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "당신은 한국 군 전역자 지원 법령에 밝은 전문가입니다. "
            "사용자 질문에 답이 되는 법령 조문이나 공공기관 안내문이 있다면 "
            "어떻게 쓰여 있을지 법령 문체로 3~5문장 작성하세요. "
            "정확한 조문 번호나 금액은 지어내지 말고 내용만 쓰세요.",
        ),
        ("human", "{question}"),
    ]
)

RERANK_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "질문에 답하는 데 각 문서가 얼마나 직접적인 근거가 되는지 0~10점으로 매기세요. "
            "질문과 대상(병사, 간부, 장기복무, 보훈대상자 등)이 다르면 점수를 낮게 주세요.",
        ),
        ("human", "질문: {question}\n\n문서 목록:\n{documents}"),
    ]
)


class DocScore(BaseModel):
    index: int = Field(description="문서 번호")
    score: float = Field(description="관련도 0~10")


class RerankResult(BaseModel):
    scores: list[DocScore]


class RegulationRetriever:
    def __init__(
        self,
        store,
        llm: BaseChatModel | None = None,
        *,
        use_hyde: bool = True,
        use_rerank: bool = True,
        candidates_per_query: int = 12,
        hyde_chain: Runnable | None = None,
        rerank_chain: Runnable | None = None,
    ):
        self.store = store
        self.candidates_per_query = candidates_per_query
        # 테스트에서는 체인을 직접 주입할 수 있다.
        self.hyde_chain = hyde_chain
        self.rerank_chain = rerank_chain
        if llm is not None:
            if use_hyde and hyde_chain is None:
                self.hyde_chain = HYDE_PROMPT | llm
            if use_rerank and rerank_chain is None:
                self.rerank_chain = RERANK_PROMPT | llm.with_structured_output(RerankResult)
        if not use_hyde:
            self.hyde_chain = None
        if not use_rerank:
            self.rerank_chain = None

    def _hyde(self, question: str) -> str | None:
        if self.hyde_chain is None:
            return None
        try:
            out = self.hyde_chain.invoke({"question": question})
            return str(getattr(out, "text", out)).strip() or None
        except Exception:
            log.warning("HyDE 생성 실패, 원래 질문으로만 검색합니다.", exc_info=True)
            return None

    def _rerank(self, question: str, docs: list[Document], k: int) -> list[Document]:
        if self.rerank_chain is None or len(docs) <= 1:
            return docs[:k]
        listing = "\n\n".join(f"[{i}] {d.page_content[:600]}" for i, d in enumerate(docs))
        try:
            result: RerankResult = self.rerank_chain.invoke(
                {"question": question, "documents": listing}
            )
        except Exception:
            log.warning("Re-ranking 실패, 벡터 검색 순서를 그대로 씁니다.", exc_info=True)
            return docs[:k]
        scores = {s.index: s.score for s in result.scores if 0 <= s.index < len(docs)}
        # 점수를 못 받은 문서는 원래 순서를 유지한 채 뒤로 보낸다.
        order = sorted(range(len(docs)), key=lambda i: (-scores.get(i, -1), i))
        for i in order:
            docs[i].metadata["rerank_score"] = scores.get(i, -1)
        return [docs[i] for i in order[:k]]

    def retrieve(self, question: str, k: int = 6) -> list[Document]:
        # 아직 아무것도 수집하지 않았으면 LLM(HyDE) 호출 없이 바로 끝낸다.
        if hasattr(self.store, "count") and self.store.count() == 0:
            return []
        queries = [question]
        if hypothetical := self._hyde(question):
            queries.append(hypothetical)

        seen: dict[str, Document] = {}
        for q in queries:
            for doc in self.store.search(q, k=self.candidates_per_query):
                seen.setdefault(doc.metadata.get("doc_id") or doc.page_content, doc)
        return self._rerank(question, list(seen.values()), k)


def build_default_retriever() -> RegulationRetriever:
    from jeonyeok_helper.llm import get_chat_model
    from jeonyeok_helper.rag.store import RegulationStore

    return RegulationRetriever(RegulationStore(), llm=get_chat_model(temperature=0))
