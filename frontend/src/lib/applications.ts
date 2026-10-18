// 신청 서류 도우미: 제도마다 챙길 서류, 내 정보로 채운 신청 내용, 낼 곳 (서버 applications.py)

import { readStorage, writeStorage } from "./storage";
import type { Source } from "./types";

const enc = encodeURIComponent;

export interface ProgramSummary {
  id: string;
  title: string;
  short: string;
  summary: string;
  aliases: string[];
}

export interface KitOffice {
  name: string;
  address?: string;
  phone?: string;
  url?: string;
}

export interface Kit {
  id: string;
  title: string;
  short: string;
  summary: string;
  fit: { level: "ok" | "check" | "unlikely"; text: string };
  steps: string[];
  documents: { name: string; by: "me" | "office"; how: string }[];
  form: { label: string; value: string; hint: string; from_profile: boolean }[];
  submit: {
    office: string | null;
    where: string;
    ways: string[];
    online: { name: string; url: string } | null;
    phone: string;
    offices: KitOffice[];
  };
  deadline: { text: string; date: string | null };
  sources: Source[];
}

export async function fetchPrograms(): Promise<ProgramSummary[]> {
  const res = await fetch("/api/applications").catch(() => null);
  if (!res?.ok) return [];
  return (await res.json()).programs ?? [];
}

export async function fetchKit(programId: string, userId: string): Promise<Kit> {
  const query = userId ? `?user_id=${enc(userId)}` : "";
  const res = await fetch(`/api/applications/${enc(programId)}${query}`).catch(() => null);
  if (!res?.ok) throw new Error("서류 안내를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.");
  return res.json();
}

const squash = (s: string) => s.replace(/\s+/g, "");

/** 할 일 이름에 나온 제도 (띄어쓰기 무시, 가장 긴 이름이 맞은 것) */
export function programFor(title: string, programs: ProgramSummary[]): ProgramSummary | null {
  const said = squash(title);
  let best: [number, ProgramSummary] | null = null;
  for (const p of programs) {
    for (const alias of p.aliases) {
      if (said.includes(squash(alias)) && (!best || alias.length > best[0])) best = [alias.length, p];
    }
  }
  return best?.[1] ?? null;
}

/** 신청 내용을 신청서에 옮겨 적기 좋게 한 덩어리 글로 */
export function formText(kit: Kit): string {
  const lines = kit.form.map((f) => `${f.label}: ${f.value || `(${f.hint || "직접 적기"})`}`);
  return [`[${kit.title} 신청 준비]`, ...lines].join("\n");
}

// 챙긴 서류 체크는 이 브라우저에만 둔다 (서버에 보낼 필요가 없는 메모)
const checkedKey = (userId: string, programId: string) => `jeonyeok.kit.${userId || "guest"}.${programId}`;

export function loadChecked(userId: string, programId: string): string[] {
  try {
    const v = JSON.parse(readStorage(checkedKey(userId, programId)) ?? "[]");
    return Array.isArray(v) ? v.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export function saveChecked(userId: string, programId: string, names: string[]): void {
  writeStorage(checkedKey(userId, programId), JSON.stringify(names));
}
