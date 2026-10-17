"""가드레일: 사용자 입력과 최종 답변을 규칙으로 검사한다.

- 입력: 프롬프트 인젝션(지시 무시, 시스템 프롬프트 요구 등)은 검색·답변 노드에 가기 전에 막는다.
  주민등록번호·카드번호·군번처럼 답에 필요 없는 개인정보는 LLM과 대화 기록에 남지 않게 가린다.
- 출력: 답변에 개인정보 형식이 섞이면 가린다 (입력에서 이미 가리므로 이중 안전장치).

LLM으로 판단하지 않고 규칙만 쓴다: 질문마다 1~2초를 더 쓰지 않기 위해서다. 이 서비스는 도구가
모두 조회 전용이라 인젝션이 새어 나가도 바꿀 수 있는 것이 없고(최소 권한), 답변은 근거 검증을
한 번 더 거친다.
"""

from __future__ import annotations

import re

# 정상 질문에 잘 나오지 않는 표현만 넣는다 ('무시'만으로는 막지 않는다: '무시당했어요' 등)
INJECTION_PATTERNS = [
    r"(이전|앞|위|기존|모든)\s*(의\s*)?(지시|지침|명령|규칙|프롬프트)[을를은는]?\s*(다\s*)?(무시|잊어|따르지)",
    r"(시스템|system)\s*(프롬프트|prompt|메시지|지시)",
    r"(너|당신|네)의?\s*(프롬프트|지시문|설정|규칙)[을를]?\s*(보여|알려|출력|말해)",
    r"ignore\s+(all\s+|the\s+)?(previous|above|prior)\s+(instructions|prompts?)",
    r"(disregard|forget)\s+(all\s+|your\s+)?(previous\s+)?(instructions|rules)",
    r"\b(jailbreak|DAN\s*mode|developer\s*mode)\b",
    r"(지금부터|이제부터)\s*(너는|넌|당신은)\s*.{0,20}(아니|역할|행세|흉내)",
]
_INJECTION = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)

BLOCKED_REPLY = (
    "그 요청은 도와드릴 수 없어요. 전역 준비와 전역 후 혜택(취업·교육·주거·금융·보훈 등)에 대해 "
    "궁금한 것을 물어봐 주세요."
)

# (이름, 정규식, 바꿀 말). 전화번호는 기관 안내에 필요해서 가리지 않는다.
PII_PATTERNS = [
    ("주민등록번호", re.compile(r"(?<!\d)\d{6}\s*-\s*[1-8]\d{6}(?!\d)"), "[주민등록번호 가림]"),
    ("카드번호", re.compile(r"(?<!\d)\d{4}([- ])\d{4}\1\d{4}\1\d{4}(?!\d)"), "[카드번호 가림]"),
    ("군번", re.compile(r"(?<!\d)\d{2}-\d{8}(?!\d)"), "[군번 가림]"),
]


def is_injection(text: str) -> bool:
    return bool(_INJECTION.search(text or ""))


def mask_pii(text: str) -> tuple[str, list[str]]:
    """개인정보 형식을 가린 글과 가린 종류 목록."""
    found = []
    for name, pattern, replacement in PII_PATTERNS:
        text, n = pattern.subn(replacement, text)
        if n:
            found.append(name)
    return text, found
