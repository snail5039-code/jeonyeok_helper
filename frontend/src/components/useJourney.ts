"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchJourney,
  generateJourney,
  loadDemoJourney,
  markDone,
  removeItem,
  saveDemoJourney,
} from "@/lib/journey";
import type { JourneyItem } from "@/lib/types";

/** 전역 로드맵 상태. 서버(또는 데모 모드면 이 브라우저)에 저장하고, 화면은 먼저 바꾼다. */
export function useJourney(userId: string, demo: boolean, ready: boolean) {
  const [items, setItems] = useState<JourneyItem[]>([]);
  // 대화에서 막 담긴 할 일 (잠깐 강조해서 보여 준다)
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const timers = useRef<number[]>([]);

  useEffect(() => {
    if (!ready || !userId) return;
    let alive = true;
    (async () => {
      try {
        const loaded = demo ? loadDemoJourney() : await fetchJourney(userId);
        if (alive) setItems(loaded);
      } catch {
        // 불러오지 못해도 채팅은 쓸 수 있다
      }
    })();
    return () => {
      alive = false;
    };
  }, [ready, userId, demo]);

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const update = useCallback(
    (next: (all: JourneyItem[]) => JourneyItem[]) =>
      setItems((all) => {
        const changed = next(all);
        if (demo) saveDemoJourney(changed);
        return changed;
      }),
    [demo],
  );

  const toggle = useCallback(
    async (item: JourneyItem) => {
      const done = !item.done;
      update((all) => all.map((i) => (i.id === item.id ? { ...i, done } : i)));
      if (demo) return;
      try {
        const saved = await markDone(userId, item.id, done);
        update((all) => all.map((i) => (i.id === saved.id ? saved : i)));
      } catch (e) {
        update((all) => all.map((i) => (i.id === item.id ? { ...i, done: item.done } : i)));
        setError(e instanceof Error ? e.message : "저장하지 못했어요.");
      }
    },
    [demo, update, userId],
  );

  const remove = useCallback(
    async (item: JourneyItem) => {
      update((all) => all.filter((i) => i.id !== item.id));
      if (demo) return;
      try {
        await removeItem(userId, item.id);
      } catch (e) {
        update((all) => [...all, item]);
        setError(e instanceof Error ? e.message : "빼지 못했어요.");
      }
    },
    [demo, update, userId],
  );

  /** 대화 답변에서 담긴 할 일을 더하고 몇 초 동안 강조한다. */
  const addPlanned = useCallback(
    (added: JourneyItem[]) => {
      if (!added.length) return;
      update((all) => [...all, ...added.filter((a) => !all.some((i) => i.id === a.id))]);
      setFresh((old) => new Set([...old, ...added.map((a) => a.id)]));
      timers.current.push(
        window.setTimeout(
          () => setFresh((old) => new Set([...old].filter((id) => !added.some((a) => a.id === id)))),
          8000,
        ),
      );
    },
    [update],
  );

  /** 서버가 바꾼 할 일 하나를 반영한다 (채팅의 '했어요' 버튼 등). */
  const applyItem = useCallback(
    (item: JourneyItem) => update((all) => all.map((i) => (i.id === item.id ? item : i))),
    [update],
  );

  /** '내 정보'로 로드맵을 한 번에 채운다. 새로 담긴 개수를 돌려준다. */
  const generate = useCallback(async (): Promise<number> => {
    setGenerating(true);
    setError("");
    try {
      if (demo) {
        await new Promise((r) => setTimeout(r, 800));
        update(() => loadDemoJourney());
        return 0;
      }
      const res = await generateJourney(userId);
      update(() => res.items);
      return res.added;
    } catch (e) {
      setError(e instanceof Error ? e.message : "로드맵을 만들지 못했어요.");
      return 0;
    } finally {
      setGenerating(false);
    }
  }, [demo, update, userId]);

  return { items, fresh, generating, error, setError, toggle, remove, addPlanned, applyItem, generate };
}

export type Journey = ReturnType<typeof useJourney>;
