"""자료 자동 갱신: 바뀐 법령·조례만 다시 수집하고, 평가 결과를 남긴다."""

from datetime import UTC, datetime, timedelta

from langchain_core.documents import Document
from test_api import temp_db

from jeonyeok_helper.db import Database, RefreshRun
from jeonyeok_helper.rag import refresh


def law_json(law_id: str, name: str, enforced: str, articles: list[str]) -> dict:
    return {
        "법령": {
            "기본정보": {"법령명_한글": name, "법령ID": law_id, "시행일자": enforced},
            "조문": {
                "조문단위": [
                    {
                        "조문여부": "조문",
                        "조문번호": n,
                        "조문제목": "",
                        "조문내용": f"제{n}조 {enforced}",
                    }
                    for n in articles
                ]
            },
        }
    }


class FakeClient:
    """국가법령정보센터 흉내: laws는 {이름: (법령ID, 일련번호, 시행일, 조문 번호들)}"""

    def __init__(self):
        self.laws = {"제대군인지원법": ("001", "100", "20260101", ["1", "2", "3"])}
        self.ordinances = {
            "o1": ("500", "20260101", "부산 제대군인 조례"),
            "o2": ("600", "20260101", "서울 제대군인 조례"),
        }
        self.fetched: list[str] = []

    def find_current(self, name):
        law_id, serial, enforced, _ = self.laws[name]
        return {"법령ID": law_id, "법령일련번호": serial, "시행일자": enforced}

    def fetch(self, serial):
        self.fetched.append(f"law:{serial}")
        for name, (law_id, s, enforced, arts) in self.laws.items():
            if s == serial:
                return law_json(law_id, name, enforced, arts)
        raise LookupError(serial)

    def find_ordinances(self, keywords, include, exclude):
        return [
            {"자치법규ID": oid, "자치법규일련번호": serial, "시행일자": enf, "자치법규명": name}
            for oid, (serial, enf, name) in self.ordinances.items()
        ]

    def fetch_ordinance(self, serial):
        self.fetched.append(f"ordin:{serial}")
        oid, (_, enforced, name) = next(
            (k, v) for k, v in self.ordinances.items() if v[0] == serial
        )
        return {
            "LawService": {
                "자치법규기본정보": {"자치법규명": name, "자치법규ID": oid, "시행일자": enforced},
                "조문": {"조": [{"조문여부": "Y", "조문번호": "000100", "조내용": "제1조 목적"}]},
            }
        }

    def find_interpretations(self, target, keywords):
        return [{"법령해석례일련번호": "9"}, {"법령해석례일련번호": "10"}]

    def load_interpretation(self, target, item):
        key = item["법령해석례일련번호"]
        self.fetched.append(f"interp:{key}")
        return Document("회답", metadata={"doc_id": f"interp:{target}:{key}", "enforced_at": ""})


class FakeStore:
    def __init__(self):
        self.docs: dict[str, dict] = {}

    def add(self, doc_id: str, enforced: str):
        self.docs[doc_id] = {"enforced_at": enforced}

    def ids(self, prefix):
        return {i for i in self.docs if i.startswith(prefix)}

    def enforced_dates(self, prefix):
        return {m["enforced_at"] for i, m in self.docs.items() if i.startswith(prefix)}

    def upsert(self, docs):
        for d in docs:
            self.docs[d.metadata["doc_id"]] = dict(d.metadata)
        return len(docs)

    def replace_prefix(self, prefix, docs):
        stale = self.ids(prefix) - {d.metadata["doc_id"] for d in docs}
        for i in stale:
            del self.docs[i]
        return self.upsert(docs), len(stale)


SOURCES = {
    "laws": [{"name": "제대군인지원법"}],
    "admin_rules": [],
    "ordinances": {"keywords": ["제대군인"], "include": ["제대군인"], "exclude": []},
    "interpretations": [{"target": "expc", "keywords": ["전역"]}],
}


def setup():
    db = Database(temp_db())
    db.migrate()
    client, store = FakeClient(), FakeStore()
    # 이미 넣어 둔 자료: 법령 조문 3개, 조례 2개, 해석례 1건 (모두 지금과 같은 시행일)
    for n in ("1", "2", "3"):
        store.add(f"law:001:제{n}조", "20260101")
    store.add("ordin:o1:제1조", "20260101")
    store.add("ordin:o2:제1조", "20260101")
    store.add("interp:expc:9", "")
    return db, client, store


def run(db, client, store, **kw):
    scores = kw.pop("scores", [{"hit": 1.0, "recall": 1.0, "mrr": 0.9}])
    calls = []

    def evaluate(_store):
        calls.append(1)
        return scores[min(len(calls) - 1, len(scores) - 1)]

    result = refresh.refresh_once(
        client, store, db, SOURCES, evaluate=evaluate, say=lambda _: None, **kw
    )
    return result, calls


def test_first_run_records_versions_without_reembedding(monkeypatch):
    monkeypatch.setattr("jeonyeok_helper.rag.ingest.save_keyword_index", lambda store: None)
    db, client, store = setup()
    result, _ = run(db, client, store)
    # 처음: 넣어 둔 시행일이 같으면 번호만 기록하고 받지 않는다. 새 해석례(10)만 더한다
    assert client.fetched == ["interp:10"]
    assert result.changed == ["법령해석례 expc 새 1건"]

    client.fetched.clear()
    result, _ = run(db, client, store)
    assert client.fetched == [] and result.changed == [] and result.retrieval is None


def test_amended_law_replaces_its_articles(monkeypatch):
    monkeypatch.setattr("jeonyeok_helper.rag.ingest.save_keyword_index", lambda store: None)
    db, client, store = setup()
    run(db, client, store)
    # 개정: 일련번호가 바뀌고 제3조가 없어지고 제4조가 생김
    client.laws["제대군인지원법"] = ("001", "101", "20261101", ["1", "2", "4"])
    client.fetched.clear()
    result, calls = run(db, client, store)
    assert client.fetched == ["law:101"]
    assert sorted(store.ids("law:001:")) == ["law:001:제1조", "law:001:제2조", "law:001:제4조"]
    assert result.docs_written == 3 and result.docs_deleted == 1
    assert result.changed == ["법령 제대군인지원법 (시행 20261101)"]
    assert calls and result.retrieval["recall"] == 1.0  # 바뀌었으니 평가


def test_repealed_ordinance_is_removed_and_changed_one_refetched(monkeypatch):
    monkeypatch.setattr("jeonyeok_helper.rag.ingest.save_keyword_index", lambda store: None)
    db, client, store = setup()
    client.ordinances["o3"] = ("700", "20260101", "대구 제대군인 조례")  # 새 조례 하나 더 있음
    run(db, client, store)
    assert "ordin:o3:제1조" in store.docs

    client.ordinances["o1"] = ("501", "20261201", "부산 제대군인 조례")  # 개정
    del client.ordinances["o2"]  # 폐지
    client.fetched.clear()
    result, _ = run(db, client, store)
    assert client.fetched == ["ordin:501"]
    assert "ordin:o2:제1조" not in store.docs
    assert "조례 폐지 서울 제대군인 조례" in result.changed


def test_dry_run_changes_nothing():
    db, client, store = setup()
    client.laws["제대군인지원법"] = ("001", "101", "20261101", ["1"])
    before = dict(store.docs)
    report = refresh.refresh_once(client, store, db, SOURCES, dry_run=True, say=lambda _: None)
    assert report.changed[0].startswith("법령 제대군인지원법")
    assert store.docs == before and client.fetched == []
    assert refresh.last_run(db) is None


def test_score_drop_is_flagged(monkeypatch):
    monkeypatch.setattr("jeonyeok_helper.rag.ingest.save_keyword_index", lambda store: None)
    db, client, store = setup()
    run(db, client, store, force_eval=True)
    client.laws["제대군인지원법"] = ("001", "101", "20261101", ["1"])
    result, _ = run(db, client, store, scores=[{"hit": 0.95, "recall": 0.95, "mrr": 0.8}])
    assert result.score_dropped


def test_score_dropped_rule():
    before = {"hit": 1.0, "recall": 1.0, "mrr": 0.9}
    assert not refresh.score_dropped({"hit": 1.0, "recall": 0.99, "mrr": 0.87}, before)  # 흔들림
    assert refresh.score_dropped({"hit": 1.0, "recall": 0.97, "mrr": 0.9}, before)
    assert not refresh.score_dropped({"hit": 0.5, "recall": 0.5, "mrr": 0.5}, None)


def test_due_every_seven_days():
    db = Database(temp_db())
    db.migrate()
    assert refresh.due(db)
    now = datetime.now(UTC)
    with db.session() as session:
        session.add(RefreshRun(started_at=now - timedelta(days=3), changed=[], errors=[]))
    assert not refresh.due(db, now)
    assert refresh.due(db, now + timedelta(days=4, minutes=1))


def test_mass_disappearance_is_not_treated_as_repeal(monkeypatch):
    """검색이 잘못돼 조례 목록이 크게 줄면 지우지 않고 오류로 남긴다."""
    monkeypatch.setattr("jeonyeok_helper.rag.ingest.save_keyword_index", lambda store: None)
    db, client, store = setup()
    for i in range(10):
        client.ordinances[f"x{i}"] = (f"9{i}", "20260101", f"조례 {i}")
        store.add(f"ordin:x{i}:제1조", "20260101")
    run(db, client, store)
    client.ordinances = {"o1": client.ordinances["o1"]}  # 12개 중 11개가 사라짐
    result, _ = run(db, client, store)
    assert len(store.ids("ordin:")) == 12
    assert any("검색 오류로 보고" in e for e in result.errors)
