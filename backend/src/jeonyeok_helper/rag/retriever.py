"""규정 검색기: 하이브리드 검색(벡터 + BM25) + HyDE + Re-ranking.

0. 하이브리드: 벡터 검색(뜻이 비슷한 글)과 BM25 키워드 검색(용어·조문 번호가 그대로 들어 있는
   글, rag/keyword.py)을 함께 돌리고 RRF(순위 역수 합)로 합친다.
1. HyDE: 사용자 질문("군대 다녀오면 연금 더 받아?")은 법령 문체와 거리가 멀다.
   LLM이 '이 질문에 답하는 조문이라면 이렇게 쓰였을 것'이라는 가상 조문을 만들고,
   원래 질문과 가상 조문 둘 다로 검색해서 후보를 넓힌다.
2. Re-ranking: 넓게 모은 후보를 LLM이 질문과의 관련도로 다시 매겨 상위 k개만 남긴다.

LLM이 없거나 호출에 실패하면 해당 단계만 건너뛰고 벡터 검색 결과를 그대로 쓴다.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

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
            "질문에 답하는 데 직접적인 근거가 되는 문서를 골라 0~10점으로 매기세요. "
            "관련 있는 문서만 점수가 높은 순으로 최대 {k}개까지 쓰고, 나머지는 쓰지 마세요. "
            "질문과 대상(병사, 간부, 장기복무, 보훈대상자 등)이 다르면 점수를 낮게 주세요.",
        ),
        ("human", "질문: {question}\n\n문서 목록:\n{documents}"),
    ]
)


# 사람들이 쓰는 말 → 법령에 적힌 말. 벡터 검색은 '실업급여'와 '구직급여'를 가깝게 보지 못해
# 골든셋에서 고용보험법 조문을 놓쳤다 (후보를 30개로 늘려도 못 찾음).
LEGAL_TERMS = {
    "실업급여": "구직급여 수급 요건",
    "실업수당": "구직급여 수급 요건",
    "군복무 크레딧": "군 복무기간 가입기간 추가 산입",
    "군 복무 크레딧": "군 복무기간 가입기간 추가 산입",
    "퇴직금": "퇴직일시금",
    "가산점": "가점",
    "내일배움카드": "직업능력개발훈련",
    "피부양자": "건강보험 피부양자 적용 대상",
    # '복학 등록금', '장학금'으로 물으면 한국장학재단 자료를 못 찾았다 (RAGAS 자료 관련성 0)
    "등록금": "국가장학금 학자금 지원",
    "장학금": "국가장학금 한국장학재단",
    "학자금": "학자금 대출 한국장학재단",
}


def expand_query(question: str) -> str:
    """질문에 흔히 쓰는 말이 있으면 법령 용어를 덧붙인다."""
    extra = [term for word, term in LEGAL_TERMS.items() if word in question]
    return f"{question} ({', '.join(extra)})" if extra else question


class DocScore(BaseModel):
    index: int = Field(description="문서 번호")
    score: float = Field(description="관련도 0~10")


class RerankResult(BaseModel):
    scores: list[DocScore]


# RRF에서 키워드 검색 결과의 무게 (벡터 검색은 1). 골든셋으로 정한다.
KEYWORD_WEIGHT = 1.0


def rrf(
    *rankings: list[Document], weights: list[float] | None = None, c: int = 60
) -> list[Document]:
    """Reciprocal Rank Fusion: 여러 검색 결과의 순위를 무게 × 1/(c+순위)로 더해 하나로 합친다.
    점수 척도가 다른 벡터 유사도와 BM25 점수를 그대로 비교하지 않아도 된다."""
    weights = weights or [1.0] * len(rankings)
    scores: dict[str, float] = {}
    docs: dict[str, Document] = {}
    for ranking, weight in zip(rankings, weights, strict=True):
        for rank, doc in enumerate(ranking, 1):
            key = doc.metadata.get("doc_id") or doc.page_content
            docs.setdefault(key, doc)
            scores[key] = scores.get(key, 0.0) + weight / (c + rank)
    return [docs[key] for key in sorted(scores, key=lambda key: -scores[key])]


def diversify(docs: list[Document], k: int, per_source: int = 2) -> list[Document]:
    """순서를 지키면서 같은 문서(법령·파일·조례)는 per_source개까지만 고른다.

    600쪽이 넘는 안내서처럼 조각이 많은 문서가 상위를 모두 차지해 법령 근거가 밀려나는 것을
    막는다. 다른 출처가 모자라면 남은 자리는 원래 순서대로 채운다.
    """
    picked: list[Document] = []
    rest: list[Document] = []
    counts: dict[str, int] = {}
    for d in docs:
        key = d.metadata.get("law_name") or d.metadata.get("source") or d.page_content[:50]
        if counts.get(key, 0) < per_source:
            counts[key] = counts.get(key, 0) + 1
            picked.append(d)
        else:
            rest.append(d)
    return (picked + rest)[:k]


class RegulationRetriever:
    def __init__(
        self,
        store,
        llm: BaseChatModel | None = None,
        *,
        use_hyde: bool = True,
        use_rerank: bool = True,
        use_keywords: bool = True,
        candidates_per_query: int = 12,
        keyword_candidates: int = 8,
        keyword_weight: float = KEYWORD_WEIGHT,
        hyde_chain: Runnable | None = None,
        rerank_chain: Runnable | None = None,
    ):
        self.store = store
        self.candidates_per_query = candidates_per_query
        self.keyword_weight = keyword_weight
        # 키워드 검색은 저장소가 지원할 때만 (테스트용 가짜 저장소에는 없을 수 있다)
        self.keyword_candidates = (
            keyword_candidates if use_keywords and hasattr(store, "keyword_search") else 0
        )
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
            return diversify(docs, k)
        # 점수는 상위 k개만 받는다. 후보 전부에 점수를 쓰게 하면 출력이 길어져 2초 넘게 걸린다.
        listing = "\n\n".join(f"[{i}] {d.page_content[:400]}" for i, d in enumerate(docs))
        try:
            result: RerankResult = self.rerank_chain.invoke(
                # 같은 문서 제한(diversify)으로 빠질 수 있어 몇 개 더 받는다
                {"question": question, "documents": listing, "k": k + 3}
            )
        except Exception:
            log.warning("Re-ranking 실패, 벡터 검색 순서를 그대로 씁니다.", exc_info=True)
            return diversify(docs, k)
        scores = {s.index: s.score for s in result.scores if 0 <= s.index < len(docs)}
        # 점수를 못 받은 문서는 원래 순서를 유지한 채 뒤로 보낸다.
        order = sorted(range(len(docs)), key=lambda i: (-scores.get(i, -1), i))
        for i in order:
            docs[i].metadata["rerank_score"] = scores.get(i, -1)
        return diversify([docs[i] for i in order], k)

    def retrieve(self, question: str, k: int = 6, region: str | None = None) -> list[Document]:
        """region을 주면 그 지역 조례도 함께 찾는다."""
        # 아직 아무것도 수집하지 않았으면 LLM(HyDE) 호출 없이 바로 끝낸다.
        if hasattr(self.store, "count") and self.store.count() == 0:
            return []

        def search(q: str) -> list[Document]:
            return self.store.search(q, k=self.candidates_per_query, region=region)

        query = expand_query(question)
        # 가상 조문을 만드는 동안(약 1.7초) 원래 질문으로 벡터·키워드 검색을 먼저 해 둔다.
        with ThreadPoolExecutor(max_workers=3) as pool:
            hyde = pool.submit(self._hyde, question)
            keyword = (
                pool.submit(self.store.keyword_search, query, self.keyword_candidates, region)
                if self.keyword_candidates
                else None
            )
            rankings, weights = [search(query)], [1.0]
            if hypothetical := hyde.result():
                rankings.append(search(hypothetical))
                weights.append(1.0)
            if keyword is not None:
                try:
                    rankings.append(keyword.result())
                    weights.append(self.keyword_weight)
                except Exception:
                    log.warning("키워드 검색 실패, 벡터 검색만 씁니다.", exc_info=True)
        return self._rerank(question, rrf(*rankings, weights=weights), k)


def build_default_retriever() -> RegulationRetriever:
    from jeonyeok_helper.llm import get_fast_chat_model
    from jeonyeok_helper.rag.store import RegulationStore

    # 가상 조문 작성과 점수 매기기는 깊은 추론이 필요 없어 생각을 끈 빠른 설정을 쓴다.
    return RegulationRetriever(RegulationStore(), llm=get_fast_chat_model())


def warm_default_keywords() -> None:
    """서버가 켜질 때 BM25 색인을 미리 읽어 둔다 (저장한 파일이 있으면 1초 안쪽)."""
    from jeonyeok_helper.rag.store import RegulationStore

    index = RegulationStore().keywords.get()
    if index is not None:
        index.tokenizer("전역")  # 형태소 분석기(Kiwi)도 띄워 둔다 (약 0.6초)
