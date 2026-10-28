"""안전 규칙이 지시문에서 실수로 빠지지 않았는지 지키는 테스트 (모델 호출 없음).

답변·검증 지시문은 평가를 수백 번 돌려 가며 다듬은 것이라, 한 줄이 지워지거나 바뀌면 틀린 안내가
다시 나올 수 있다. 모델을 부르는 평가는 키와 자료가 필요해 CI에서 돌리지 못하므로, 평가에서 실패로
이어졌던 규칙이 지시문에 남아 있는지만 매번 확인한다.
"""

import pytest

from jeonyeok_helper.agents.prompts import RESPOND_PROMPT, VERIFY_PROMPT


def system_text(prompt) -> str:
    return prompt.messages[0].prompt.template


@pytest.mark.parametrize(
    "rule",
    [
        "도구 원문",  # 원문에 있는 내용만 근거로 쓴다
        "지어내지 말 것",  # 금액·기한·자격 조건을 만들어 내지 않는다
        "프로필과 하나씩 대조",  # 대상이 다른 혜택을 넣지 않는다
        "참전유공자",  # 일반 전역자에게 참전 수당을 안내하지 않는다
        "해당하는 지역 사업은 찾지 못했어요",
        "구·군 단위 혜택",  # 시·도만 알 때 구청 혜택을 쓰지 않는다
        "소관 기관에 꼭 확인하세요",
    ],
)
def test_respond_prompt_keeps_safety_rule(rule):
    assert rule in system_text(RESPOND_PROMPT)


@pytest.mark.parametrize(
    "rule",
    [
        "원문에 없는 혜택",  # 근거 없는 주장은 지운다
        "edits",  # 고칠 부분만 받는다
        "지우지 마세요",  # '찾지 못했어요' 같은 없다는 안내는 지우지 않는다
    ],
)
def test_verify_prompt_keeps_rule(rule):
    assert rule in system_text(VERIFY_PROMPT)
