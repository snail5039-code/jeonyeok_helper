import { describe, expect, it } from "vitest";

import { greeting } from "./guide";
import {
  badges,
  byStage,
  currentStage,
  daysLeft,
  ddayLabel,
  dueDate,
  levelOf,
  toCivilian,
  nextItem,
  profileCompleteness,
  progress,
  stageDone,
} from "./journey";
import type { JourneyItem, Profile, StageKey } from "./types";

let n = 0;
const item = (stage: StageKey, done = false, extra: Partial<JourneyItem> = {}): JourneyItem => ({
  id: `i${++n}`,
  stage,
  title: `할 일 ${n}`,
  action: "신청하세요",
  detail: "",
  sources: [],
  origin: "plan",
  question: "",
  core: false,
  deadline: "",
  due_months: null,
  done,
  created_at: null,
  done_at: null,
  ...extra,
});
const many = (count: number, done: boolean) => Array.from({ length: count }, () => item("job", done));

describe("계급: 끝낸 개수로 오르고, 핵심을 다 끝내면 민간인", () => {
  it("빈 로드맵은 이병", () => {
    expect(levelOf([])).toMatchObject({ rank: "이병", next: 1, finished: false });
  });

  it("끝낸 개수에 따라 오른다", () => {
    expect(levelOf([...many(1, true), ...many(3, false)]).rank).toBe("일병");
    expect(levelOf([...many(4, true), item("job", false, { core: true })]).rank).toBe("상병");
    expect(levelOf([...many(8, true), item("job", false, { core: true })]).rank).toBe("병장");
    expect(levelOf([...many(2, true), ...many(5, false)]).next).toBe(2);
  });

  it("할 일이 늘어도 계급이 내려가지 않는다", () => {
    const before = [...many(4, true), item("job", false, { core: true })];
    const after = [...before, ...many(10, false)];
    expect(levelOf(after).rank).toBe(levelOf(before).rank);
  });

  it("핵심을 다 끝내고 병장 수준(8개)까지 끝내야 민간인 (보너스 할 일이 남아도)", () => {
    const core = [1, 2, 3].map(() => item("job", true, { core: true }));
    const bonus = (n: number, done: boolean) => Array.from({ length: n }, () => item("life", done));
    // 핵심 3개만 끝낸 직후: 일병~병장을 건너뛰고 민간인이 되면 안 된다
    expect(levelOf([...core, ...bonus(8, false)])).toMatchObject({ rank: "일병", finished: false });
    expect(toCivilian([...core, ...bonus(8, false)])).toBe(5);
    const all = [...core, ...bonus(5, true), ...bonus(3, false)];
    expect(levelOf(all)).toMatchObject({ rank: "민간인", finished: true, next: 0 });
    expect(progress(all)).toMatchObject({ done: 8, total: 11, coreDone: 3, coreTotal: 3, percent: 100 });
  });

  it("핵심 표시가 없는 옛 할 일은 전부 끝내야 완주", () => {
    expect(levelOf([item("job", true), item("job")]).finished).toBe(false);
    expect(levelOf(many(3, true)).finished).toBe(true); // 3개뿐이면 전부 끝낸 것
  });

  it("핵심 임무가 적게 담겼을 때는 끝내도 민간인이 되지 않는다", () => {
    // 1개 담고 끝낸 직후 민간인이 되던 버그
    const one = [item("job", true, { core: true })];
    expect(levelOf(one)).toMatchObject({ rank: "일병", finished: false });
    expect(levelOf([...one, item("job", true, { core: true })]).finished).toBe(false);
    expect(levelOf([...one, ...many(2, true).map((i) => ({ ...i, core: true }))]).finished).toBe(true);
  });
});

describe("단계와 다음 할 일", () => {
  it("단계는 핵심 할 일만 끝내면 완료", () => {
    expect(stageDone([item("job", true, { core: true }), item("job")])).toBe(true);
    expect(stageDone([item("job", false, { core: true }), item("job", true)])).toBe(false);
  });

  it("지금 단계는 안 끝난 첫 단계", () => {
    expect(currentStage([])).toBeNull();
    const items = [item("before", true, { core: true }), item("before"), item("job", false, { core: true })];
    expect(currentStage(items)).toBe("job");
  });

  it("단계 순서대로, 안에서는 안 끝난 핵심·기한 빠른 순", () => {
    const late = item("job", false, { core: true, due_months: 36 });
    const soon = item("job", false, { core: true, due_months: 3 });
    const plain = item("job");
    const done = item("job", true, { core: true });
    const groups = byStage([item("later"), done, plain, late, soon]);
    expect(groups.map((g) => g.stage.key)).toEqual(["job", "later"]);
    expect(groups[0].items.map((i) => i.id)).toEqual([soon.id, late.id, plain.id, done.id]);
  });

  it("다음 할 일: 핵심 → 기한 빠른 것 → 단계 순 (백엔드와 같은 규칙)", () => {
    const before = item("before");
    const core = item("job", false, { core: true });
    const soon = item("life", false, { core: true, due_months: 2 });
    expect(nextItem([before, core, soon])?.id).toBe(soon.id);
    expect(nextItem([before, core])?.id).toBe(core.id);
    expect(nextItem([item("job", true)])).toBeNull();
  });
});

describe("기한 D-day", () => {
  it("전역일 + 개월 수의 그 달 마지막 날", () => {
    const due = dueDate({ due_months: 36 }, "2026-03")!;
    expect([due.getFullYear(), due.getMonth() + 1, due.getDate()]).toEqual([2029, 3, 31]);
    expect(dueDate({ due_months: 6 }, "2025")!.getMonth() + 1).toBe(6); // 월을 모르면 그해 12월 기준
    expect(dueDate({ due_months: null }, "2026-03")).toBeNull();
    expect(dueDate({ due_months: 12 }, undefined)).toBeNull();
  });

  it("남은 날과 표시", () => {
    expect(daysLeft(new Date(2026, 9, 20), new Date(2026, 9, 13, 15))).toBe(7);
    expect(ddayLabel(7)).toBe("D-7");
    expect(ddayLabel(0)).toBe("D-DAY");
    expect(ddayLabel(-3)).toBe("3일 지남");
  });
});

describe("badges", () => {
  it("첫 완료·대화 3개·단계 완료·완주", () => {
    const items = [
      item("job", true, { origin: "chat", core: true }),
      item("job", false, { origin: "chat" }),
      item("study", false, { origin: "chat", core: true }),
    ];
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
    expect(badges([], { ...full, certificates: "정보처리기사" }).find((b) => b.id === "profile")?.earned).toBe(true);
    expect(profileCompleteness({ goals: [] })).toBe(0);
  });
});

describe("첫 화면 길잡이 인사", () => {
  it("처음이면 복무 형태부터 묻는다", () => {
    const g = greeting({}, []);
    expect(g.replies[0].message).toBe("의무복무 병사로 전역했어요");
  });

  it("로드맵이 없으면 만들자고 한다", () => {
    expect(greeting({ service_type: "conscript" }, []).replies[0].message).toBe("내 로드맵 만들어 줘");
  });

  it("로드맵이 있으면 다음 할 일과 기한, 했어요 버튼", () => {
    const next = item("job", false, { core: true, title: "취업지원 신청", deadline: "전역 후 3년 이내", due_months: 36 });
    const g = greeting({ service_type: "conscript", discharge_date: "2026-03" }, [next, item("life")]);
    expect(g.say).toContain("'취업지원 신청'");
    expect(g.say).toContain("전역 후 3년 이내");
    expect(g.replies[0].action).toEqual({ type: "done", item_id: next.id });
    expect(g.replies.at(-1)?.open).toBe("journey");
  });

  it("완주하면 축하", () => {
    const done = [1, 2, 3].map(() => item("job", true, { core: true }));
    expect(greeting({ service_type: "conscript" }, done).say).toContain("민간인 완성");
  });

  it("담은 임무를 다 끝냈지만 민간인은 아직이면 임무를 더 찾자고 한다 (화면이 죽던 경우)", () => {
    const g = greeting({ service_type: "short_term_officer" }, [item("right_after", true)]);
    expect(g.say).toContain("다 끝냈어요");
    expect(g.replies[0].message).toBe("내 로드맵 만들어 줘");
    expect(g.replies.at(-1)?.open).toBe("journey");
  });
});
