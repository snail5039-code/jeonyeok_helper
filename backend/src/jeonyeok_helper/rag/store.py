"""pgvector(PostgreSQL) 벡터 저장소. 문서 ID(doc_id)로 upsert해서 다시 수집해도 중복이 없다.

처음에는 Chroma(로컬 파일)였다. 배포(RDS PostgreSQL 하나로 피드백 DB와 함께), 여러 서버에서의
동시 접근, 백업을 위해 바꿨다. Chroma는 Windows에서 대량 삭제 뒤 색인이 손상된 적도 있다.

임베딩이 3,072차원이라 pgvector의 HNSW 색인(최대 2,000차원)은 쓰지 않는다. 문서 1만 개
규모에서는 전체 비교로도 충분히 빠르다 (조례는 지역 필터로 먼저 줄인다).
"""

from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_postgres import PGVector
from sqlalchemy import text

from jeonyeok_helper.benefits.regions import province_variants, region_keys
from jeonyeok_helper.config import get_settings


def region_filter(region: str | None) -> dict:
    """조례는 사용자 지역 것만 검색한다. 지자체마다 비슷한 조례가 수백 개라
    섞어 두면 법령이 밀려난다. 지역을 모르면 조례는 빼고 법령·파일만 찾는다."""
    # JSONB에서는 키가 없는 문서가 $ne에 걸리지 않아서 '키 없음'도 같이 넣는다
    not_ordinance = {
        "$or": [{"source_type": {"$ne": "ordinance"}}, {"source_type": {"$exists": False}}]
    }
    keys = region_keys(region)
    if not keys:
        return not_ordinance
    # 시도 이름은 통합 전후 표기('광주', '(구)광주', '전남광주통합')를 모두 본다
    sidos = sorted({v for k in keys for v in province_variants(k)})
    local = [
        {"sigungu": {"$in": keys}},  # 시군구 조례
        {"$and": [{"sido": {"$in": sidos}}, {"sigungu": ""}]},  # 시도 조례
    ]
    if len(keys) == 1:  # '경기'처럼 시도만 말하면 그 안의 시군구 조례도
        local.append({"sido": {"$in": sidos}})
    return {"$or": [not_ordinance, *local]}


def region_allows(meta: dict, region: str | None) -> bool:
    """region_filter와 같은 규칙을 파이썬으로 (키워드 검색 결과를 거를 때)."""
    if meta.get("source_type") != "ordinance":
        return True
    keys = region_keys(region)
    if not keys:
        return False
    sidos = {v for k in keys for v in province_variants(k)}
    if meta.get("sigungu") in keys:
        return True
    if meta.get("sido") in sidos and (meta.get("sigungu", "") == "" or len(keys) == 1):
        return True
    return False


# langchain-postgres가 만드는 표: langchain_pg_collection(이름) ← langchain_pg_embedding(문서)
_IDS_BY_SOURCE = text(
    "SELECT e.id FROM langchain_pg_embedding e JOIN langchain_pg_collection c"
    " ON e.collection_id = c.uuid WHERE c.name = :collection AND e.cmetadata->>'source' = :source"
)
_COUNT = text(
    "SELECT count(*) FROM langchain_pg_embedding e JOIN langchain_pg_collection c"
    " ON e.collection_id = c.uuid WHERE c.name = :collection"
)


class RegulationStore:
    def __init__(
        self,
        embeddings: Embeddings | None = None,
        url: str | None = None,
        collection: str | None = None,
    ):
        s = get_settings()
        if embeddings is None:
            from jeonyeok_helper.llm import get_embeddings

            embeddings = get_embeddings()
        self.collection = collection or s.vector_collection
        self.db = PGVector(
            embeddings=embeddings,
            connection=url or s.database_url,
            collection_name=self.collection,
            use_jsonb=True,
        )
        from jeonyeok_helper.rag.keyword import shared_index

        self.keywords = shared_index(self.db._make_sync_session, self.collection)

    def upsert(self, docs: list[Document], batch_size: int = 64) -> int:
        """임베딩 API 한도를 넘지 않도록 나눠서 넣는다. 같은 doc_id는 덮어쓴다."""
        for start in range(0, len(docs), batch_size):
            batch = docs[start : start + batch_size]
            self.db.add_documents(batch, ids=[d.metadata["doc_id"] for d in batch])
        return len(docs)

    def search(self, query: str, k: int, region: str | None = None) -> list[Document]:
        return self.db.similarity_search(query, k=k, filter=region_filter(region))

    def keyword_search(self, query: str, k: int, region: str | None = None) -> list[Document]:
        """BM25 키워드 검색 (하이브리드 검색의 한쪽). 색인이 없으면 빈 목록."""
        index = self.keywords.get()
        if index is None:
            return []
        return index.search(query, k, allow=lambda m: region_allows(m, region))

    def replace_source(self, source: str, docs: list[Document]) -> int:
        """파일 하나의 조각을 새 조각으로 바꾼다. 조각 수가 줄면 예전 조각이 남으므로
        새 목록에 없는 것만 지운다."""
        new_ids = {d.metadata["doc_id"] for d in docs}
        with self.db._make_sync_session() as session:
            rows = session.execute(
                _IDS_BY_SOURCE, {"collection": self.collection, "source": source}
            )
            old_ids = [r[0] for r in rows]
        if stale := [i for i in old_ids if i not in new_ids]:
            self.db.delete(ids=stale)
        return self.upsert(docs)

    def count(self) -> int:
        with self.db._make_sync_session() as session:
            return session.execute(_COUNT, {"collection": self.collection}).scalar_one()
