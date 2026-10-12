"""Chroma 벡터 저장소. 문서 ID(doc_id)로 upsert해서 다시 수집해도 중복이 생기지 않는다."""

from __future__ import annotations

from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from jeonyeok_helper.benefits.regions import province_variants, region_keys
from jeonyeok_helper.config import get_settings


def region_filter(region: str | None) -> dict:
    """조례는 사용자 지역 것만 검색한다. 지자체마다 비슷한 조례가 수백 개라
    섞어 두면 법령이 밀려난다. 지역을 모르면 조례는 빼고 법령·파일만 찾는다."""
    not_ordinance = {"source_type": {"$ne": "ordinance"}}
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


class RegulationStore:
    def __init__(
        self,
        embeddings: Embeddings | None = None,
        persist_dir: Path | None = None,
        collection: str | None = None,
    ):
        s = get_settings()
        if embeddings is None:
            from jeonyeok_helper.llm import get_embeddings

            embeddings = get_embeddings()
        self.db = Chroma(
            collection_name=collection or s.chroma_collection,
            embedding_function=embeddings,
            persist_directory=str(persist_dir or s.chroma_dir),
        )

    def upsert(self, docs: list[Document], batch_size: int = 64) -> int:
        """임베딩 API 한도를 넘지 않도록 나눠서 넣는다."""
        for start in range(0, len(docs), batch_size):
            batch = docs[start : start + batch_size]
            self.db.add_documents(batch, ids=[d.metadata["doc_id"] for d in batch])
        return len(docs)

    def search(self, query: str, k: int, region: str | None = None) -> list[Document]:
        return self.db.similarity_search(query, k=k, filter=region_filter(region))

    def replace_source(self, source: str, docs: list[Document]) -> int:
        """파일 하나의 조각을 새 조각으로 바꾼다. 조각 수가 줄면 예전 조각이 남으므로 새 목록에
        없는 것만 지운다. 파일 조각을 통째로(수천 개) 지웠다가 Windows에서 Chroma 색인이
        손상된 적이 있어(2026-10-12, 문서를 새 저장소로 옮겨 복구) 한꺼번에 지우지 않는다."""
        new_ids = {d.metadata["doc_id"] for d in docs}
        old_ids = self.db._collection.get(where={"source": source}, include=[])["ids"]
        if stale := [i for i in old_ids if i not in new_ids]:
            self.db._collection.delete(ids=stale)
        return self.upsert(docs)

    def count(self) -> int:
        return self.db._collection.count()
