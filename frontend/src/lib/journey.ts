// 전역 로드맵(여정): 단계, 진행률, 계급(레벨), 배지, 서버 저장.
// 할 일은 '내 정보'로 한 번에 만들거나(plan) 대화하며 하나씩 담긴다(chat).

import { requestJson } from "./api";
import { readStorage, writeStorage } from "./storage";
import type { JourneyItem, Profile, StageKey } from "./types";

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

export interface Level {
  rank: string;
  /** 다음 계급까지 남은 % (마지막이면 0) */
  next: number;
  line: string;
}

// 진행률에 따라 계급이 오른다. B급 감성으로.
const LEVELS: { at: number; rank: string; line: string }[] = [
  { at: 0, rank: "이병", line: "충성! 전역을 명받았습니다… 근데 이제 뭐 함?" },
  { at: 20, rank: "일병", line: "슬슬 감 잡는 중. 일병 정도는 됨 ㅇㅈ" },
  { at: 45, rank: "상병", line: "상병 꺾였다. 이제 좀 한다는 소리 들음" },
  { at: 75, rank: "병장", line: "말년 병장 폼 미쳤다. 거의 다 왔음" },
  { at: 100, rank: "민간인", line: "민간인 완성. 충성! (이제 진짜 끝)" },
];

export function progress(items: JourneyItem[]): { done: number; total: number; percent: number } {
  const done = items.filter((i) => i.done).length;
  return { done, total: items.length, percent: items.length ? Math.round((done / items.length) * 100) : 0 };
}

export function levelOf(percent: number): Level {
  const i = LEVELS.findLastIndex((l) => percent >= l.at);
  const now = LEVELS[i];
  const after = LEVELS[i + 1];
  return { rank: now.rank, line: now.line, next: after ? after.at - percent : 0 };
}

/** 지금 머무는 단계: 아직 남은 할 일이 있는 첫 단계 (다 끝났으면 마지막 단계) */
export function currentStage(items: JourneyItem[]): StageKey | null {
  if (!items.length) return null;
  const open = STAGES.find((s) => items.some((i) => i.stage === s.key && !i.done));
  return open?.key ?? [...STAGES].reverse().find((s) => items.some((i) => i.stage === s.key))!.key;
}

export function byStage(items: JourneyItem[]): { stage: Stage; items: JourneyItem[] }[] {
  return STAGES.map((stage) => ({ stage, items: items.filter((i) => i.stage === stage.key) })).filter(
    (g) => g.items.length,
  );
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
    earned: list.every((i) => i.done),
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
    { id: "master", name: "전역 마스터", emoji: "🏆", line: "모든 할 일 완료", earned: all.total > 0 && all.done === all.total },
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

export async function removeItem(userId: string, itemId: string): Promise<void> {
  await requestJson("DELETE", `journey/${enc(userId)}/items/${enc(itemId)}`, undefined, "빼지 못했어요.");
}

export async function saveProfile(userId: string, profile: Profile): Promise<Profile> {
  const res = await requestJson("PUT", `profile/${enc(userId)}`, profile, "내 정보를 저장하지 못했어요.");
  return (await res.json()).profile;
}

// ---------- 데모 모드 (서버 없이 이 브라우저에만) ----------

const DEMO_KEY = "jeonyeok.demo.journey";

function demoItem(stage: StageKey, title: string, action: string, source: string): JourneyItem {
  return {
    id: `demo:${title}`,
    stage,
    title,
    action,
    detail: "",
    sources: [{ type: "institution", title: source, url: "" }],
    origin: "plan",
    question: "",
    done: false,
    created_at: null,
    done_at: null,
  };
}

export const DEMO_JOURNEY: JourneyItem[] = [
  demoItem("before", "장병내일준비적금 만기 확인", "전역 전에 가입 은행 앱에서 만기일을 확인하세요", "국방부"),
  demoItem("right_after", "예비군 편성 확인", "병무청 누리집에서 편성 부대를 확인하세요", "병무청"),
  demoItem("job", "국민취업지원제도", "고용24에서 온라인으로 신청하세요", "고용24"),
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
