"""이어 하기 코드: 로그인 없이 다른 기기에서 같은 기록을 여는 짧은 코드.

익명 ID(UUID)는 길어서 옮겨 적기 어렵다. 헷갈리는 글자(0·O·1·I·L)를 뺀 31자 중 8자로 만든
코드(예: JY-7K3Q-9XPA)를 익명 ID에 이어 둔다. 경우의 수가 약 8,500억이라 찍어서 맞히기 어렵고,
API는 코드 확인을 1분 횟수로 제한한다. 코드는 비밀번호가 아니라 '이 기록의 열쇠'라서, 새로 만들면
이전 코드는 바로 쓸 수 없게 된다.
"""

from __future__ import annotations

import re
import secrets

from sqlalchemy import delete, select

from jeonyeok_helper.db import Database, ResumeCode

ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
LENGTH = 8
PREFIX = "JY"


def _random_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def display(code: str) -> str:
    """저장한 코드(8자)를 보여 주는 모양으로: JY-7K3Q-9XPA"""
    return f"{PREFIX}-{code[:4]}-{code[4:]}"


def normalize(text: str) -> str | None:
    """사람이 적은 코드를 저장 모양으로. 소문자·띄어쓰기·하이픈·앞의 JY는 무시한다.
    코드에 없는 글자(0·O·1·I·L 등)가 있으면 틀린 코드로 본다."""
    raw = re.sub(r"[\s-]", "", text.upper())
    if raw.startswith(PREFIX) and len(raw) == LENGTH + len(PREFIX):
        raw = raw[len(PREFIX) :]
    if len(raw) != LENGTH or any(c not in ALPHABET for c in raw):
        return None
    return raw


def get_code(db: Database, user_id: str) -> str | None:
    with db.session() as session:
        row = session.scalar(select(ResumeCode).where(ResumeCode.user_id == user_id))
        return display(row.code) if row else None


def new_code(db: Database, user_id: str) -> str:
    """이 사용자의 코드를 새로 만든다 (이전 코드는 지운다)."""
    with db.session() as session:
        session.execute(delete(ResumeCode).where(ResumeCode.user_id == user_id))
        while True:
            code = _random_code()
            if session.get(ResumeCode, code) is None:
                break
        session.add(ResumeCode(code=code, user_id=user_id))
    return display(code)


def find_user(db: Database, text: str) -> str | None:
    code = normalize(text)
    if code is None:
        return None
    with db.session() as session:
        row = session.get(ResumeCode, code)
        return row.user_id if row else None
