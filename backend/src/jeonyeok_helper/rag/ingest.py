"""수집·검색 명령.

uv run jeonyeok-rag laws            # data/laws.yaml의 법령 수집
uv run jeonyeok-rag files           # data/raw/ 의 파일 수집
uv run jeonyeok-rag search "질문"    # 검색 결과 확인
uv run jeonyeok-rag stats           # 저장된 문서 수
"""

from __future__ import annotations

import argparse
from pathlib import Path

from jeonyeok_helper.cli import run_cli
from jeonyeok_helper.config import DATA_DIR, get_settings, load_yaml

LAWS_FILE = DATA_DIR / "laws.yaml"


def load_law_list(path: Path = LAWS_FILE) -> list[dict]:
    return load_yaml(path, "laws")


def ingest_laws(client, store, laws: list[dict]) -> tuple[int, list[str]]:
    """법령별로 수집한다. 한 법령이 실패해도 나머지는 계속 진행. (저장 수, 실패 메시지)."""
    total, errors = 0, []
    for law in laws:
        name = law["name"]
        try:
            docs = client.load_law(name, articles=law.get("articles"))
            total += store.upsert(docs)
            print(f"  ✓ {name}: {len(docs)}개 조문")
        except Exception as e:
            errors.append(f"{name}: {e}")
            print(f"  ✗ {name}: {e}")
    return total, errors


def ingest_files(store, directory: Path) -> tuple[int, list[str]]:
    from jeonyeok_helper.rag.loaders import load_directory

    docs, skipped = load_directory(directory)
    for reason in skipped:
        print(f"  - 건너뜀: {reason}")
    return store.upsert(docs), skipped


def main(argv: list[str] | None = None) -> int:
    return run_cli(lambda: _run(argv))


def _run(argv: list[str] | None) -> int:

    parser = argparse.ArgumentParser(prog="jeonyeok-rag", description="규정 수집과 검색")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("laws", help="법령 수집")
    sub.add_parser("files", help="data/raw 파일 수집")
    sub.add_parser("stats", help="저장된 문서 수")
    p_search = sub.add_parser("search", help="검색 결과 확인")
    p_search.add_argument("question")
    p_search.add_argument("-k", type=int, default=None)
    p_search.add_argument("--no-hyde", action="store_true")
    p_search.add_argument("--no-rerank", action="store_true")
    args = parser.parse_args(argv)

    from jeonyeok_helper.rag.store import RegulationStore

    s = get_settings()
    store = RegulationStore()

    if args.cmd == "laws":
        from jeonyeok_helper.rag.law_api import LawApiClient

        total, errors = ingest_laws(LawApiClient(s.law_api_oc), store, load_law_list())
        print(f"법령 {total}개 조문 저장, 실패 {len(errors)}건")
        return 1 if errors else 0

    if args.cmd == "files":
        total, _ = ingest_files(store, s.raw_docs_dir)
        print(f"파일 청크 {total}개 저장")
        return 0

    if args.cmd == "stats":
        print(f"저장된 문서: {store.count()}개")
        return 0

    from jeonyeok_helper.llm import get_chat_model
    from jeonyeok_helper.rag.retriever import RegulationRetriever

    retriever = RegulationRetriever(
        store,
        llm=get_chat_model(temperature=0),
        use_hyde=not args.no_hyde,
        use_rerank=not args.no_rerank,
    )
    for i, doc in enumerate(retriever.retrieve(args.question, k=args.k or s.retrieval_k), 1):
        score = doc.metadata.get("rerank_score")
        print(f"\n[{i}] {doc.metadata.get('citation')}" + (f"  (점수 {score})" if score else ""))
        print(doc.page_content[:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
