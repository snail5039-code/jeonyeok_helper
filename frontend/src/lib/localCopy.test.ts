import { beforeEach, describe, expect, it } from "vitest";

import { COPY_KEY, loadCopy, saveCopy, shouldRestore } from "./localCopy";
import type { JourneyItem } from "./types";

const item = { id: "a", title: "예비군 편성 확인", done: true } as JourneyItem;

// vitest 기본 환경(node)에는 localStorage가 없어 간단히 흉내 낸다
const store = new Map<string, string>();
globalThis.localStorage = {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
  removeItem: (k: string) => void store.delete(k),
  clear: () => store.clear(),
  key: () => null,
  length: 0,
} as Storage;

describe("브라우저 사본", () => {
  beforeEach(() => store.clear());

  it("같은 익명 ID의 사본만 읽는다", () => {
    saveCopy("me", { region: "부산" }, [item]);
    expect(loadCopy("me")?.items).toHaveLength(1);
    expect(loadCopy("someone-else")).toBeNull();
  });

  it("깨진 사본은 없는 것으로 본다", () => {
    store.set(COPY_KEY, "{broken");
    expect(loadCopy("me")).toBeNull();
  });

  it("서버가 비었고 사본에 기록이 있을 때만 되살린다", () => {
    saveCopy("me", { region: "부산" }, [item]);
    const copy = loadCopy("me");
    expect(shouldRestore({ profile: {}, items: [] }, copy)).toBe(true);
    // 서버에 기록이 있으면 서버가 기준
    expect(shouldRestore({ profile: { region: "서울" }, items: [] }, copy)).toBe(false);
    // 사본도 비었으면 되살릴 것이 없다
    saveCopy("me", {}, []);
    expect(shouldRestore({ profile: {}, items: [] }, loadCopy("me"))).toBe(false);
  });
});
