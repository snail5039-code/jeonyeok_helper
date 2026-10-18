import { describe, expect, it } from "vitest";

import { calendarEntries, escapeText, foldLine, icsFileName, makeIcs } from "./calendar";
import type { JourneyItem } from "./types";

const item = (over: Partial<JourneyItem> = {}): JourneyItem => ({
  id: "a1",
  stage: "job",
  title: "전직지원금 신청",
  action: "관할 보훈청에 신청",
  detail: "",
  sources: [{ type: "regulation", title: "제대군인법", url: "https://www.law.go.kr/x" }],
  origin: "plan",
  question: "",
  core: true,
  deadline: "전역 후 6개월 이내",
  due_months: 6,
  done: false,
  created_at: null,
  done_at: null,
  ...over,
});

const today = new Date(2026, 9, 18);
const bytes = (s: string) => new TextEncoder().encode(s).length;

describe("캘린더에 넣을 할 일", () => {
  it("전역일로 마감일을 셀 수 있고 안 끝난 것만, 마감 빠른 순", () => {
    const entries = calendarEntries(
      [
        item({ id: "late", due_months: 36 }),
        item({ id: "soon" }),
        item({ id: "done", done: true }),
        item({ id: "nodue", due_months: null }),
        item({ id: "nodeadline", deadline: "" }),
      ],
      "2026-09",
      today,
    );
    expect(entries.map((e) => e.item.id)).toEqual(["soon", "late"]);
    // 2026-09 전역 + 6개월 → 2027-03 마지막 날
    expect(entries[0].due).toEqual(new Date(2027, 2, 31));
  });

  it("전역일을 모르거나 이미 지난 기한은 넣지 않는다", () => {
    expect(calendarEntries([item()], undefined, today)).toEqual([]);
    expect(calendarEntries([item()], "2020-01", today)).toEqual([]);
  });
});

describe(".ics 파일", () => {
  const ics = makeIcs(calendarEntries([item()], "2026-09", today), new Date(Date.UTC(2026, 9, 18, 0, 0, 0)));
  const unfolded = ics.replace(/\r\n /g, "");

  it("달력 하나에 하루 종일 일정 하나", () => {
    expect(ics.startsWith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:")).toBe(true);
    expect(ics.endsWith("END:VCALENDAR\r\n")).toBe(true);
    expect(unfolded).toContain("DTSTART;VALUE=DATE:20270331\r\n");
    expect(unfolded).toContain("DTEND;VALUE=DATE:20270401\r\n");
    expect(unfolded).toContain("UID:a1@jeonyeok-helper\r\n");
    expect(unfolded).toContain("DTSTAMP:20261018T000000Z\r\n");
    expect(unfolded).toContain("SUMMARY:[마감] 전직지원금 신청\r\n");
  });

  it("마감 7일 전·1일 전 알림이 붙는다", () => {
    expect(unfolded.match(/BEGIN:VALARM/g)).toHaveLength(2);
    expect(unfolded).toContain("TRIGGER:-P6DT15H\r\n");
    expect(unfolded).toContain("TRIGGER:-PT15H\r\n");
    expect(unfolded.match(/ACTION:DISPLAY/g)).toHaveLength(2);
  });

  it("줄 끝은 모두 CRLF이고 한 줄은 75바이트를 넘지 않는다", () => {
    expect(ics.replace(/\r\n/g, "")).not.toMatch(/[\r\n]/);
    for (const line of ics.split("\r\n")) expect(bytes(line)).toBeLessThanOrEqual(75);
  });

  it("설명에 할 일, 기한, 출처 링크가 들어간다", () => {
    expect(unfolded).toContain("관할 보훈청에 신청\\n기한: 전역 후 6개월 이내");
    expect(unfolded).toContain("제대군인법: https://www.law.go.kr/x");
  });
});

describe("형식 규칙", () => {
  it("특수 문자를 이스케이프한다", () => {
    expect(escapeText("a,b;c\\d\ne")).toBe("a\\,b\\;c\\\\d\\ne");
  });

  it("한글을 글자 중간에서 자르지 않고 접는다", () => {
    const line = `SUMMARY:${"가".repeat(60)}`;
    const folded = foldLine(line);
    const parts = folded.split("\r\n");
    expect(parts.length).toBeGreaterThan(1);
    expect(parts.slice(1).every((p) => p.startsWith(" "))).toBe(true);
    for (const p of parts) expect(bytes(p)).toBeLessThanOrEqual(75);
    expect(folded.replace(/\r\n /g, "")).toBe(line);
  });

  it("파일 이름: 하나면 할 일 이름, 여럿이면 전체", () => {
    const one = calendarEntries([item()], "2026-09", today);
    expect(icsFileName(one)).toBe("전역도우미_기한_전직지원금_신청.ics");
    expect(icsFileName([...one, ...one])).toBe("전역도우미_기한_전체.ics");
  });
});
