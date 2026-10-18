"""브라우저 알림(Web Push): 기한 계산, 보낼 알림 고르기, 구독 API."""

import asyncio
from datetime import date, datetime

import pytest
from test_api import make_client, temp_db

from jeonyeok_helper import push
from jeonyeok_helper.agents.state import Route
from jeonyeok_helper.config import get_settings
from jeonyeok_helper.db import Database, JourneyItem

FCM = "https://fcm.googleapis.com/fcm/send/abc"


def test_due_date_matches_the_screen():
    # 화면(dueDate)과 같다: 전역 달 + 개월 수의 마지막 날, 월을 모르면 12월 기준
    assert push.due_date("2026-09", 6) == date(2027, 3, 31)
    assert push.due_date("2026-03", 36) == date(2029, 3, 31)
    assert push.due_date("2026-01", 1) == date(2026, 2, 28)
    assert push.due_date("2025", 6) == date(2026, 6, 30)
    assert push.due_date("2026-09", -2) == date(2026, 7, 31)
    assert push.due_date(None, 6) is None
    assert push.due_date("2026-09", None) is None


def item(**over) -> JourneyItem:
    values = dict(
        id="i1",
        user_id="u1",
        stage="job",
        title="전직지원금 신청",
        deadline="전역 후 6개월 이내",
        due_months=6,
        done=False,
    )
    values.update(over)
    return JourneyItem(**values)


@pytest.mark.parametrize(
    ("today", "sent", "expected"),
    [
        (date(2027, 1, 1), set(), None),  # 89일 남음: 아직
        (date(2027, 3, 1), set(), 30),  # 30일 남음
        (date(2027, 3, 1), {30}, None),  # 이미 보냄
        (date(2027, 3, 26), {30}, 7),  # 5일 남음: 7일 전 알림을 놓쳤으면 지금
        (date(2027, 3, 26), set(), 7),  # 30일 전도 놓쳤으면 가까운 것 하나만
        (date(2027, 3, 31), {30, 7}, 1),  # 오늘 마감
        (date(2027, 4, 1), set(), None),  # 지남
    ],
)
def test_reminder_picks_the_nearest_unsent(today, sent, expected):
    r = push.reminder_for(item(), "2026-09", today, sent)
    assert (r.days_before if r else None) == expected


def test_no_reminder_without_date_or_when_done():
    assert push.reminder_for(item(), None, date(2027, 3, 30), set()) is None
    assert push.reminder_for(item(done=True), "2026-09", date(2027, 3, 30), set()) is None
    assert push.reminder_for(item(deadline=""), "2026-09", date(2027, 3, 30), set()) is None


def test_only_known_push_services_are_allowed():
    assert push.allowed_endpoint(FCM)
    assert push.allowed_endpoint("https://updates.push.services.mozilla.com/wpush/v2/x")
    assert push.allowed_endpoint("https://web.push.apple.com/abc")
    assert not push.allowed_endpoint("http://fcm.googleapis.com/x")  # https만
    assert not push.allowed_endpoint("https://evil.example.com/fcm.googleapis.com")
    assert not push.allowed_endpoint("https://push.apple.com.evil.com/x")
    assert not push.allowed_endpoint("https://169.254.169.254/latest")


class FakeSender:
    def __init__(self, status=201):
        self.status = status
        self.sent: list[tuple[str, dict]] = []

    def __call__(self, sub, payload):
        self.sent.append((sub.endpoint, payload))
        return self.status


def setup_db() -> Database:
    db = Database(temp_db())
    db.migrate()
    with db.session() as session:
        session.add(item())
        session.add(item(id="i2", title="국민취업지원제도", due_months=36))
        session.add(item(id="i3", user_id="other"))  # 구독 안 한 사람
    push.subscribe(db, "u1", FCM, "p", "a")
    return db


async def profile_of(user_id: str) -> dict:
    return {"discharge_date": "2026-09"}


def at(y, m, d, hour=10) -> datetime:
    """한국 시각"""
    return datetime(y, m, d, hour, tzinfo=push.KST)


def test_run_once_sends_each_reminder_once():
    db, send = setup_db(), FakeSender()
    assert asyncio.run(push.run_once(db, profile_of, at(2027, 3, 1), send)) == 1
    endpoint, payload = send.sent[0]
    assert endpoint == FCM
    assert payload["title"] == "[마감 30일 전] 전직지원금 신청"
    assert payload["url"] == "/?page=journey"
    # 한 시간 뒤 다시 확인해도 또 보내지 않는다
    assert asyncio.run(push.run_once(db, profile_of, at(2027, 3, 1, 11), send)) == 0
    # 7일 전이 되면 다시 한 번
    assert asyncio.run(push.run_once(db, profile_of, at(2027, 3, 24), send)) == 1
    assert send.sent[-1][1]["title"] == "[마감 7일 전] 전직지원금 신청"


def test_run_once_is_quiet_at_night():
    db, send = setup_db(), FakeSender()
    assert asyncio.run(push.run_once(db, profile_of, at(2027, 3, 1, 22), send)) == 0
    assert send.sent == []


def test_gone_subscription_is_removed():
    db, send = setup_db(), FakeSender(status=410)
    asyncio.run(push.run_once(db, profile_of, at(2027, 3, 1), send))
    assert push.subscriptions(db, "u1") == []


@pytest.fixture
def vapid(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "vapid_public_key", "PUBLIC")
    monkeypatch.setattr(s, "vapid_private_key", "PRIVATE")


def test_subscribe_api(vapid):
    send = FakeSender()
    sub = {"endpoint": FCM, "keys": {"p256dh": "p", "auth": "a"}}
    with make_client([Route(next="answer")], app_kwargs={"push_sender": send}) as client:
        assert client.get("/push/key").json() == {"key": "PUBLIC"}
        assert client.put("/push/u1", json=sub).status_code == 204
        bad = client.put("/push/u1", json={**sub, "endpoint": "https://evil.example.com/x"})
        test = client.post("/push/u1/test").json()
        assert client.post("/push/u1/unsubscribe", json={"endpoint": FCM}).status_code == 204
        after = client.post("/push/u1/test").json()
    assert bad.status_code == 422
    assert test == {"delivered": 1} and send.sent[0][1]["tag"] == "test"
    assert after == {"delivered": 0}


def test_push_is_off_without_keys(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "vapid_public_key", "")
    monkeypatch.setattr(s, "vapid_private_key", "")
    sub = {"endpoint": FCM, "keys": {"p256dh": "p", "auth": "a"}}
    with make_client([Route(next="answer")]) as client:
        assert client.get("/push/key").json() == {"key": None}
        assert client.put("/push/u1", json=sub).status_code == 503


def test_webpush_sender_encrypts_for_the_browser(monkeypatch):
    """가짜 브라우저 구독으로 실제 암호화·VAPID 서명을 해 보내고, 받은 쪽에서 풀어 본다."""
    import base64
    import json
    import os
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    import http_ece
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    from jeonyeok_helper.db import PushSubscription

    def b64(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    server_key = ec.generate_private_key(ec.SECP256R1())
    s = get_settings()
    monkeypatch.setattr(
        s, "vapid_private_key", b64(server_key.private_numbers().private_value.to_bytes(32, "big"))
    )
    monkeypatch.setattr(s, "vapid_subject", "")  # 비어 있어도 기본값으로 서명된다

    browser = ec.generate_private_key(ec.SECP256R1())
    browser_pub = browser.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    secret = os.urandom(16)
    got: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            got["headers"] = {k.lower(): v for k, v in self.headers.items()}
            got["body"] = self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(201)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        sub = PushSubscription(
            id=1,
            user_id="u1",
            endpoint=f"http://127.0.0.1:{server.server_port}/push",
            p256dh=b64(browser_pub),
            auth=b64(secret),
        )
        status = push.webpush_sender(sub, {"title": "[마감 7일 전] 전직지원금 신청"})
    finally:
        server.shutdown()

    plain = http_ece.decrypt(
        got["body"], private_key=browser, auth_secret=secret, version="aes128gcm"
    )
    assert status == 201
    assert got["headers"]["content-encoding"] == "aes128gcm"
    assert got["headers"]["authorization"].startswith("vapid ")
    assert json.loads(plain)["title"] == "[마감 7일 전] 전직지원금 신청"
