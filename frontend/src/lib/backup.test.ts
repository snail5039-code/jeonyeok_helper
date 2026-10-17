import { describe, expect, it } from "vitest";

import { backupFileName, makeBackup, parseBackup } from "./backup";
import type { JourneyItem } from "./types";

const item: JourneyItem = {
  id: "a",
  stage: "job",
  title: "국민취업지원제도",
  action: "고용24에서 신청",
  detail: "",
  sources: [],
  origin: "plan",
  question: "",
  core: true,
  deadline: "",
  due_months: 12,
  done: true,
  created_at: null,
  done_at: null,
};

describe("내 기록 파일", () => {
  it("만든 기록을 다시 읽으면 그대로다", () => {
    const backup = makeBackup({ service_type: "conscript", region: "부산" }, [item], new Date("2026-10-18T09:00:00Z"));
    const read = parseBackup(JSON.stringify(backup));
    expect(read.profile).toEqual({ service_type: "conscript", region: "부산" });
    expect(read.items[0]).toMatchObject({ title: "국민취업지원제도", done: true, core: true });
    expect(read.saved_at).toBe("2026-10-18T09:00:00.000Z");
  });

  it("다른 파일이나 깨진 파일은 알아들을 수 있게 거절한다", () => {
    expect(() => parseBackup("not json")).toThrow("전역도우미 기록 파일이 아니에요.");
    expect(() => parseBackup(JSON.stringify({ app: "other" }))).toThrow("전역도우미 기록 파일이 아니에요.");
    expect(() => parseBackup(JSON.stringify({ app: "jeonyeok_helper", version: 9 }))).toThrow("버전");
  });

  it("빠진 칸은 빈 값으로 채운다", () => {
    const read = parseBackup(JSON.stringify({ app: "jeonyeok_helper", version: 1 }));
    expect(read.profile).toEqual({});
    expect(read.items).toEqual([]);
  });

  it("파일 이름에 저장한 날짜가 들어간다", () => {
    expect(backupFileName(new Date(2026, 9, 18))).toBe("전역도우미_내기록_2026-10-18.json");
  });
});
