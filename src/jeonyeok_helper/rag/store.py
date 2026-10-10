"""Chroma 벡터 저장소. 문서 ID(doc_id)로 upsert해서 다시 수집해도 중복이 생기지 않는다."""

from __future__ import annotations

from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from jeonyeok_helper.config import get_settings


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

    def search(self, query: str, k: int) -> list[Document]:
        return self.db.similarity_search(query, k=k)

    def count(self) -> int:
        return self.db._collection.count()
