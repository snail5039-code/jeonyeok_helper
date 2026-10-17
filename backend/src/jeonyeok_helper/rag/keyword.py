"""키워드 검색 (BM25 + Kiwi 형태소 분석). 벡터 검색과 함께 쓰는 하이브리드 검색의 한쪽.

벡터 검색은 뜻이 비슷한 글을 잘 찾지만 '공무상요양비', '제25조', '전직지원금'처럼 정확한 용어나
조문 번호는 놓치기 쉽다. BM25는 그 단어가 실제로 들어 있는 조각을 찾는다. 한국어는 조사가 붙어
('요양비를', '요양비는') 띄어쓰기로 자르면 같은 단어로 보지 못하므로 Kiwi로 형태소를 나눈다.

색인은 한 번 만들어 Postgres의 cache_entry 표(db/cache.py)에 통째로(문서·형태소·BM25 통계)
저장한다. Docker 이미지를 새로 만들어도 DB에 남는다. 다음 실행에서는 pgvector 표의 지문(조각 id와
본문의 md5)만 비교해(약 0.05초) 같으면 저장한 것을 그대로 읽고, 자료가 바뀌었으면 새로 들어온
조각만 형태소 분석해 다시 저장한다.
자료를 넣는 명령(jeonyeok-rag)은 끝날 때 색인을 다시 저장하고, 서버는 켜질 때 미리 읽어 둔다.
"""

from __future__ import annotations

import logging
import pickle
import threading
from pathlib import Path

from langchain_core.documents import Document
from sqlalchemy import text

log = logging.getLogger(__name__)

CACHE_NAMESPACE = "bm25"
# 저장 형식이 바뀌면 올린다 (예전 형식 파일은 다시 만든다)
INDEX_VERSION = 1
# 명사·동사·형용사 어근·외국어·숫자만 쓴다 (조사·어미는 검색에 도움이 안 된다)
KEEP_TAGS = ("NNG", "NNP", "NNB", "NR", "VV", "VA", "XR", "SL", "SN", "SH")

_FROM = (
    " FROM langchain_pg_embedding e JOIN langchain_pg_collection c"
    " ON e.collection_id = c.uuid WHERE c.name = :collection"
)
_ALL_DOCS = text("SELECT e.id, e.document, e.cmetadata" + _FROM)
# 조각이 하나라도 더해지거나 지워지거나 바뀌면 달라지는 지문
_SIGNATURE = text(
    "SELECT count(*) || ':' || coalesce(md5(string_agg(e.id || md5(e.document), ','"
    " ORDER BY e.id)), '')" + _FROM
)


class Tokenizer:
    """Kiwi는 띄우는 데 0.6초쯤 걸려 처음 쓸 때 만든다."""

    def __init__(self):
        self._kiwi = None

    @property
    def kiwi(self):
        if self._kiwi is None:
            from kiwipiepy import Kiwi

            self._kiwi = Kiwi()
        return self._kiwi

    def __call__(self, text: str) -> list[str]:
        return [t.form for t in self.kiwi.tokenize(text) if t.tag.startswith(KEEP_TAGS)]

    def many(self, texts: list[str]) -> list[list[str]]:
        return [
            [t.form for t in tokens if t.tag.startswith(KEEP_TAGS)]
            for tokens in self.kiwi.tokenize(texts)
        ]


def _key(doc_id: str, content: str) -> str:
    """같은 id라도 본문이 바뀌면 다시 분석하도록 본문 길이·앞부분까지 넣는다."""
    return f"{doc_id}:{len(content)}:{content[:40]}"


class KeywordIndex:
    """BM25 색인. docs는 (id, 본문, 메타데이터) 목록, tokens는 같은 순서의 형태소 목록."""

    def __init__(self, docs: list[tuple[str, str, dict]], tokens: list[list[str]], bm25=None):
        from rank_bm25 import BM25Okapi

        self.docs = docs
        self.tokens = tokens
        self.bm25 = bm25 if bm25 is not None else BM25Okapi(tokens)
        self.tokenizer = Tokenizer()

    def search(self, query: str, k: int, allow=None) -> list[Document]:
        """allow(metadata) → bool 로 거른 뒤 점수가 높은 k개. 겹치는 단어가 없으면 빼고 준다."""
        q = self.tokenizer(query)
        if not q:
            return []
        scores = self.bm25.get_scores(q)
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        out: list[Document] = []
        for i in order:
            if scores[i] <= 0 or len(out) >= k:
                break
            doc_id, content, meta = self.docs[i]
            if allow is None or allow(meta):
                out.append(Document(page_content=content, metadata=dict(meta), id=doc_id))
        return out


def signature(session_factory, collection: str) -> str:
    with session_factory() as session:
        return session.execute(_SIGNATURE, {"collection": collection}).scalar_one()


class SavedIndexStorage:
    """색인을 Postgres 저장 캐시에 둔다. DB를 쓸 수 없으면 저장하지 않는다(매번 만든다)."""

    def __init__(self, collection: str):
        self.collection = collection

    def load(self) -> dict:
        from jeonyeok_helper.db.cache import MISSING, get_saved_cache

        saved = get_saved_cache()
        if saved is None:
            return {}
        try:
            value = saved.get(CACHE_NAMESPACE, self.collection)
        except Exception:
            log.warning("저장한 키워드 색인 읽기 실패", exc_info=True)
            return {}
        return {} if value is MISSING else _valid(value)

    def save(self, payload: dict) -> None:
        from jeonyeok_helper.db.cache import get_saved_cache

        if saved := get_saved_cache():
            saved.put(CACHE_NAMESPACE, self.collection, payload)


class FileIndexStorage:
    """파일에 둔다 (테스트용)."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        try:
            return _valid(pickle.loads(self.path.read_bytes()))
        except (OSError, pickle.UnpicklingError, EOFError, AttributeError, ImportError):
            return {}

    def save(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
        tmp.replace(self.path)  # 쓰다가 끊겨도 예전 파일이 깨지지 않게


def _valid(saved) -> dict:
    return saved if isinstance(saved, dict) and saved.get("version") == INDEX_VERSION else {}


def build_index(session_factory, collection: str, storage=None) -> KeywordIndex:
    """저장한 색인이 지금 DB와 같으면 그대로 읽고, 다르면 바뀐 조각만 분석해 다시 만들어
    저장한다."""
    storage = storage if storage is not None else SavedIndexStorage(collection)
    sig = signature(session_factory, collection)
    saved = storage.load()
    if saved.get("signature") == sig:
        log.info("키워드 색인: 저장한 색인 사용 (%d개 조각)", len(saved["docs"]))
        return KeywordIndex(saved["docs"], saved["tokens"], saved["bm25"])

    with session_factory() as session:
        rows = session.execute(_ALL_DOCS, {"collection": collection}).all()
    docs = [(str(r[0]), r[1] or "", r[2] or {}) for r in rows]
    # 예전 색인의 형태소 분석 결과는 본문이 그대로인 조각에 다시 쓴다
    old_docs, old_tokens = saved.get("docs", []), saved.get("tokens", [])
    known = {_key(d[0], d[1]): toks for d, toks in zip(old_docs, old_tokens, strict=True)}
    todo = [d for d in docs if _key(d[0], d[1]) not in known]
    if todo:
        log.info("키워드 색인: %d개 조각 형태소 분석", len(todo))
        for d, toks in zip(todo, Tokenizer().many([d[1] for d in todo]), strict=True):
            known[_key(d[0], d[1])] = toks
    index = KeywordIndex(docs, [known[_key(d[0], d[1])] for d in docs])
    try:
        storage.save(
            {
                "version": INDEX_VERSION,
                "signature": sig,
                "docs": docs,
                "tokens": index.tokens,
                "bm25": index.bm25,
            }
        )
        log.info("키워드 색인 저장 (%d개 조각)", len(docs))
    except Exception:
        log.warning("키워드 색인 저장 실패 (이번 실행에서는 그대로 씀)", exc_info=True)
    return index


class LazyKeywordIndex:
    """처음 쓸 때 한 번만 읽거나 만든다. 그동안 다른 검색은 기다린다.
    실패하면 키워드 검색 없이 간다."""

    def __init__(self, session_factory, collection: str, storage=None):
        self._args = (session_factory, collection, storage)
        self._index: KeywordIndex | None = None
        self._failed = False
        self._lock = threading.Lock()

    def get(self) -> KeywordIndex | None:
        if self._index is not None or self._failed:
            return self._index
        with self._lock:
            if self._index is None and not self._failed:
                try:
                    self._index = build_index(*self._args)
                except Exception:
                    log.warning("키워드 색인 만들기 실패, 벡터 검색만 씁니다.", exc_info=True)
                    self._failed = True
        return self._index

    def rebuild(self) -> KeywordIndex | None:
        """자료를 새로 넣은 뒤 지금 DB 기준으로 다시 만들어 저장한다."""
        self.reset()
        return self.get()

    def reset(self) -> None:
        with self._lock:
            self._index, self._failed = None, False


_shared: dict[str, LazyKeywordIndex] = {}
_shared_lock = threading.Lock()


def shared_index(session_factory, collection: str):
    """같은 컬렉션은 프로세스 안에서 색인 하나를 같이 쓴다 (서버 시작 때 미리 읽은 것을 MCP
    도구의 검색기가 그대로 쓰도록)."""
    with _shared_lock:
        if collection not in _shared:
            _shared[collection] = LazyKeywordIndex(session_factory, collection)
        return _shared[collection]
