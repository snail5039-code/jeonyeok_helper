"""수집·검색 명령.

uv run jeonyeok-rag laws            # data/laws.yaml의 법령·행정규칙 수집
uv run jeonyeok-rag ordinances      # data/ordinances.yaml 기준 지자체 조례 수집
uv run jeonyeok-rag interpretations # data/interpretations.yaml 기준 법령해석례 수집
uv run jeonyeok-rag datasets        # 공공데이터 CSV(보훈 민원·구비서류, 장학금) 수집
uv run jeonyeok-rag files          # data/raw/ 의 파일 수집
uv run jeonyeok-rag web            # data/webpages.yaml의 기관 안내 페이지 수집
uv run jeonyeok-rag search "질문"    # 검색 결과 확인
uv run jeonyeok-rag stats           # 저장된 문서 수
"""

from __future__ import annotations

import argparse
from pathlib import Path

from jeonyeok_helper.cli import run_cli
from jeonyeok_helper.config import DATA_DIR, get_settings, load_yaml

LAWS_FILE = DATA_DIR / "laws.yaml"
ORDINANCES_FILE = DATA_DIR / "ordinances.yaml"
INTERPRETATIONS_FILE = DATA_DIR / "interpretations.yaml"


def load_law_list(path: Path = LAWS_FILE) -> list[dict]:
    return load_yaml(path, "laws")


def _ingest_each(store, entries: list[dict], load) -> tuple[int, list[str]]:
    """항목별로 수집한다. 하나가 실패해도 나머지는 계속 진행. (저장 수, 실패 메시지)."""
    total, errors = 0, []
    for entry in entries:
        name = entry["name"]
        try:
            docs = load(entry)
            total += store.upsert(docs)
            print(f"  ✓ {name}: {len(docs)}개 조문")
        except Exception as e:
            errors.append(f"{name}: {e}")
            print(f"  ✗ {name}: {e}")
    return total, errors


def ingest_laws(client, store, laws: list[dict]) -> tuple[int, list[str]]:
    return _ingest_each(store, laws, lambda law: client.load_law(law["name"], law.get("articles")))


def ingest_admin_rules(client, store, path: Path = LAWS_FILE) -> tuple[int, list[str]]:
    """laws.yaml의 admin_rules(훈령·고시)를 이름으로 수집한다."""
    rules = load_yaml(path, "admin_rules")
    return _ingest_each(store, rules, lambda rule: client.load_admin_rule(rule["name"]))


def ingest_interpretations(
    client, store, path: Path = INTERPRETATIONS_FILE
) -> tuple[int, list[str]]:
    """interpretations.yaml 기준으로 법령해석례를 1건 = 문서 1개로 저장한다."""
    total, errors = 0, []
    for source in load_yaml(path, "sources"):
        target = source["target"]
        found = client.find_interpretations(target, source["keywords"])
        docs = []
        for item in found:
            try:
                if doc := client.load_interpretation(target, item):
                    docs.append(doc)
            except Exception as e:
                errors.append(f"{target} {item.get('안건명', '')[:30]}: {e}")
        total += store.upsert(docs)
        print(f"  ✓ {target}: {len(found)}건 중 {len(docs)}건 저장")
    return total, errors


def ingest_ordinances(client, store, path: Path = ORDINANCES_FILE) -> tuple[int, list[str]]:
    """data/ordinances.yaml 기준으로 조례를 찾아 조문 단위로 저장한다. (저장 수, 실패 메시지)."""
    from jeonyeok_helper.rag.law_api import ordinance_json_to_documents

    found = client.find_ordinances(
        load_yaml(path, "keywords"), load_yaml(path, "include"), load_yaml(path, "exclude")
    )
    print(f"  조례 {len(found)}개 발견")
    total, errors = 0, []
    for i, item in enumerate(found, 1):
        name = item.get("자치법규명", "")
        try:
            docs = ordinance_json_to_documents(client.fetch_ordinance(item["자치법규일련번호"]))
            total += store.upsert(docs)
        except Exception as e:
            errors.append(f"{name}: {e}")
            print(f"  ✗ {name}: {e}")
        if i % 50 == 0:
            print(f"  {i}/{len(found)}")
    return total, errors


def ingest_files(store, directory: Path) -> tuple[int, list[str]]:
    from jeonyeok_helper.rag.loaders import load_directory
    from jeonyeok_helper.rag.transcribe import ensure_transcripts

    for name in ensure_transcripts(directory):
        print(f"  ✓ 글자 정보가 없는 PDF를 옮겨 적음: {name}")
    docs, skipped = load_directory(directory)
    for reason in skipped:
        print(f"  - 건너뜀: {reason}")
    return store.upsert(docs), skipped


def main(argv: list[str] | None = None) -> int:
    return run_cli(lambda: _run(argv))


def _run(argv: list[str] | None) -> int:

    parser = argparse.ArgumentParser(prog="jeonyeok-rag", description="규정 수집과 검색")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("laws", help="법령·행정규칙 수집")
    sub.add_parser("ordinances", help="지자체 조례 수집")
    sub.add_parser("interpretations", help="법령해석례 수집")
    sub.add_parser("datasets", help="공공데이터 CSV(보훈 민원, 장학금) 수집")
    sub.add_parser("files", help="data/raw 파일 수집")
    sub.add_parser("web", help="data/webpages.yaml의 기관 안내 페이지 수집")
    sub.add_parser("stats", help="저장된 문서 수")
    p_search = sub.add_parser("search", help="검색 결과 확인")
    p_search.add_argument("question")
    p_search.add_argument("-k", type=int, default=None)
    p_search.add_argument("--region", default=None, help="이 지역 조례도 검색 (예: 부산)")
    p_search.add_argument("--no-hyde", action="store_true")
    p_search.add_argument("--no-rerank", action="store_true")
    args = parser.parse_args(argv)

    from jeonyeok_helper.rag.store import RegulationStore

    s = get_settings()
    store = RegulationStore()

    if args.cmd in ("laws", "ordinances", "interpretations"):
        from jeonyeok_helper.rag.law_api import LawApiClient

        client = LawApiClient(s.law_api_oc)
        if args.cmd == "laws":
            total, errors = ingest_laws(client, store, load_law_list())
            rules, rule_errors = ingest_admin_rules(client, store)
            total, errors = total + rules, errors + rule_errors
            label = "법령·행정규칙 조문"
        elif args.cmd == "ordinances":
            total, errors = ingest_ordinances(client, store)
            label = "조례 조문"
        else:
            total, errors = ingest_interpretations(client, store)
            label = "법령해석례"
        print(f"{label} {total}개 저장, 실패 {len(errors)}건")
        return 1 if errors else 0

    if args.cmd == "datasets":
        from jeonyeok_helper.rag.datasets import load_datasets

        docs, notes = load_datasets()
        for note in notes:
            print(f"  ✓ {note}")
        print(f"공공데이터 {store.upsert(docs)}건 저장")
        return 0

    if args.cmd == "files":
        total, _ = ingest_files(store, s.raw_docs_dir)
        print(f"파일 청크 {total}개 저장")
        return 0

    if args.cmd == "web":
        from jeonyeok_helper.rag.webpages import load_webpage_list, load_webpages

        docs, errors = load_webpages(load_webpage_list())
        for e in errors:
            print(f"  ✗ {e}")
        print(f"안내 페이지 조각 {store.upsert(docs)}개 저장, 실패 {len(errors)}건")
        return 1 if errors else 0

    if args.cmd == "stats":
        print(f"저장된 문서: {store.count()}개")
        return 0

    from jeonyeok_helper.llm import get_fast_chat_model
    from jeonyeok_helper.rag.retriever import RegulationRetriever

    retriever = RegulationRetriever(
        store,
        llm=get_fast_chat_model(),
        use_hyde=not args.no_hyde,
        use_rerank=not args.no_rerank,
    )
    for i, doc in enumerate(
        retriever.retrieve(args.question, k=args.k or s.retrieval_k, region=args.region), 1
    ):
        score = doc.metadata.get("rerank_score")
        print(f"\n[{i}] {doc.metadata.get('citation')}" + (f"  (점수 {score})" if score else ""))
        print(doc.page_content[:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
