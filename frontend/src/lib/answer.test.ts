import { describe, expect, it } from "vitest";

import { benefitKind, parseAnswer, splitInline } from "./answer";

describe("parseAnswer", () => {
  it("요약, 혜택 블록, 마무리 문단으로 나눈다", () => {
    const text = [
      "의무복무를 마쳤다면 혜택이 2가지 있어요 [1].",
      "",
      "### 군복무 크레딧 | 국민연금공단",
      "- 대상: 병역 이행자",
      "- **내용**: 가입기간 추가 인정 [1]",
      "- 노령연금 청구 때 반영돼요",
      "### 2. 국민취업지원제도 | 고용노동부",
      "- 신청：고용24",
      "정확한 자격과 기한은 소관 기관에 꼭 확인하세요.",
    ].join("\n");

    const { lead, benefits, tail } = parseAnswer(text);

    expect(lead).toEqual(["의무복무를 마쳤다면 혜택이 2가지 있어요 [1]."]);
    expect(benefits).toHaveLength(2);
    expect(benefits[0]).toEqual({
      title: "군복무 크레딧",
      org: "국민연금공단",
      fields: [
        ["대상", "병역 이행자"],
        ["내용", "가입기간 추가 인정 [1]"],
      ],
      extra: ["노령연금 청구 때 반영돼요"],
    });
    // 번호 붙은 제목과 전각 콜론도 인식한다.
    expect(benefits[1].title).toBe("국민취업지원제도");
    expect(benefits[1].fields).toEqual([["신청", "고용24"]]);
    expect(tail).toEqual(["정확한 자격과 기한은 소관 기관에 꼭 확인하세요."]);
  });

  it("블록 없는 단순 답변은 요약 문단만 남는다", () => {
    expect(parseAnswer("안녕하세요!\n무엇이 궁금하세요?")).toEqual({
      lead: ["안녕하세요!", "무엇이 궁금하세요?"],
      benefits: [],
      tail: [],
    });
  });
});

describe("splitInline", () => {
  it("굵은 글씨와 출처 번호를 나눈다", () => {
    expect(splitInline("**크레딧**은 연금에 반영 [12]돼요")).toEqual([
      { kind: "bold", value: "크레딧" },
      { kind: "text", value: "은 연금에 반영 " },
      { kind: "cite", index: 12 },
      { kind: "text", value: "돼요" },
    ]);
  });

  it("HTML은 글자 그대로 둔다 (렌더링은 React가 이스케이프)", () => {
    expect(splitInline("<b>x</b>")).toEqual([{ kind: "text", value: "<b>x</b>" }]);
  });
});

describe("benefitKind", () => {
  it.each([
    ["군복무 크레딧", "pension"],
    ["국민취업지원제도", "job"],
    ["국가장학금", "school"],
    ["예비군 편성 확인", "reserve"],
    ["국가유공자 등록", "merit"],
    ["서울시 청년 정책", "region"],
    ["기타 지원", "other"],
  ])("%s → %s", (title, kind) => {
    expect(benefitKind(title)).toBe(kind);
  });
});
