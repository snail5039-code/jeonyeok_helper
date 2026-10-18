"""신청 서류 도우미: "전직지원금 신청할래요" → 챙길 서류, 내 정보로 채운 신청 내용, 낼 곳.

제도마다 무엇을 들고 어디로 가는지는 data/applications.yaml에 근거 자료 그대로 정리해 두고
(LLM이 서류 목록을 지어내지 않게), 여기서는 내 정보(복무 형태·계급·전역일·지역)로
- 대상에 맞는지 미리 알려 주고
- 신청서에 적을 내용을 채우고 (이름·주민등록번호는 저장하지 않으니 직접 적는 칸으로)
- 사는 곳 관할 보훈(지)청을 찾고
- 전역일로 신청 마감일을 계산한다.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from jeonyeok_helper.benefits.offices import find_offices, load_offices
from jeonyeok_helper.config import DATA_DIR, load_yaml

APPLICATIONS_FILE = DATA_DIR / "applications.yaml"

SERVICE_NAMES = {
    "conscript": "의무복무 병사",
    "short_term_officer": "단기복무 간부 (5년 미만)",
    "long_term": "중·장기복무 간부 (5년 이상)",
    "merit": "보훈대상자",
}
# 신청하려는 말: 제도 이름 + 이 중 하나 ("전직지원금 신청할래요", "보훈 등록 서류 뭐 필요해요")
APPLY_WORDS = re.compile(
    r"신청|서류|준비|접수|어디에?\s*내|어디서\s*해|어떻게|하려고|할래|하고\s*싶|방법|연기"
)


class Document(BaseModel):
    name: str
    by: str = "me"  # me: 내가 낸다, office: 기관이 직접 확인
    how: str = ""


class FormField(BaseModel):
    label: str
    field: str | None = None
    hint: str = ""


class Link(BaseModel):
    name: str
    url: str


class Submit(BaseModel):
    office: str | None = None  # veterans: 관할 보훈(지)청
    where: str = ""
    ways: list[str] = []
    online: Link | None = None
    phone: str = ""


class Deadline(BaseModel):
    text: str
    due_months: int | None = None


class SourceRef(BaseModel):
    type: str
    title: str
    url: str = ""


class Program(BaseModel):
    id: str
    title: str
    short: str
    aliases: list[str]
    summary: str
    fits: list[str]
    needs_injury: bool = False
    fit_note: str
    steps: list[str]
    documents: list[Document]
    form: list[FormField]
    submit: Submit
    deadline: Deadline
    sources: list[SourceRef]


@lru_cache
def load_programs(path: Path = APPLICATIONS_FILE) -> tuple[Program, ...]:
    return tuple(Program(**p) for p in load_yaml(path, "programs"))


def get_program(program_id: str) -> Program | None:
    return next((p for p in load_programs() if p.id == program_id), None)


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def find_program(text: str) -> Program | None:
    """말에 나온 제도 (띄어쓰기는 무시). 여러 개면 가장 긴 이름이 맞은 것."""
    said = _squash(text)
    best: tuple[int, Program] | None = None
    for p in load_programs():
        for alias in p.aliases:
            if _squash(alias) in said and (best is None or len(alias) > best[0]):
                best = (len(alias), p)
    return best[1] if best else None


def asked_to_apply(text: str) -> Program | None:
    """신청하려는 말이면 그 제도 ("전직지원금 신청할래요"). 제도 설명만 묻는 말은 아니다."""
    program = find_program(text)
    return program if program and APPLY_WORDS.search(text) else None


def _value(field: str, profile: dict) -> str:
    v = profile.get(field)
    if v in (None, "", []):
        return ""
    if field == "service_type":
        return SERVICE_NAMES.get(str(v), str(v))
    if field == "service_years":
        return f"{v}년"
    if field == "age":
        return f"{v}세"
    if isinstance(v, list):
        return ", ".join(map(str, v))
    return str(v)


def fit(program: Program, profile: dict) -> dict:
    """내 정보로 본 대상 여부: ok(맞아 보임) / check(확인 필요) / unlikely(대상이 아닐 수 있음)"""
    service = profile.get("service_type")
    if not service:
        return {
            "level": "check",
            "text": f"복무 형태를 알면 대상인지 알려 드릴게요. {program.fit_note}",
        }
    if service not in program.fits:
        name = SERVICE_NAMES.get(service, service)
        return {"level": "unlikely", "text": f"{name}는 대상이 아닐 수 있어요. {program.fit_note}"}
    if program.needs_injury and not profile.get("injury"):
        return {"level": "check", "text": program.fit_note}
    return {"level": "ok", "text": program.fit_note}


def build_kit(program: Program, profile: dict | None) -> dict:
    """화면에 그릴 신청 키트. 내 정보로 채울 수 있는 것은 채운다."""
    from jeonyeok_helper.push import due_date

    profile = profile or {}
    form = []
    for f in program.form:
        value = _value(f.field, profile) if f.field else ""
        form.append(
            {
                "label": f.label,
                "value": value,
                # 내 정보 칸인데 비었으면 채우는 곳을, 직접 적는 칸이면 안내를
                "hint": f.hint or ("내 정보에 넣으면 채워져요" if f.field and not value else ""),
                "from_profile": bool(f.field),
            }
        )

    offices = []
    if program.submit.office == "veterans" and profile.get("region"):
        offices = [
            o.model_dump(exclude={"regions"})
            for o in find_offices(load_offices(), str(profile["region"]))
        ]

    due = due_date(profile.get("discharge_date"), program.deadline.due_months)
    return {
        "id": program.id,
        "title": program.title,
        "short": program.short,
        "summary": program.summary,
        "fit": fit(program, profile),
        "steps": program.steps,
        "documents": [d.model_dump() for d in program.documents],
        "form": form,
        "submit": program.submit.model_dump() | {"offices": offices},
        "deadline": {"text": program.deadline.text, "date": due.isoformat() if due else None},
        "sources": [s.model_dump() for s in program.sources],
    }


def summaries() -> list[dict]:
    return [
        {"id": p.id, "title": p.title, "short": p.short, "summary": p.summary, "aliases": p.aliases}
        for p in load_programs()
    ]
