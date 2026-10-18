"""자료 자동 갱신: 법령 개정·조례 변경을 확인해 바뀐 것만 다시 수집한다.

    uv run jeonyeok-rag refresh            # 한 번 확인하고, 바뀌었으면 수집·색인·평가
    uv run jeonyeok-rag refresh --dry-run  # 무엇이 바뀌었는지만 (저장하지 않음)
    uv run jeonyeok-rag refresh --loop     # 서버처럼 켜 두면 7일마다 (docker compose의 refresh)

국가법령정보센터는 법령·행정규칙·조례가 개정될 때마다 일련번호(MST)가 새로 붙는다. 마지막으로
수집한 일련번호를 source_version 표에 두고, 목록 검색(가벼운 요청)으로 지금 번호와 비교해 다를
때만 본문을 받아 임베딩한다. 처음 돌 때는 저장된 번호가 없으므로, 이미 넣어 둔 조문의 시행일과
지금 시행일이 같으면 번호만 기록하고(다시 임베딩하지 않음) 다르면 수집한다.

- 법령·행정규칙: 바뀌면 그 법령의 조문을 통째로 바꾼다 (개정으로 없어진 조문은 지움)
- 조례: 바뀐 조례만 다시 받고, 목록에서 사라진(폐지된) 조례는 지운다
- 법령해석례: 새 해석례만 더한다 (해석례는 고쳐지지 않는다)

바뀐 것이 있으면 BM25 색인을 다시 저장하고 검색 골든셋을 돌려 refresh_run 표에 남긴다.
점수가 지난번보다 떨어지면 score_dropped로 표시하고 경고를 남긴다.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from jeonyeok_helper.config import load_yaml
from jeonyeok_helper.db import Database, RefreshRun, SourceVersion

log = logging.getLogger(__name__)

EVERY = timedelta(days=7)
# 한 번에 이보다 많이(5개 넘게, 그리고 20% 넘게) 사라지면 폐지가 아니라 검색 오류로 보고
# 지우지 않는다
MAX_GONE = (5, 0.2)
# 이만큼 떨어지면 점수가 떨어진 것으로 본다 (재정렬 LLM 때문에 MRR은 ±0.03쯤 흔들린다)
DROP = {"hit": 0.03, "recall": 0.02}


@dataclass
class Report:
    changed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    written: int = 0
    deleted: int = 0
    baselined: int = 0  # 처음 돌 때 번호만 기록한 수

    @property
    def touched(self) -> bool:
        return bool(self.written or self.deleted)


class Refresher:
    def __init__(
        self,
        client,
        store,
        db: Database,
        sources: dict,
        dry_run: bool = False,
        say: Callable[[str], None] = print,
    ):
        """sources: default_sources()와 같은 모양 (laws, admin_rules, ordinances 등)"""
        self.client, self.store, self.db = client, store, db
        self.sources = sources
        self.dry_run = dry_run
        self.say = say
        self.report = Report()
        self._versions_cache: dict[str, dict[str, SourceVersion]] = {}

    # ---------- 저장한 번호 ----------

    def _versions(self, kind: str) -> dict[str, SourceVersion]:
        with self.db.session() as session:
            rows = session.scalars(select(SourceVersion).where(SourceVersion.kind == kind))
            return {r.key: r for r in rows}

    def _save_version(self, kind: str, key: str, version: str, name: str, enforced: str) -> None:
        if self.dry_run:
            return
        with self.db.session() as session:
            row = session.get(SourceVersion, (kind, key))
            if row is None:
                session.add(SourceVersion(kind=kind, key=key, version=version, name=name,
                                          enforced_at=enforced))  # fmt: skip
            else:
                row.version, row.name, row.enforced_at = version, name, enforced
                row.updated_at = datetime.now(UTC)

    def _forget_version(self, kind: str, key: str) -> None:
        if self.dry_run:
            return
        with self.db.session() as session:
            if row := session.get(SourceVersion, (kind, key)):
                session.delete(row)

    # ---------- 바뀌었는지 ----------

    def _changed(self, saved: SourceVersion | None, prefix: str, version: str, enforced: str):
        """다시 수집해야 하는지. 처음(저장한 번호 없음)이면 넣어 둔 조문의 시행일과 비교한다."""
        if saved is not None:
            return saved.version != version
        stored = self.store.enforced_dates(prefix)
        return not stored or stored != {enforced}

    def _replace(self, label: str, prefix: str, load) -> bool:
        """본문을 받아 prefix의 조문을 바꾼다. 성공하면 True"""
        self.report.changed.append(label)
        if self.dry_run:
            self.say(f"  ~ {label} (바뀜, 미리 보기라 저장 안 함)")
            return True
        try:
            docs = load()
            written, deleted = self.store.replace_prefix(prefix, docs)
        except Exception as e:
            self.report.errors.append(f"{label}: {e}")
            self.say(f"  ✗ {label}: {e}")
            return False
        self.report.written += written
        self.report.deleted += deleted
        self.say(f"  ✓ {label}: {written}개 저장, {deleted}개 지움")
        return True

    def _versioned(self, kind, key, version, enforced, name, label, prefix, load) -> None:
        saved = self._versions_cache[kind].get(key)
        if not self._changed(saved, prefix, version, enforced):
            if saved is None:  # 처음: 지금 자료가 최신이라 번호만 기록
                self._save_version(kind, key, version, name, enforced)
                self.report.baselined += 1
            return
        if self._replace(label, prefix, load):
            self._save_version(kind, key, version, name, enforced)

    # ---------- 종류별 ----------

    def laws(self) -> None:
        from jeonyeok_helper.rag.law_api import law_json_to_documents

        for law in self.sources.get("laws", []):
            name = law["name"]
            try:
                found = self.client.find_current(name)
            except Exception as e:
                self.report.errors.append(f"법령 {name}: {e}")
                continue
            if found is None:
                self.report.errors.append(f"법령 {name}: 현행 법령을 찾지 못함")
                continue
            serial, articles = found["법령일련번호"], law.get("articles")

            def load(serial=serial, articles=articles):
                docs = law_json_to_documents(self.client.fetch(serial))
                return [d for d in docs if d.metadata["article"] in articles] if articles else docs

            self._versioned("law", found["법령ID"], serial, found.get("시행일자", ""), name,
                            f"법령 {name} (시행 {found.get('시행일자', '')})",
                            f"law:{found['법령ID']}:", load)  # fmt: skip

    def admin_rules(self) -> None:
        for rule in self.sources.get("admin_rules", []):
            name = rule["name"]
            try:
                found = self.client.find_admin_rule(name)
            except Exception as e:
                self.report.errors.append(f"행정규칙 {name}: {e}")
                continue
            if found is None:
                self.report.errors.append(f"행정규칙 {name}: 찾지 못함")
                continue
            serial = found["행정규칙일련번호"]
            self._versioned("admrul", found["행정규칙ID"], serial, found.get("시행일자", ""), name,
                            f"행정규칙 {name} (시행 {found.get('시행일자', '')})",
                            f"admrul:{found['행정규칙ID']}:",
                            lambda serial=serial: self.client.fetch_admin_rule(serial))  # fmt: skip

    def ordinances(self) -> None:
        from jeonyeok_helper.rag.law_api import ordinance_json_to_documents

        cfg = self.sources.get("ordinances")
        if not cfg:
            return
        try:
            found = self.client.find_ordinances(cfg["keywords"], cfg["include"], cfg["exclude"])
        except Exception as e:
            self.report.errors.append(f"조례 목록: {e}")
            return
        current = {item["자치법규ID"]: item for item in found if item.get("자치법규ID")}
        for oid, item in current.items():
            serial, name = item["자치법규일련번호"], item.get("자치법규명", "")
            self._versioned("ordin", oid, serial, item.get("시행일자", ""), name,
                            f"조례 {name}", f"ordin:{oid}:",
                            lambda serial=serial: ordinance_json_to_documents(
                                self.client.fetch_ordinance(serial)))  # fmt: skip

        # 목록에서 사라진 조례 = 폐지(또는 이름이 바뀌어 조건에서 빠짐)
        stored = {doc_id.split(":")[1] for doc_id in self.store.ids("ordin:")}
        gone = stored - current.keys()
        if len(gone) > MAX_GONE[0] and len(gone) > len(stored) * MAX_GONE[1]:
            self.report.errors.append(
                f"조례 {len(gone)}개가 한꺼번에 목록에서 사라져(지난번 {len(stored)}개)"
                " 검색 오류로 보고 폐지 처리를 건너뜀"
            )
            return
        names = {k: v.name for k, v in self._versions_cache["ordin"].items()}
        for oid in sorted(gone):
            label = f"조례 폐지 {names.get(oid) or oid}"
            self.report.changed.append(label)
            if self.dry_run:
                self.say(f"  ~ {label} (미리 보기라 지우지 않음)")
                continue
            _, deleted = self.store.replace_prefix(f"ordin:{oid}:", [])
            self.report.deleted += deleted
            self._forget_version("ordin", oid)
            self.say(f"  ✓ {label}: {deleted}개 지움")

    def interpretations(self) -> None:
        for source in self.sources.get("interpretations", []):
            target = source["target"]
            try:
                found = self.client.find_interpretations(target, source["keywords"])
            except Exception as e:
                self.report.errors.append(f"법령해석례 {target}: {e}")
                continue
            known = {doc_id.split(":", 2)[2] for doc_id in self.store.ids(f"interp:{target}:")}
            new = [
                i for i in found
                if str(i.get("법령해석례일련번호") or i.get("법령해석일련번호")) not in known
            ]  # fmt: skip
            if not new:
                continue
            label = f"법령해석례 {target} 새 {len(new)}건"
            self.report.changed.append(label)
            if self.dry_run:
                self.say(f"  ~ {label} (미리 보기라 저장 안 함)")
                continue
            docs = []
            for item in new:
                try:
                    if doc := self.client.load_interpretation(target, item):
                        docs.append(doc)
                except Exception as e:
                    self.report.errors.append(f"{target} {item.get('안건명', '')[:30]}: {e}")
            self.report.written += self.store.upsert(docs)
            self.say(f"  ✓ {label}: {len(docs)}건 저장")

    def run(self) -> Report:
        self._versions_cache = {k: self._versions(k) for k in ("law", "admrul", "ordin")}
        for step, label in [
            (self.laws, "법령"),
            (self.admin_rules, "행정규칙"),
            (self.ordinances, "조례"),
            (self.interpretations, "법령해석례"),
        ]:
            self.say(f"{label} 확인 중…")
            step()
        return self.report


# ---------- 갱신 뒤 평가와 기록 ----------


def score_dropped(now: dict, before: dict | None) -> bool:
    if not before:
        return False
    return any(before.get(m, 0) - now.get(m, 0) >= gap for m, gap in DROP.items())


def last_run(db: Database, with_score: bool = False) -> RefreshRun | None:
    with db.session() as session:
        q = select(RefreshRun).order_by(RefreshRun.started_at.desc())
        if with_score:
            q = q.where(RefreshRun.retrieval.is_not(None))
        return session.scalars(q.limit(1)).first()


def evaluate_retrieval(store) -> dict:
    """검색 골든셋(서비스 설정)을 돌려 전체 점수와 보고서 경로를 돌려준다."""
    from jeonyeok_helper.llm import get_fast_chat_model
    from jeonyeok_helper.rag.retriever import RegulationRetriever
    from jeonyeok_helper.retrieval_eval import (
        load_golden,
        run_retrieval_eval,
        save_retrieval,
        summarize_retrieval,
    )

    retriever = RegulationRetriever(store, llm=get_fast_chat_model())
    results = run_retrieval_eval(retriever, load_golden(), k=6)
    summary = summarize_retrieval(results)
    report = save_retrieval({"full": (results, summary)}, 6)
    return summary["overall"] | {"report": report.name}


def refresh_once(
    client,
    store,
    db: Database,
    sources: dict,
    dry_run: bool = False,
    force_eval: bool = False,
    evaluate: Callable[[object], dict] = evaluate_retrieval,
    say: Callable[[str], None] = print,
) -> RefreshRun | Report:
    started = datetime.now(UTC)
    report = Refresher(client, store, db, sources, dry_run, say).run()
    if dry_run:
        return report

    retrieval, dropped = None, False
    if report.touched:
        from jeonyeok_helper.rag.ingest import save_keyword_index

        save_keyword_index(store)
    if report.touched or force_eval:
        before = last_run(db, with_score=True)
        try:
            retrieval = evaluate(store)
            dropped = score_dropped(retrieval, before.retrieval if before else None)
        except Exception as e:
            report.errors.append(f"검색 골든셋 평가: {e}")
        if dropped:
            log.warning(
                "자료 갱신 뒤 검색 점수가 떨어졌습니다: %s → %s", before.retrieval, retrieval
            )

    run = RefreshRun(
        started_at=started,
        finished_at=datetime.now(UTC),
        changed=report.changed,
        errors=report.errors,
        docs_written=report.written,
        docs_deleted=report.deleted,
        retrieval=retrieval,
        score_dropped=dropped,
    )
    with db.session() as session:
        session.add(run)
    return run


def due(db: Database, now: datetime | None = None) -> bool:
    """마지막 갱신에서 7일이 지났는지 (한 번도 안 돌았으면 지금)"""
    last = last_run(db)
    if last is None:
        return True
    started = last.started_at if last.started_at.tzinfo else last.started_at.replace(tzinfo=UTC)
    return (now or datetime.now(UTC)) - started >= EVERY


def loop(run: Callable[[], object], db: Database, check_every: int = 3600) -> None:
    """한 시간마다 확인해 7일이 지났으면 갱신한다. 재시작해도 마지막 기록을 보고 이어 간다."""
    while True:
        try:
            if due(db):
                run()
        except Exception:
            log.exception("자료 자동 갱신 실패")
        time.sleep(check_every)


def default_sources() -> dict:
    from jeonyeok_helper.rag.ingest import INTERPRETATIONS_FILE, LAWS_FILE, ORDINANCES_FILE

    return {
        "laws": load_yaml(LAWS_FILE, "laws"),
        "admin_rules": load_yaml(LAWS_FILE, "admin_rules"),
        "ordinances": {
            "keywords": load_yaml(ORDINANCES_FILE, "keywords"),
            "include": load_yaml(ORDINANCES_FILE, "include"),
            "exclude": load_yaml(ORDINANCES_FILE, "exclude"),
        },
        "interpretations": load_yaml(INTERPRETATIONS_FILE, "sources"),
    }
