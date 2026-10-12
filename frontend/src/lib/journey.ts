// 전역 로드맵(여정): 단계, 진행률, 계급(레벨), 배지, 서버 저장.
// 할 일은 '내 정보'로 한 번에 만들거나(plan) 대화하며 하나씩 담긴다(chat).

import { requestJson } from "./api";
import { readStorage, writeStorage } from "./storage";
import type { JourneyItem, Profile, StageKey, Suggestion } from "./types";

export interface Stage {
  key: StageKey;
  title: string;
  emoji: string;
  /** 단계를 다 끝내면 받는 배지 */
  badge: { name: string; emoji: string; line: string };
}

export const STAGES: Stage[] = [
  { key: "before", title: "전역 전", emoji: "🎒", badge: { name: "짐 싸기 완료", emoji: "🎒", line: "말년엔 원래 할 게 많음" } },
  { key: "right_after", title: "전역 직후", emoji: "🪖", badge: { name: "예비군 입문", emoji: "🪖", line: "축하합니다 예비군 1년 차" } },
  { key: "job", title: "취업·창업", emoji: "💼", badge: { name: "취준 생존자", emoji: "💼", line: "자소서 쓰다 눈물 한 방울" } },
  { key: "study", title: "학업", emoji: "📚", badge: { name: "복학생 각성", emoji: "📚", line: "과탑은 몰라도 출석은 1등" } },
  { key: "life", title: "주거·생활", emoji: "🏠", badge: { name: "자취 만렙", emoji: "🏠", line: "월세 앞에 장사 없다" } },
  { key: "later", title: "나중에", emoji: "⏳", badge: { name: "미래의 나에게", emoji: "⏳", line: "연금은 미래의 내가 고마워함" } },
]; // prettier-ignore

export const STAGE_BY_KEY = Object.fromEntries(STAGES.map((s) => [s.key, s])) as Record<StageKey, Stage>;

// ---------- 진행률과 계급 ----------
// 계급은 끝낸 할 일 '개수'로 오른다 (할 일이 늘어도 내려가지 않게).
// 민간인(완주)은 핵심 할 일을 모두 끝냈을 때. 핵심 표시가 없는 옛 할 일만 있으면 전부 끝냈을 때.

export interface Level {
  rank: string;
  /** 다음 계급까지 남은 할 일 수 (민간인이면 0) */
  next: number;
  line: string;
  /** 핵심 할 일을 다 끝내 로드맵을 완주했는지 */
  finished: boolean;
}

const LEVELS: { at: number; rank: string; line: string }[] = [
  { at: 0, rank: "이병", line: "충성! 전역을 명받았습니다… 근데 이제 뭐 함?" },
  { at: 1, rank: "일병", line: "첫 단추 끼움. 일병 정도는 됨 ㅇㅈ" },
  { at: 4, rank: "상병", line: "상병 꺾였다. 이제 좀 한다는 소리 들음" },
  { at: 8, rank: "병장", line: "말년 병장 폼 미쳤다. 핵심만 끝내면 민간인!" },
];
const CIVILIAN = { rank: "민간인", line: "민간인 완성. 충성! (이제 진짜 끝)" };

/** 완주 기준이 되는 할 일: 핵심 표시가 있으면 핵심만, 없으면 전부 */
export function coreItems(items: JourneyItem[]): JourneyItem[] {
  const core = items.filter((i) => i.core);
  return core.length ? core : items;
}

export function progress(items: JourneyItem[]): {
  done: number;
  total: number;
  coreDone: number;
  coreTotal: number;
  /** 완주까지 (핵심 기준) */
  percent: number;
} {
  const core = coreItems(items);
  const coreDone = core.filter((i) => i.done).length;
  return {
    done: items.filter((i) => i.done).length,
    total: items.length,
    coreDone,
    coreTotal: core.length,
    percent: core.length ? Math.round((coreDone / core.length) * 100) : 0,
  };
}

export function levelOf(items: JourneyItem[]): Level {
  const p = progress(items);
  if (p.coreTotal > 0 && p.coreDone === p.coreTotal) return { ...CIVILIAN, next: 0, finished: true };
  const i = LEVELS.findLastIndex((l) => p.done >= l.at);
  const after = LEVELS[i + 1];
  return { rank: LEVELS[i].rank, line: LEVELS[i].line, next: after ? after.at - p.done : 0, finished: false };
}

/** 단계 완료: 그 단계의 핵심 할 일(없으면 전부)을 끝냈을 때 */
export function stageDone(list: JourneyItem[]): boolean {
  return list.length > 0 && coreItems(list).every((i) => i.done);
}

/** 지금 머무는 단계: 아직 안 끝난 첫 단계 (다 끝났으면 마지막 단계) */
export function currentStage(items: JourneyItem[]): StageKey | null {
  if (!items.length) return null;
  const open = STAGES.find((s) => {
    const list = items.filter((i) => i.stage === s.key);
    return list.length > 0 && !stageDone(list);
  });
  return open?.key ?? [...STAGES].reverse().find((s) => items.some((i) => i.stage === s.key))!.key;
}

export function byStage(items: JourneyItem[]): { stage: Stage; items: JourneyItem[] }[] {
  return STAGES.map((stage) => ({ stage, items: sortItems(items.filter((i) => i.stage === stage.key)) })).filter(
    (g) => g.items.length,
  );
}

/** 단계 안에서: 안 끝난 핵심 → 기한 빠른 순 → 나머지, 끝낸 것은 아래로 */
export function sortItems(items: JourneyItem[]): JourneyItem[] {
  const rank = (i: JourneyItem) => [i.done ? 1 : 0, i.core ? 0 : 1, i.due_months ?? 999] as const;
  return [...items].sort((a, b) => {
    const [x, y] = [rank(a), rank(b)];
    return x[0] - y[0] || x[1] - y[1] || x[2] - y[2];
  });
}

/** 다음에 권할 할 일 (백엔드 guide.next_item과 같은 규칙) */
export function nextItem(items: JourneyItem[]): JourneyItem | null {
  const order = Object.fromEntries(STAGES.map((s, i) => [s.key, i]));
  const open = items.filter((i) => !i.done);
  if (!open.length) return null;
  return open.reduce((best, i) => {
    const key = (x: JourneyItem) => [x.core ? 0 : 1, x.due_months == null ? 1 : 0, x.due_months ?? 0, order[x.stage]];
    const [a, b] = [key(i), key(best)];
    for (let k = 0; k < a.length; k++) if (a[k] !== b[k]) return a[k] < b[k] ? i : best;
    return best;
  });
}

// ---------- 기한 ----------

/** 전역일(YYYY-MM 또는 YYYY)에 개월 수를 더한 마감일 (그 달 마지막 날) */
export function dueDate(item: Pick<JourneyItem, "due_months">, dischargeDate?: string): Date | null {
  if (item.due_months == null || !dischargeDate) return null;
  const m = dischargeDate.match(/^(\d{4})(?:-(\d{1,2}))?/);
  if (!m) return null;
  const month = (m[2] ? Number(m[2]) : 12) - 1 + item.due_months;
  return new Date(Number(m[1]), month + 1, 0);
}

/** 오늘부터 마감일까지 남은 날 (지났으면 음수) */
export function daysLeft(due: Date, today = new Date()): number {
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((due.getTime() - start.getTime()) / 86_400_000);
}

export function ddayLabel(days: number): string {
  return days > 0 ? `D-${days.toLocaleString()}` : days === 0 ? "D-DAY" : `${(-days).toLocaleString()}일 지남`;
}

// ---------- 배지 ----------

export interface Badge {
  id: string;
  name: string;
  emoji: string;
  line: string;
  earned: boolean;
}

export function badges(items: JourneyItem[], profile: Profile): Badge[] {
  const stageBadges = byStage(items).map(({ stage, items: list }) => ({
    id: `stage:${stage.key}`,
    ...stage.badge,
    earned: stageDone(list),
  }));
  const all = progress(items);
  return [
    { id: "first", name: "첫 단추", emoji: "👔", line: "시작이 반이라던데 진짜임?", earned: all.done > 0 },
    { id: "profile", name: "정보통", emoji: "🗂️", line: "내 정보 80% 이상 입력", earned: profileCompleteness(profile) >= 80 },
    {
      id: "talker",
      name: "질문 폭격기",
      emoji: "💬",
      line: "대화로 할 일 3개 이상 담기",
      earned: items.filter((i) => i.origin === "chat").length >= 3,
    },
    ...stageBadges,
    { id: "master", name: "전역 마스터", emoji: "🏆", line: "핵심 할 일 모두 완료", earned: levelOf(items).finished },
  ];
}

// ---------- 내 정보 ----------

// 채울수록 검색이 정확해지는 항목 (메모 제외)
const PROFILE_FIELDS: (keyof Profile)[] = [
  "service_type", "service_years", "discharge_date", "age", "region", "branch", "rank",
  "specialty", "education", "goals", "desired_job", "certificates", "housing", "injury",
]; // prettier-ignore

export function profileCompleteness(p: Profile): number {
  const filled = PROFILE_FIELDS.filter((k) => {
    const v = p[k];
    return Array.isArray(v) ? v.length > 0 : v !== undefined && v !== null && v !== "";
  }).length;
  return Math.round((filled / PROFILE_FIELDS.length) * 100);
}

// ---------- 서버 ----------

const enc = encodeURIComponent;

export async function fetchJourney(userId: string): Promise<JourneyItem[]> {
  const res = await fetch(`/api/journey/${enc(userId)}`);
  if (!res.ok) throw new Error("로드맵을 불러오지 못했어요.");
  return (await res.json()).items;
}

export async function generateJourney(userId: string): Promise<{ intro: string; added: number; items: JourneyItem[] }> {
  const res = await requestJson("POST", `journey/${enc(userId)}/generate`, undefined, "로드맵을 만들지 못했어요.");
  return res.json();
}

export async function markDone(userId: string, itemId: string, done: boolean): Promise<JourneyItem> {
  const res = await requestJson("PATCH", `journey/${enc(userId)}/items/${enc(itemId)}`, { done }, "저장하지 못했어요.");
  return res.json();
}

export async function addItems(userId: string, items: Suggestion[], question: string): Promise<JourneyItem[]> {
  const res = await requestJson("POST", `journey/${enc(userId)}/items`, { items, question }, "로드맵에 담지 못했어요.");
  return (await res.json()).added;
}

export async function removeItem(userId: string, itemId: string): Promise<void> {
  await requestJson("DELETE", `journey/${enc(userId)}/items/${enc(itemId)}`, undefined, "빼지 못했어요.");
}

export async function saveProfile(userId: string, profile: Profile): Promise<Profile> {
  const res = await requestJson("PUT", `profile/${enc(userId)}`, profile, "내 정보를 저장하지 못했어요.");
  return (await res.json()).profile;
}

// ---------- 데모 모드 (서버 없이 이 브라우저에만) ----------

const DEMO_KEY = "jeonyeok.demo.journey";

function demoItem(
  stage: StageKey,
  title: string,
  action: string,
  source: string,
  extra: Partial<JourneyItem> = {},
): JourneyItem {
  return {
    id: `demo:${title}`,
    stage,
    title,
    action,
    detail: "",
    sources: [{ type: "institution", title: source, url: "" }],
    origin: "plan",
    question: "",
    core: false,
    deadline: "",
    due_months: null,
    done: false,
    created_at: null,
    done_at: null,
    ...extra,
  };
}

export const DEMO_JOURNEY: JourneyItem[] = [
  demoItem("before", "장병내일준비적금 만기 확인", "전역 전에 가입 은행 앱에서 만기일을 확인하세요", "국방부", { core: true }),
  demoItem("right_after", "예비군 편성 확인", "병무청 누리집에서 편성 부대를 확인하세요", "병무청", { core: true }),
  demoItem("job", "국민취업지원제도", "고용24에서 온라인으로 신청하세요", "고용24", { core: true }),
  demoItem("study", "국가장학금 신청", "복학 학기 전에 한국장학재단에서 신청하세요", "한국장학재단"),
  demoItem("later", "군복무 크레딧", "따로 신청하지 않아도 노령연금 받을 때 반영돼요", "국민연금공단"),
];

export function loadDemoJourney(): JourneyItem[] {
  try {
    const saved = readStorage(DEMO_KEY);
    return saved ? JSON.parse(saved) : DEMO_JOURNEY;
  } catch {
    return DEMO_JOURNEY;
  }
}

export function saveDemoJourney(items: JourneyItem[]): void {
  writeStorage(DEMO_KEY, JSON.stringify(items));
}
