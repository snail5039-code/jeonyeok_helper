// 내 기록 파일: 로그인이 없으니 내 정보와 작전도를 파일 하나로 내려받아 두고,
// 다른 브라우저·기기에서 그 파일로 그대로 되살린다.

import { requestJson } from "./api";
import type { JourneyItem, Profile } from "./types";

export const BACKUP_APP = "jeonyeok_helper";
export const BACKUP_VERSION = 1;

export interface Backup {
  app: typeof BACKUP_APP;
  version: typeof BACKUP_VERSION;
  saved_at: string;
  profile: Profile;
  items: JourneyItem[];
}

const enc = encodeURIComponent;

export function makeBackup(profile: Profile, items: JourneyItem[], now = new Date()): Backup {
  return { app: BACKUP_APP, version: BACKUP_VERSION, saved_at: now.toISOString(), profile, items };
}

/** 파일 내용을 읽어 기록인지 확인한다. 다른 파일이면 사람이 읽을 수 있는 안내로 예외를 던진다. */
export function parseBackup(text: string): Backup {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error("전역도우미 기록 파일이 아니에요.");
  }
  const d = data as Partial<Backup>;
  if (!d || d.app !== BACKUP_APP) throw new Error("전역도우미 기록 파일이 아니에요.");
  if (d.version !== BACKUP_VERSION) throw new Error("이 버전에서 읽을 수 없는 기록 파일이에요.");
  return {
    app: BACKUP_APP,
    version: BACKUP_VERSION,
    saved_at: typeof d.saved_at === "string" ? d.saved_at : "",
    profile: d.profile && typeof d.profile === "object" ? d.profile : {},
    items: Array.isArray(d.items) ? d.items : [],
  };
}

export function backupFileName(now = new Date()): string {
  const day = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  return `전역도우미_내기록_${day}.json`;
}

/** 서버에 저장된 내 기록 (서버가 기준. 화면 상태보다 정확하다) */
export async function fetchBackup(userId: string): Promise<Backup> {
  const res = await fetch(`/api/backup/${enc(userId)}`);
  if (!res.ok) throw new Error("기록을 불러오지 못했어요.");
  return parseBackup(await res.text());
}

/** 기록 파일 내용으로 이 브라우저의 기록을 바꾼다. 서버가 저장한 결과를 돌려준다. */
export async function restoreBackup(userId: string, backup: Backup): Promise<{ profile: Profile; items: JourneyItem[] }> {
  const body = {
    app: BACKUP_APP,
    version: BACKUP_VERSION,
    profile: backup.profile,
    items: backup.items.map((i) => ({
      stage: i.stage,
      title: i.title,
      action: i.action ?? "",
      detail: i.detail ?? "",
      sources: i.sources ?? [],
      core: Boolean(i.core),
      deadline: i.deadline ?? "",
      due_months: i.due_months ?? null,
      done: Boolean(i.done),
      origin: i.origin === "plan" ? "plan" : "chat",
      question: i.question ?? "",
    })),
  };
  const res = await requestJson("PUT", `backup/${enc(userId)}`, body, "기록을 되살리지 못했어요.");
  return res.json();
}

/** 브라우저에서 파일로 내려받게 한다 */
export function downloadBackup(backup: Backup): void {
  const blob = new Blob([JSON.stringify(backup, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = backupFileName(new Date(backup.saved_at || Date.now()));
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
