import { beforeEach, describe, expect, it } from "vitest";

import { formText, loadChecked, programFor, saveChecked, type Kit, type ProgramSummary } from "./applications";

const programs: ProgramSummary[] = [
  { id: "transition_allowance", title: "제대군인 전직지원금", short: "전직지원금", summary: "", aliases: ["전직지원금", "전직 지원금"] },
  { id: "merit_registration", title: "국가유공자 등록", short: "보훈 등록", summary: "", aliases: ["국가유공자 등록", "보훈 등록"] },
];

// vitest 기본 환경(node)에는 localStorage가 없어 간단히 흉내 낸다
const store = new Map<string, string>();
globalThis.localStorage = {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
  removeItem: (k: string) => void store.delete(k),
  clear: () => store.clear(),
  key: () => null,
  length: 0,
} as Storage;

describe("할 일에 맞는 제도", () => {
  it("띄어쓰기가 달라도 찾는다", () => {
    expect(programFor("전직 지원금 신청", programs)?.id).toBe("transition_allowance");
    expect(programFor("국가유공자등록 신청하기", programs)?.id).toBe("merit_registration");
    expect(programFor("예비군 편성 확인", programs)).toBeNull();
  });
});

describe("신청 내용 복사", () => {
  it("빈칸은 안내로 채운다", () => {
    const kit = {
      title: "제대군인 전직지원금",
      form: [
        { label: "계급", value: "중사", hint: "", from_profile: true },
        { label: "군", value: "", hint: "내 정보에 넣으면 채워져요", from_profile: true },
        { label: "계좌", value: "", hint: "", from_profile: false },
      ],
    } as Kit;
    expect(formText(kit)).toBe("[제대군인 전직지원금 신청 준비]\n계급: 중사\n군: (내 정보에 넣으면 채워져요)\n계좌: (직접 적기)");
  });
});

describe("챙긴 서류", () => {
  beforeEach(() => store.clear());

  it("사람·제도마다 따로 기억한다", () => {
    saveChecked("me", "transition_allowance", ["전직지원금 지급신청서"]);
    expect(loadChecked("me", "transition_allowance")).toEqual(["전직지원금 지급신청서"]);
    expect(loadChecked("me", "merit_registration")).toEqual([]);
    expect(loadChecked("other", "transition_allowance")).toEqual([]);
  });

  it("깨진 값은 빈 목록", () => {
    store.set("jeonyeok.kit.me.x", "{broken");
    expect(loadChecked("me", "x")).toEqual([]);
  });
});
