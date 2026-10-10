from fastapi.testclient import TestClient

from jeonyeok_helper.api.main import app


def test_health():
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    # 키 값 자체는 절대 응답에 담기지 않고 설정 여부(bool)만 나온다.
    assert all(isinstance(v, bool) for v in body["keys"].values())
