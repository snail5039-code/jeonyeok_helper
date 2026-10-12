import { describe, expect, it } from "vitest";

import { badges, byStage, currentStage, levelOf, profileCompleteness, progress } from "./journey";
import type { JourneyItem, Profile, StageKey } from "./types";

let n = 0;
const item = (stage: StageKey, done = false, origin: "plan" | "chat" = "plan"): JourneyItem => ({
  id: `i${++n}`,
  stage,
  title: `할 일 ${n}`,
  action: "",
  detail: "",
  sources: [],
  origin,
  question: "",
  done,
  created_at: null,
  done_at: null,
});

describe("progress / levelOf", () => {
  it("빈 로드맵은 0%, 이병", () => {
    expect(progress([])).toEqual({ done: 0, total: 0, percent: 0 });
    expect(levelOf(0).rank).toBe("이병");
  });

  it("진행률에 따라 계급이 오른다", () => {
    expect(levelOf(19).rank).toBe("이병");
    expect(levelOf(20).rank).toBe("일병");
    expect(levelOf(50).rank).toBe("상병");
    expect(levelOf(75).rank).toBe("병장");
    expect(levelOf(100)).toMatchObject({ rank: "민간인", next: 0 });
    expect(levelOf(30).next).toBe(15);
  });

  it("완료 개수로 퍼센트를 반올림한다", () => {
    expect(progress([item("job", true), item("job"), item("job")]).percent).toBe(33);
  });
});

describe("currentStage / byStage", () => {
  it("남은 할 일이 있는 첫 단계", () => {
    expect(currentStage([])).toBeNull();
    expect(currentStage([item("later"), item("before", true), item("job")])).toBe("job");
  });

  it("다 끝났으면 마지막 단계", () => {
    expect(currentStage([item("before", true), item("study", true)])).toBe("study");
  });

  it("단계 순서대로, 빈 단계는 뺀다", () => {
    const groups = byStage([item("later"), item("before")]);
    expect(groups.map((g) => g.stage.key)).toEqual(["before", "later"]);
  });
});

describe("badges", () => {
  it("첫 완료·대화 3개·단계 완료·전체 완료", () => {
    const items = [item("job", true, "chat"), item("job", true, "chat"), item("study", false, "chat")];
    const got = Object.fromEntries(badges(items, {}).map((b) => [b.id, b.earned]));
    expect(got).toMatchObject({ first: true, talker: true, "stage:job": true, "stage:study": false, master: false });
  });

  it("정보통은 내 정보 80% 이상", () => {
    const full: Profile = {
      service_type: "conscript", service_years: 2, discharge_date: "2026-01", age: 23, region: "서울",
      branch: "육군", rank: "병장", specialty: "보병", education: "대학 재학", goals: ["취업"], desired_job: "IT",
      certificates: "", housing: "", injury: "",
    }; // prettier-ignore
    expect(profileCompleteness(full)).toBe(79);
    expect(badges([], full).find((b) => b.id === "profile")?.earned).toBe(false);
    const more = { ...full, certificates: "정보처리기사" };
    expect(profileCompleteness(more)).toBe(86);
    expect(badges([], more).find((b) => b.id === "profile")?.earned).toBe(true);
  });

  it("빈 목록·빈 배열은 채운 것으로 치지 않는다", () => {
    expect(profileCompleteness({ goals: [] })).toBe(0);
  });
});
