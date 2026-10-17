// 브라우저 사본: 서버에 둔 내 정보·작전도를 이 브라우저에도 한 벌 둔다.
// 서버 기록이 사라졌으면 사본으로 다시 올리고, 서버에 연결이 안 되면 사본으로 보여 준다.

import { readStorage, writeStorage } from "./storage";
import type { JourneyItem, Profile } from "./types";

export const COPY_KEY = "jeonyeok.copy";

export interface LocalCopy {
  userId: string;
  saved_at: string;
  profile: Profile;
  items: JourneyItem[];
}

export function saveCopy(userId: string, profile: Profile, items: JourneyItem[], now = new Date()): void {
  const copy: LocalCopy = { userId, saved_at: now.toISOString(), profile, items };
  writeStorage(COPY_KEY, JSON.stringify(copy));
}

/** 이 익명 ID의 사본. 다른 ID의 것(이어 하기로 바뀐 경우)이나 깨진 값은 없는 것으로 본다 */
export function loadCopy(userId: string): LocalCopy | null {
  try {
    const copy = JSON.parse(readStorage(COPY_KEY) ?? "null") as LocalCopy | null;
    if (!copy || copy.userId !== userId || !Array.isArray(copy.items)) return null;
    return { ...copy, profile: copy.profile ?? {} };
  } catch {
    return null;
  }
}

export function isEmpty(profile: Profile, items: JourneyItem[]): boolean {
  return items.length === 0 && Object.keys(profile).length === 0;
}

/** 서버 기록이 비었는데 사본에는 기록이 있으면, 사본으로 되살려야 한다 */
export function shouldRestore(server: { profile: Profile; items: JourneyItem[] }, copy: LocalCopy | null): copy is LocalCopy {
  return copy !== null && isEmpty(server.profile, server.items) && !isEmpty(copy.profile, copy.items);
}
