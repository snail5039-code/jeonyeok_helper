"""길잡이: 검색 결과를 늘어놓는 대신, 사용자를 로드맵을 따라 한 걸음씩 안내한다.

    coach (질문마다 맨 앞)
      ├ talk     → 인사, 진행 보고('했어요'), '다음 뭐 해요?', 정보 알려 주기
      │            → 검색 없이 바로 짧게 답
      └ research → 기존 RAG(supervisor → 워커 → 답변 → 검증) → guide

    guide (검색 답변 뒤): 답변 위에 보일 한마디('지금 이것부터')와 로드맵에 담을 할 일 제안

빠른 답 버튼은 LLM이 아니라 여기서 정해진 규칙으로 만든다.
- 처음 쓰는 사람: 복무 형태 → 지역 → 전역일을 하나씩 버튼으로 묻는다 (missing_field)
- 로드맵이 있으면: 다음 할 일 하나를 권하고 [했어요] [어떻게 해요?] [나중에] (next_item)

로드맵은 DB에 있고 그래프는 DB를 모른다. API가 할 일 목록을 config의 journey로 넘긴다.
"""

from __future__ import annotations

import os
import re
from datetime import date
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from jeonyeok_helper.agents.prompts import COMMON
from jeonyeok_helper.agents.roadmap import STAGE_TITLES, StageKey, fits_education, fits_service_text
from jeonyeok_helper.journey import ground_deadline

STAGE_ORDER = {key: i for i, key in enumerate(STAGE_TITLES)}

# 처음 쓰는 사람에게 차례로 물을 것 (로드맵을 만드는 데 꼭 필요한 셋)
ONBOARDING = ("service_type", "region", "discharge_date")
FIELD_LABELS = {"service_type": "복무 형태", "region": "사는 지역", "discharge_date": "전역일"}
# 길잡이 말이 질문으로 끝나지 않으면 붙인다 (버튼만 덩그러니 나오지 않게)
ASK_QUESTIONS = {
    "service_type": "어떻게 복무했어요?",
    "region": "지금 어디 살아요?",
    "discharge_date": "언제 전역했어요? (예정이어도 괜찮아요)",
}


def with_question(say: str, missing: str | None) -> str:
    say = say.strip()
    if missing and not say.rstrip(" )").endswith("?"):
        say = f"{say} {ASK_QUESTIONS[missing]}"
    return say


SERVICE_REPLIES = [
    ("의무복무 병사", "의무복무 병사로 전역했어요"),
    ("단기 간부 (5년 미만)", "단기 간부로 5년 미만 복무했어요"),
    ("중·장기 복무 (5년 이상)", "중·장기 복무 간부로 5년 이상 복무했어요"),
    ("보훈대상자", "국가유공자·보훈대상자예요"),
]
REGIONS = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기",
    "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]  # fmt: skip


# 이런 말이 들어간 질문은 자료를 찾아 답한다 (LLM이 아는 척 말로 넘기지 않게)
RESEARCH_WORDS = re.compile(
    "|".join(
        ["어떻게", "방법", "절차", "서류", "자격", "조건", "얼마", "금액", "언제까지", "기한",
         "어디서", "어디에", "신청", "받을 수", "받을수", "되나요", "혜택", "지원금",
         "뭐 받", "뭐가 있", "뭐 있",
         # 자격을 확인하는 말: 길잡이가 기억으로 '맞아요'라고 답하지 않고 근거를 찾게 (평가 h29)
         "맞죠", "맞나요", "해당되", "해당하나", "인정되", "인정돼", "쳐주"]
    )
)  # fmt: skip


# '했어요'를 잘못 눌렀다는 말 (이건 신청 방법을 묻는 게 아니라 완료를 되돌려 달라는 것)
REOPEN_WORDS = re.compile(r"실수로|잘못 눌|잘못눌|되돌|취소|아직 안 ?했|안 했는데|놓쳤|다시 해")


# ---------- 프로필 보정 ----------

CONSCRIPT_WORDS = re.compile(r"이병|일병|상병|병장|병사")
LONG_YEARS = re.compile(r"(\d{1,2})\s*년\s*(?:넘게|이상|간|동안|차)?\s*복무")
MERIT_WORDS = re.compile(r"유공자|보훈대상|보훈보상|상이등급|등록(했|됐|되었|돼)|등록자")


# 전역일을 말했다고 볼 수 있는 단서: 연도, 'N월', 작년·올해, 'N년 됐어요', 'N개월 뒤' 등
DATE_HINT = re.compile(
    r"\d{4}|\d{1,2}\s*월|재작년|작년|올해|내년|지난\s*달|이번\s*달|다음\s*달|다음\s*주|어제|오늘|"
    r"\d+\s*(년|개월|달|주)\s*(전|후|뒤|됐|되었|지났|남았)"
)


# 복무 정보를 말했을 수 있는 단서. 하나도 없으면 프로필 추출(LLM 약 3초)을 건너뛴다.
# '군 복무기간이 국민연금에 인정되나요?'처럼 제도만 묻는 말에는 새로 알 정보가 없다.
PROFILE_HINT = re.compile(
    r"\d|병사|병장|상병|일병|이병|간부|장교|부사관|준사관|하사|중사|상사|원사|소위|중위|대위|소령|"
    r"중령|대령|준위|의무\s*복무|단기|중기|장기|직업\s*군인|현역|상근|사회\s*복무|공익|전환\s*복무|"
    r"유공자|보훈|상이|다쳤|다친|부상|아파|질병|살아|살고|사는|거주|이사|나이|살이|세예요|"
    r"재작년|작년|올해|내년|지난\s*달|이번\s*달|다음\s*달|곧\s*전역|전역\s*예정|전역\s*했|제대\s*했|"
    + "|".join(REGIONS)
)


def may_tell_profile(text: str) -> bool:
    return bool(PROFILE_HINT.search(text))


def repair_profile(user_text: str, new: dict) -> dict:
    """추출된 프로필에서 사용자가 말하지 않은 것을 뺀다.

    '의병전역했는데 보훈 등록 가능한가요?'를 이미 보훈대상자로 등록한 사람으로 읽은 적이 있다
    (등록을 물은 것이지 등록했다고 한 것이 아니다). 등록했다고 말해야만 인정한다."""
    from jeonyeok_helper.agents.state import cadre_of

    out = dict(new)
    if out.get("service_type") == "unknown":
        out.pop("service_type")
    if out.get("service_type") == "merit" and not MERIT_WORDS.search(user_text):
        out.pop("service_type")
    # 날짜를 말하지 않았는데 전역일을 채우지 않는다 ('병사로 전역했어, 1년 안에 할 일'을
    # 전역일 2027-10으로 읽은 적이 있다, 평가 c20)
    if out.get("discharge_date") and not DATE_HINT.search(user_text):
        out.pop("discharge_date")
    last = user_text.strip().splitlines()[-1] if user_text.strip() else ""
    # 모델이 분명한 말도 '모름'으로 비우는 일이 있어(평가 c08·l03·t01) 확실한 경우만 채운다
    if not out.get("service_type"):
        if MERIT_WORDS.search(str(out.get("merit_status") or "")):
            # '국가유공자인데'를 보훈 칸에만 넣고 복무 형태는 비운 경우 (평가 m04)
            out["service_type"] = "merit"
        elif CONSCRIPT_WORDS.search(last):
            out["service_type"] = "conscript"
        elif (m := LONG_YEARS.search(last)) and int(m[1]) >= 5:
            out["service_type"] = "long_term"  # 병사는 5년을 복무하지 않는다
    # 장교·부사관 구분은 이번에 한 말에서만 읽는다 (앞 대화의 다른 계급과 섞이지 않게)
    if (cadre := cadre_of(last)) and out.get("service_type") != "conscript":
        out["cadre"] = cadre
    return out


# '그거 신청 어디서 해요?'처럼 가리키는 말로 시작하는 질문
# ('그 지원금 아직 신청돼요?'처럼 '그 + 제도 이름 대신 쓰는 말'도 포함, 평가 h27)
VAGUE_START = re.compile(
    r"^\s*(그거|이거|저거|그것|이것|거기|그건|이건|"
    r"(그|이|저)\s*(지원금|제도|혜택|카드|사업|서류|프로그램|교육|돈|수당|대출))"
)


def needs_research(text: str) -> bool:
    return bool(RESEARCH_WORDS.search(text)) and not REOPEN_WORDS.search(text)


def is_vague_first_turn(text: str, turns: int) -> bool:
    """대화 첫 마디가 가리키는 말뿐이면 무엇을 묻는지 알 수 없다 (되물어야 한다)."""
    return turns <= 1 and bool(VAGUE_START.match(text))


def find_done(items: list[dict], title: str) -> dict | None:
    """완료한 할 일 중 이 제목과 같은 것 (LLM이 제목을 조금 다르게 적어도 찾는다)."""
    title = title.strip()
    if not title:
        return None
    done = [i for i in items if i.get("done")]
    return next((i for i in done if same_task(i["title"], title)), None)


def missing_field(profile: dict | None) -> str | None:
    p = profile or {}
    for key in ONBOARDING:
        value = p.get(key)
        if not value or value == "unknown":
            return key
    return None


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def mentions(say: str, title: str) -> bool:
    """길잡이 말이 이 할 일을 이미 언급했는지 (제목 첫 낱말, 예: '예비군 훈련 참여' → '예비군')."""
    first = title.split()[0] if title.split() else title
    return _squash(title) in _squash(say) or (len(first) >= 3 and first in say)


def same_task(a: str, b: str) -> bool:
    """제목이 거의 같은 할 일 ('장병내일준비적금 수령' ≈ '장병내일준비적금 정부지원금 수령')."""
    x, y = _squash(a), _squash(b)
    return x in y or y in x or len(os.path.commonprefix([x, y])) >= 6


def with_next_step(say: str, item: dict) -> str:
    """길잡이 말에 다음 할 일이 없으면 덧붙인다."""
    say = say.strip()
    if mentions(say, item["title"]):
        return say
    return f"{say} 다음은 '{item['title']}' 차례예요. {item.get('action', '')}".strip()


def ask_replies(field: str, today: date | None = None) -> list[dict]:
    """빠진 정보를 고르는 버튼. 누르면 message가 사용자 말로 보내진다."""
    today = today or date.today()
    if field == "service_type":
        return [{"label": label, "message": msg} for label, msg in SERVICE_REPLIES]
    if field == "region":
        return [{"label": r, "message": f"{r} 살아요"} for r in REGIONS]
    if field == "discharge_date":
        y = today.year
        return [
            {"label": "아직 복무 중 (전역 예정)", "message": f"{y + 1}년 초에 전역 예정이에요"},
            {"label": f"{y}년 전역", "message": f"{y}년에 전역했어요"},
            {"label": f"{y - 1}년 전역", "message": f"{y - 1}년에 전역했어요"},
            {"label": f"{y - 2}년 이전", "message": f"{y - 2}년에 전역했어요"},
        ]
    return []


def next_item(items: list[dict], skipped: list[str] | None = None) -> dict | None:
    """다음에 권할 할 일: 안 끝낸 것 중 핵심 → 기한 빠른 것 → 단계 순."""
    skip = set(skipped or [])
    open_items = [i for i in items if not i.get("done") and i.get("id") not in skip]
    if not open_items:
        return None

    def key(i: dict):
        due = i.get("due_months")
        return (
            not i.get("core"),
            due is None,
            due if due is not None else 0,
            STAGE_ORDER.get(i.get("stage", ""), 99),
        )

    return min(open_items, key=key)


def kit_replies(question: str) -> list[dict]:
    """신청하려는 말이면("전직지원금 신청할래요") 그 제도의 신청 서류 도우미를 여는 버튼."""
    from jeonyeok_helper.applications import asked_to_apply

    program = asked_to_apply(question)
    return (
        [{"label": f"{program.short} 서류 챙기기", "open": f"kit:{program.id}"}] if program else []
    )


def step_replies(item: dict) -> list[dict]:
    title, item_id = item["title"], item["id"]
    return [
        {
            "label": "했어요",
            "message": f"'{title}' 했어요",
            "action": {"type": "done", "item_id": item_id},
        },
        {"label": "어떻게 해요?", "message": f"{title}, 어떻게 신청해요?"},
        {
            "label": "나중에 할게요",
            "message": "이건 나중에 할게요. 다음 거 알려줘요",
            "action": {"type": "later", "item_id": item_id},
        },
    ]


def format_journey(items: list[dict], nxt: dict | None) -> str:
    if not items:
        return "(아직 로드맵 없음)"
    done = sum(bool(i.get("done")) for i in items)
    core = [i for i in items if i.get("core")]
    core_done = sum(bool(i.get("done")) for i in core)
    lines = [f"할 일 {len(items)}개 중 {done}개 완료 (핵심 {core_done}/{len(core)})"]
    for i in items[:20]:
        mark = "✓" if i.get("done") else "·"
        stage = STAGE_TITLES.get(i.get("stage", ""), "")
        extra = f" (기한: {i['deadline']})" if i.get("deadline") else ""
        lines.append(f"{mark} [{stage}] {i['title']}: {i.get('action', '')}{extra}")
    if nxt:
        what = f"{nxt['title']} - {nxt.get('action', '')} {nxt.get('detail', '')}"
        lines.append(f"\n지금 권할 다음 할 일: {what}")
    return "\n".join(lines)


# ---------- coach: 이번 질문을 바로 말로 답할지, 자료를 찾아 답할지 ----------

COACH_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            COMMON + "\n\n당신은 전역자의 '길잡이' 전역이입니다. 사용자를 전역 로드맵을 따라 "
            "한 걸음씩 안내합니다. 이번 메시지를 어떻게 처리할지 고르세요.\n"
            "기본은 research(자료를 찾아 답하기)입니다. 아래 경우에만 talk를 고르세요.\n"
            "talk:\n"
            "1. 인사·감사·잡담 ('안녕하세요', '고마워요')\n"
            "2. 진행 보고 ('~ 했어요', '나중에 할게요')\n"
            "3. 복무 형태·지역·전역일 같은 자기 정보만 말하고 따로 묻는 것이 없을 때\n"
            "4. 다음 할 일 안내 요청 ('다음 뭐 해요?', '뭐부터 해야 돼요?', '로드맵 만들어 줘')\n"
            "5. 완료 표시를 되돌려 달라는 말 ('실수로 했어요 눌렀어', '그거 아직 안 했어', "
            "'놓쳤어 다시 해줘'): reopen에 로드맵에서 ✓ 표시된 그 할 일 제목을 그대로 쓰고, say로 "
            "되돌렸다고 알려 주세요\n"
            "6. '그거', '이거'처럼 가리키는 말뿐이고 앞 대화에 그 대상이 없어서 무엇을 묻는지 "
            "알 수 없을 때: say에서 어떤 혜택·제도를 말하는지 되물으세요 (기관을 지어내지 말 것)\n"
            "그 밖에 혜택·제도·법령·자격·금액·기한·서류·신청 방법('어떻게 신청해요?')·기관을 "
            "묻는 질문은 모두 research ('혜택 뭐 있어요?'처럼 복무 형태를 몰라도: 병사 기준으로 "
            "찾고 화면이 따로 유형을 묻습니다). 애매하면 research.\n\n"
            "talk일 때 say에 사용자에게 할 말을 쓰세요.\n"
            "- 2~3문장, 짧고 친근한 반말 섞인 해요체 ('~했군요' 같은 딱딱한 말 대신 "
            "'오, 좋아요!', '굿!'). 군대 농담은 가끔 한 번만 (예: '충성!', '말년 병장 폼').\n"
            "- 금액·자격·기한 같은 사실은 아래 '로드맵'에 적힌 것만. 모르면 "
            "'자세히 알아볼까요?'로 넘기기\n"
            "- '빠진 정보'가 있으면 say 끝에 그것을 묻는 질문 하나 (고르는 버튼이 함께 나옴)\n"
            "- 빠진 정보가 없고 '지금 권할 다음 할 일'이 있으면 그 할 일을 한 문장으로 "
            "권하기 ([했어요] [어떻게 해요?] [나중에] 버튼이 함께 나옴)\n"
            "- 로드맵이 아직 없고 빠진 정보도 없으면 '로드맵을 만들고 있어요'라고 말하기\n"
            "- 전역과 관계없는 말(날씨·시사·장난)이나 뜻을 알 수 없는 입력이면, 인사로 착각하지 "
            "말고 첫 문장에서 '그건 제가 도울 수 없어요'(못 알아들었으면 "
            "'무슨 말인지 잘 모르겠어요')라고 분명히 말한 뒤, "
            "전역 혜택·절차는 도울 수 있다고 짧게 이어 가기\n\n"
            "오늘: {today}\n사용자 프로필: {profile}\n빠진 정보: {missing}\n\n로드맵:\n{journey}",
        ),
        MessagesPlaceholder("messages"),
    ]
).partial(today=lambda: date.today().isoformat())


class CoachDecision(BaseModel):
    mode: Literal["research", "talk"]
    say: str = Field(default="", description="talk일 때 사용자에게 할 말 (2~3문장)")
    reopen: str = Field(
        default="", description="완료를 되돌려 달라는 할 일의 제목 (로드맵의 ✓ 할 일). 아니면 빈 칸"
    )


def make_coach(llm) -> Runnable:
    return COACH_PROMPT | llm.with_structured_output(CoachDecision)


# ---------- guide: 검색 답변 위의 한마디 + 로드맵에 담을 할 일 제안 ----------

GUIDE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "당신은 전역자의 길잡이 전역이입니다. 아래 상담 답변은 길어서, 그 위에 보일 "
            "짧은 한마디와 로드맵에 담을 할 일을 정합니다.\n"
            "say: 1~2문장, 친근한 해요체. "
            "질문이 차이·뜻·가능 여부·조건을 묻는 설명 질문이면 "
            "('차이가 뭐예요?', '받을 수 있어요?', '~인가요?') "
            "답변의 결론을 먼저 그대로 요약하세요 "
            "(예: '크레딧은 연금 가입 기간을 늘려 주는 거고, 전직지원금은 5년 이상 복무자의 구직 "
            "지원금이에요'). 그 밖의 질문이면 답변에서 '지금 가장 먼저 할 일' 하나를 짚으세요. "
            "구체적인 혜택·제도 이름을 말할 것 ('정부24에서 조회하세요' 같은 일반 안내는 금지). "
            "답변에 없는 사실은 쓰지 말 것. 빠진 정보가 있으면 끝에 그것을 묻는 질문 하나 "
            "(프로필에 이미 있는 정보는 묻지 말 것).\n"
            "오늘은 {today}입니다. 신청 기간이 지난 공고, 이미 지나간 일, 그리고 프로필의 "
            "'전역 상태'가 이미 전역함이면 복무 중에만 할 수 있는 일(전역예정장병 프로그램, "
            "적금 가입, 전역 전 교육)은 say에서 권하지도, items에 담지도 말 것.\n"
            "items: 사용자가 직접 해야 할 일(신청, 등록, 확인, 준비) 0~3개.\n"
            "- 답변에 있는 내용만, 근거 출처 번호(sources)를 반드시 넣기\n"
            "- 사용자에게 해당하지 않거나 정보일 뿐이면 빼기 (빈 목록 가능)\n"
            "- '사이트에서 혜택 조회하기'처럼 특정 제도가 아닌 일반 할 일은 빼기\n"
            "- '이미 로드맵에 있는 할 일'과 같은 일은 빼기\n"
            "- stage: before(전역 전), right_after(전역 직후), job(취업·창업), study(학업), "
            "life(주거·생활), later(나중에). 사용자의 전역 시기를 고려\n"
            "- core: 놓치면 손해이거나 기한이 있는 핵심 할 일이면 true\n"
            "- deadline: 답변에 적힌 신청 기한 문구를 그대로 (예: '전역 후 3년 이내'). "
            "없으면 빈 칸\n"
            "- due_months: deadline이 전역일 기준이면 개월 수 (전역 후 3년 이내 → 36, "
            "전역 6개월 전 → -6). 아니면 비움\n"
            "- title은 혜택·제도 이름 20자 안팎, action은 '~하세요' 한 문장",
        ),
        (
            "human",
            "사용자 프로필: {profile}\n빠진 정보: {missing}\n"
            "이미 로드맵에 있는 할 일: {existing}\n\n"
            "질문: {question}\n\n답변:\n{answer}\n\n근거 출처:\n{sources}",
        ),
    ]
).partial(today=lambda: date.today().isoformat())


class PlanItemDraft(BaseModel):
    stage: StageKey
    title: str = Field(description="할 일 이름 (혜택·제도 이름, 20자 안팎)")
    action: str = Field(description="사용자가 할 일 한 문장 (예: '고용24에서 온라인 신청하세요')")
    detail: str = Field(default="", description="대상·금액·기한을 답변에 있는 대로 한 문장")
    sources: list[int] = Field(description="근거 출처 번호 (예: [1, 3]). 반드시 하나 이상")
    core: bool = Field(default=False, description="놓치면 손해이거나 기한이 있는 핵심 할 일")
    deadline: str = Field(default="", description="답변에 적힌 신청 기한 문구 그대로")
    due_months: int | None = Field(default=None, description="전역일 기준 기한(개월)")


class GuideDraft(BaseModel):
    say: str = Field(default="", description="답변 위에 보일 한마디 (1~2문장)")
    items: list[PlanItemDraft] = Field(
        default_factory=list, description="로드맵에 담을 할 일 0~3개"
    )


def make_guide(llm) -> Runnable:
    return GUIDE_PROMPT | llm.with_structured_output(GuideDraft)


def pick_items(
    draft: GuideDraft,
    *,
    answer: str,
    sources: list[dict],
    existing: list[str],
    profile: dict | None = None,
) -> list[dict]:
    """근거 출처가 있는 새 할 일만, 출처 번호는 실제 출처로 바꾸고 기한은 답변에 있을 때만."""
    known = {t.strip() for t in existing}
    p = profile or {}
    items = []
    for item in draft.items[:3]:
        refs = [sources[i - 1] for i in item.sources if 1 <= i <= len(sources)]
        title = item.title.strip()[:120]
        # 근거가 기관 안내(사이트·연락처)뿐이면 구체적인 제도가 아니다 ('정부24에서 조회' 같은 것)
        grounded = any(r.get("type") in ("regulation", "benefit") for r in refs)
        if not grounded or not title or any(same_task(title, k) for k in known):
            continue
        if not fits_education(title, p.get("education"), p.get("goals")):
            continue  # 대학원생에게 국가장학금 같은 학부 전용 장학금은 담지 않는다
        if not fits_service_text(f"{title} {item.action}", p.get("service_type")):
            continue  # 병사에게 5년 이상 복무자 전용 제도는 담지 않는다
        known.add(title)
        deadline, due = ground_deadline(item.deadline, item.due_months, [answer])
        items.append(
            {
                "stage": item.stage,
                "title": title,
                "action": item.action.strip(),
                "detail": item.detail.strip(),
                "sources": refs,
                "core": item.core,
                "deadline": deadline,
                "due_months": due,
            }
        )
    return items
