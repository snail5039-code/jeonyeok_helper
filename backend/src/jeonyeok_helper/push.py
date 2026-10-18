"""브라우저 알림(Web Push): 계정 없이 신청 기한을 알려 준다.

사용자가 허락한 브라우저의 푸시 구독(주소와 암호화 키)만 익명 ID와 함께 저장한다.
서버는 한 시간마다 기한을 확인해, 마감 30·7·1일 전에 한 번씩 알림을 보낸다.
서버가 꺼져 있어 그날을 놓쳤으면 다음에 확인할 때 가장 가까운 알림 하나만 보내고(밀린 알림을
몰아서 보내지 않는다), 밤(21시~9시)에는 보내지 않는다.
마감일 계산은 화면(frontend/src/lib/journey.ts dueDate)과 같다: 전역 달 + 개월 수의 마지막 날.
"""

from __future__ import annotations

import asyncio
import calendar
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import delete, select

from jeonyeok_helper.config import get_settings
from jeonyeok_helper.db import Database, JourneyItem, PushSent, PushSubscription

log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))  # 한국은 서머타임이 없다
REMIND_DAYS = (30, 7, 1)
SEND_HOURS = range(9, 21)  # 9시~20시대에만 보낸다
CHECK_EVERY = 60 * 60  # 초

# 브라우저가 주는 푸시 주소는 이 서비스들 것뿐이다. 다른 주소로는 서버가 요청을 보내지 않는다.
PUSH_HOSTS = (
    "fcm.googleapis.com",  # 크롬·엣지·삼성 인터넷(안드로이드)
    "updates.push.services.mozilla.com",  # 파이어폭스
    ".push.apple.com",  # 사파리·아이폰 홈 화면 앱
    ".notify.windows.com",  # 예전 엣지
)


def allowed_endpoint(endpoint: str) -> bool:
    url = urlparse(endpoint)
    host = url.hostname or ""
    return url.scheme == "https" and any(
        host == h.lstrip(".") or (h.startswith(".") and host.endswith(h)) for h in PUSH_HOSTS
    )


def today_kst(now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)).astimezone(KST)


# ---------- 기한 ----------


def due_date(discharge_date: str | None, due_months: int | None) -> date | None:
    """전역일(YYYY-MM 또는 YYYY)에 개월 수를 더한 달의 마지막 날. 월을 모르면 그해 12월 기준."""
    if due_months is None or not discharge_date:
        return None
    parts = discharge_date[:7].split("-")
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 and parts[1] else 12
    except ValueError:
        return None
    index = year * 12 + (month - 1) + due_months
    y, m = divmod(index, 12)
    return date(y, m + 1, calendar.monthrange(y, m + 1)[1])


@dataclass
class Reminder:
    item_id: str
    user_id: str
    title: str
    deadline: str
    days_left: int
    days_before: int  # 이번에 보내는 알림 (30, 7, 1)


def reminder_for(
    item: JourneyItem, discharge_date: str | None, today: date, sent: set[int]
) -> Reminder | None:
    """이 할 일에 지금 보낼 알림. 남은 날이 알림 기준(30·7·1일) 안으로 들어왔고 아직 안 보냈으면."""
    if item.done or not item.deadline:
        return None
    due = due_date(discharge_date, item.due_months)
    if due is None:
        return None
    left = (due - today).days
    if left < 0:
        return None
    reached = [d for d in REMIND_DAYS if left <= d]
    if not reached:
        return None
    nearest = min(reached)
    if nearest in sent:
        return None
    return Reminder(item.id, item.user_id, item.title, item.deadline, left, nearest)


def message(r: Reminder) -> dict:
    when = "오늘 마감" if r.days_left == 0 else f"마감 {r.days_left}일 전"
    return {
        "title": f"[{when}] {r.title}",
        "body": f"{r.deadline}. 놓치기 전에 신청하세요. 정확한 기한은 소관 기관에 확인하세요.",
        "url": "/?page=journey",
        "tag": f"due-{r.item_id}",
    }


# ---------- 구독 ----------


def subscribe(db: Database, user_id: str, endpoint: str, p256dh: str, auth: str) -> None:
    """같은 브라우저가 다시 구독하면(익명 ID가 바뀌었어도) 그 구독을 이 ID로 옮긴다."""
    with db.session() as session:
        row = session.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
        if row is None:
            session.add(
                PushSubscription(user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth)
            )
        else:
            row.user_id, row.p256dh, row.auth = user_id, p256dh, auth


def unsubscribe(db: Database, user_id: str, endpoint: str) -> bool:
    with db.session() as session:
        res = session.execute(
            delete(PushSubscription).where(
                PushSubscription.user_id == user_id, PushSubscription.endpoint == endpoint
            )
        )
        return res.rowcount > 0


def subscriptions(db: Database, user_id: str | None = None) -> list[PushSubscription]:
    with db.session() as session:
        q = select(PushSubscription)
        if user_id is not None:
            q = q.where(PushSubscription.user_id == user_id)
        return list(session.scalars(q))


# ---------- 보내기 ----------

# 보내기 함수: (구독, 내용) → HTTP 상태 코드. 테스트에서는 가짜로 바꾼다.
Sender = Callable[[PushSubscription, dict], int]
ProfileGetter = Callable[[str], Awaitable[dict]]


def configured() -> bool:
    s = get_settings()
    return bool(s.vapid_public_key and s.vapid_private_key)


def webpush_sender(sub: PushSubscription, payload: dict) -> int:
    from pywebpush import WebPushException, webpush

    s = get_settings()
    try:
        res = webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=s.vapid_private_key,
            vapid_claims={"sub": s.vapid_subject or "https://localhost"},
            ttl=24 * 60 * 60,
            timeout=10,
        )
        return res.status_code
    except WebPushException as e:
        return e.response.status_code if e.response is not None else 0


def _deliver(db: Database, subs: list[PushSubscription], payload: dict, send: Sender) -> int:
    """구독들에 보낸다. 없어진 구독(404·410)은 지운다. 받은 구독 수를 돌려준다."""
    delivered = 0
    for sub in subs:
        status = send(sub, payload)
        if status in (404, 410):
            with db.session() as session:
                session.execute(delete(PushSubscription).where(PushSubscription.id == sub.id))
        elif 200 <= status < 300:
            delivered += 1
        else:
            log.warning("알림 보내기 실패 (상태 %s)", status)
    return delivered


def send_test(db: Database, user_id: str, send: Sender = webpush_sender) -> int:
    payload = {
        "title": "전역도우미 알림이 켜졌어요",
        "body": "신청 기한 30일·7일·1일 전에 이렇게 알려 드릴게요.",
        "url": "/?page=journey",
        "tag": "test",
    }
    return _deliver(db, subscriptions(db, user_id), payload, send)


async def run_once(
    db: Database,
    profile_of: ProfileGetter,
    now: datetime | None = None,
    send: Sender = webpush_sender,
) -> int:
    """구독한 사용자들의 기한을 확인해 보낼 알림을 보낸다. 보낸 알림 수를 돌려준다."""
    local = today_kst(now)
    if local.hour not in SEND_HOURS:
        return 0
    today = local.date()
    by_user: dict[str, list[PushSubscription]] = {}
    for sub in subscriptions(db):
        by_user.setdefault(sub.user_id, []).append(sub)

    count = 0
    for user_id, subs in by_user.items():
        discharge = (await profile_of(user_id)).get("discharge_date")
        if not discharge:
            continue
        with db.session() as session:
            items = list(
                session.scalars(
                    select(JourneyItem).where(
                        JourneyItem.user_id == user_id, JourneyItem.done.is_(False)
                    )
                )
            )
            sent_rows = session.scalars(
                select(PushSent).where(PushSent.item_id.in_([i.id for i in items]))
            ).all()
        sent: dict[str, set[int]] = {}
        for row in sent_rows:
            sent.setdefault(row.item_id, set()).add(row.days_before)

        for item in items:
            r = reminder_for(item, discharge, today, sent.get(item.id, set()))
            if r is None:
                continue
            delivered = await asyncio.to_thread(_deliver, db, subs, message(r), send)
            # 받은 곳이 없어도(구독이 모두 없어졌어도) 기록해 같은 알림을 계속 시도하지 않는다.
            # 놓친 더 먼 알림(예: 7일 전 알림을 보내면 30일 전 알림)도 보낸 것으로 둔다.
            with db.session() as session:
                for d in REMIND_DAYS:
                    if d >= r.days_before and d not in sent.get(item.id, set()):
                        session.add(PushSent(item_id=item.id, days_before=d))
            count += delivered
    return count


async def loop(db: Database, profile_of: ProfileGetter) -> None:
    """서버가 켜져 있는 동안 한 시간마다 기한 알림을 확인한다."""
    while True:
        try:
            sent = await run_once(db, profile_of)
            if sent:
                log.info("기한 알림 %d건 보냄", sent)
        except Exception:
            log.warning("기한 알림 확인 실패", exc_info=True)
        await asyncio.sleep(CHECK_EVERY)
