import { describe, expect, it } from "vitest";

import { asOfText, dateLabel } from "./asOf";

describe("자료 기준일", () => {
  it("날짜를 읽기 쉽게", () => {
    expect(dateLabel("20260820")).toBe("2026.08.20");
    expect(dateLabel("2026-10-18")).toBe("2026.10.18");
    expect(dateLabel("2026")).toBe("2026");
  });

  it("확인일과 최근 시행일을 한 줄로", () => {
    expect(asOfText({ checked: "2026-10-18", latest_enforced: "20260820" })).toBe(
      "자료 기준 · 법령 개정 확인 2026.10.18 · 인용한 법령 최근 시행 2026.08.20",
    );
    expect(asOfText({ checked: null, latest_enforced: "20260101" })).toBe("자료 기준 · 인용한 법령 최근 시행 2026.01.01");
    expect(asOfText({ checked: null, latest_enforced: null })).toBe("");
    expect(asOfText(undefined)).toBe("");
  });
});
