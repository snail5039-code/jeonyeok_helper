// 캘린더에 넣기: 기한이 있는 할 일을 .ics(iCalendar, RFC 5545) 파일로 만들어
// 구글·애플·아웃룩 캘린더에 넣는다. 계정 없이 기한 알림을 받는 방법이다.

import { daysLeft, dueDate } from "./journey";
import type { JourneyItem } from "./types";

/** 알림: 마감 7일 전, 1일 전 오전 9시 (하루 종일 일정은 그날 0시 기준이라 -15시간 = 전날 9시) */
export const ALARMS = [
  { trigger: "-P6DT15H", label: "7일 전" },
  { trigger: "-PT15H", label: "1일 전" },
] as const;

export interface CalendarEntry {
  item: JourneyItem;
  due: Date;
}

/** 캘린더에 넣을 수 있는 할 일: 안 끝났고, 전역일로 마감일을 셀 수 있고, 아직 안 지난 것 */
export function calendarEntries(items: JourneyItem[], dischargeDate?: string, today = new Date()): CalendarEntry[] {
  return items
    .filter((item) => !item.done && item.deadline)
    .map((item) => ({ item, due: dueDate(item, dischargeDate) }))
    .filter((e): e is CalendarEntry => e.due !== null && daysLeft(e.due, today) >= 0)
    .sort((a, b) => a.due.getTime() - b.due.getTime());
}

/** 글자 값 안의 \ ; , 줄바꿈을 이스케이프한다 */
export function escapeText(text: string): string {
  return text.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
}

const encoder = new TextEncoder();

/** 한 줄이 75바이트를 넘으면 접는다. 한글은 3바이트라 글자 수가 아니라 바이트로 세고, 글자 중간에서 자르지 않는다 */
export function foldLine(line: string): string {
  const parts: string[] = [];
  let current = "";
  let bytes = 0;
  for (const ch of line) {
    const size = encoder.encode(ch).length;
    // 이어지는 줄은 앞에 공백 한 칸이 붙으므로 74바이트까지
    const limit = parts.length ? 74 : 75;
    if (bytes + size > limit) {
      parts.push(current);
      current = "";
      bytes = 0;
    }
    current += ch;
    bytes += size;
  }
  parts.push(current);
  return parts.join("\r\n ");
}

const pad = (n: number) => String(n).padStart(2, "0");
const dateValue = (d: Date) => `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`;
const stampValue = (d: Date) =>
  `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`;

function event({ item, due }: CalendarEntry, now: Date): string[] {
  const next = new Date(due.getFullYear(), due.getMonth(), due.getDate() + 1);
  const description = [
    item.action,
    `기한: ${item.deadline} (전역일 기준으로 계산한 마감일이에요)`,
    ...item.sources.filter((s) => s.url).map((s) => `${s.title}: ${s.url}`),
    "정확한 자격과 기한은 소관 기관에 꼭 확인하세요. - 전역도우미",
  ]
    .filter(Boolean)
    .join("\n");
  const summary = `[마감] ${item.title}`;
  return [
    "BEGIN:VEVENT",
    `UID:${item.id}@jeonyeok-helper`,
    `DTSTAMP:${stampValue(now)}`,
    `DTSTART;VALUE=DATE:${dateValue(due)}`,
    `DTEND;VALUE=DATE:${dateValue(next)}`,
    `SUMMARY:${escapeText(summary)}`,
    `DESCRIPTION:${escapeText(description)}`,
    "TRANSP:TRANSPARENT",
    ...ALARMS.flatMap((a) => [
      "BEGIN:VALARM",
      "ACTION:DISPLAY",
      `DESCRIPTION:${escapeText(`${a.label}: ${summary}`)}`,
      `TRIGGER:${a.trigger}`,
      "END:VALARM",
    ]),
    "END:VEVENT",
  ];
}

/** .ics 파일 내용 (줄 끝은 CRLF) */
export function makeIcs(entries: CalendarEntry[], now = new Date()): string {
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//jeonyeok-helper//ko",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "X-WR-CALNAME:전역도우미 기한",
    ...entries.flatMap((e) => event(e, now)),
    "END:VCALENDAR",
  ];
  return lines.map(foldLine).join("\r\n") + "\r\n";
}

export function icsFileName(entries: CalendarEntry[]): string {
  if (entries.length === 1) {
    const title = entries[0].item.title.replace(/[\\/:*?"<>|\s]+/g, "_").slice(0, 40);
    return `전역도우미_기한_${title}.ics`;
  }
  return "전역도우미_기한_전체.ics";
}

/** 브라우저에서 .ics 파일로 내려받게 한다. 휴대폰에서는 열면 캘린더 앱이 추가 화면을 띄운다 */
export function downloadIcs(entries: CalendarEntry[]): void {
  const blob = new Blob([makeIcs(entries)], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = icsFileName(entries);
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
