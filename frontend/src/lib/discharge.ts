export type DischargeMoment = "before" | "after";

/** 전역일이 일/월/년까지만 알려진 경우 해당 기간의 마지막 날을 기준으로 판단한다. */
export function dischargeMoment(value?: string, today = new Date()): DischargeMoment {
  if (!value) return "before";
  const match = value.match(/^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?$/);
  if (!match) return "before";
  const year = Number(match[1]);
  const month = Number(match[2] ?? 12);
  const day = match[3] ? Number(match[3]) : new Date(year, month, 0).getDate();
  const discharge = new Date(year, month - 1, day);
  if (discharge.getFullYear() !== year || discharge.getMonth() !== month - 1 || discharge.getDate() !== day) return "before";
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return discharge < startOfToday ? "after" : "before";
}
