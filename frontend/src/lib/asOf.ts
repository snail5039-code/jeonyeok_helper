// 답변에 자료 기준일 표시: 언제 기준 자료로 답했는지 보이게 한다.

import type { AsOf } from "./types";

/** 법령 시행일: 20260820 → 2026.08.20 */
export function dateLabel(d: string): string {
  return d.replace(/^(\d{4})-?(\d{2})-?(\d{2})$/, "$1.$2.$3");
}

/** 답변 아래 한 줄. 알 수 있는 것이 없으면 빈 문자열 */
export function asOfText(asOf: AsOf | undefined): string {
  if (!asOf) return "";
  const parts = [];
  if (asOf.checked) parts.push(`법령 개정 확인 ${dateLabel(asOf.checked)}`);
  if (asOf.latest_enforced) parts.push(`인용한 법령 최근 시행 ${dateLabel(asOf.latest_enforced)}`);
  return parts.length ? `자료 기준 · ${parts.join(" · ")}` : "";
}
