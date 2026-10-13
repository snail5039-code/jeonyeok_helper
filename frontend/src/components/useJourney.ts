"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchJourney,
  generateJourney,
  loadDemoJourney,
  markDone,
  removeItem,
  restoreItems,
  saveDemoJourney,
} from "@/lib/journey";
import type { JourneyItem } from "@/lib/types";

/** 되돌릴 수 있는 변경 한 건 (완료, 빼기, 담기, 내 정보로 만들기) */
export interface Change {
  id: string;
  label: string;
  undo: () => Promise<void>;
}

const HISTORY_MAX = 20;
const TOAST_MS = 10_000;

/** 전역 로드맵 상태. 서버(또는 데모 모드면 이 브라우저)에 저장하고, 화면은 먼저 바꾼다.
    바뀐 것은 모두 기록해 둬서, 마음이 바뀌면 하나씩 또는 여러 단계를 한꺼번에 되돌릴 수 있다. */
export function useJourney(userId: string, demo: boolean, ready: boolean) {
  const [items, setItems] = useState<JourneyItem[]>([]);
  // 대화에서 막 담긴 할 일 (잠깐 강조해서 보여 준다)
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<Change[]>([]);
  const [toast, setToast] = useState<Change | null>(null);
  const timers = useRef<number[]>([]);
  const itemsRef = useRef<JourneyItem[]>([]);
  // 빼기를 되돌리면 새 id로 다시 만들어지므로, 옛 id를 새 id로 바꿔 부르는 표
  const alias = useRef<Record<string, string>>({});

  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

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

  const resolve = (id: string) => alias.current[id] ?? id;
  const find = (id: string) => itemsRef.current.find((i) => i.id === resolve(id));

  // ---------- 기록하지 않는 동작 (되돌리기도 이것으로 한다) ----------

  const setDone = useCallback(
    async (id: string, done: boolean) => {
      const real = alias.current[id] ?? id;
      update((all) => all.map((i) => (i.id === real ? { ...i, done } : i)));
      if (demo) return;
      const saved = await markDone(userId, real, done);
      update((all) => all.map((i) => (i.id === saved.id ? saved : i)));
    },
    [demo, update, userId],
  );

  const deleteIds = useCallback(
    async (ids: string[]) => {
      const real = ids.map((id) => alias.current[id] ?? id);
      update((all) => all.filter((i) => !real.includes(i.id)));
      if (demo) return;
      await Promise.all(real.map((id) => removeItem(userId, id).catch(() => undefined)));
    },
    [demo, update, userId],
  );

  const bringBack = useCallback(
    async (gone: JourneyItem[]) => {
      if (demo) {
        update((all) => [...all, ...gone.filter((g) => !all.some((i) => i.id === g.id))]);
        return;
      }
      const back = await restoreItems(userId, gone);
      gone.forEach((g) => {
        const now = back.find((b) => b.title === g.title);
        if (now) alias.current[g.id] = now.id;
      });
      update((all) => [...all, ...back.filter((b) => !all.some((i) => i.id === b.id))]);
    },
    [demo, update, userId],
  );

  // ---------- 기록 ----------

  const record = useCallback((label: string, undo: () => Promise<void>) => {
    const change: Change = { id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, label, undo };
    setHistory((h) => [...h.slice(-(HISTORY_MAX - 1)), change]);
    setToast(change);
    timers.current.push(window.setTimeout(() => setToast((t) => (t?.id === change.id ? null : t)), TOAST_MS));
  }, []);

  /** 맨 위에서부터 count개를 되돌린다 (방향을 틀 때 여러 단계를 한꺼번에) */
  const undoLast = useCallback(
    async (count = 1) => {
      const target = history.slice(-count).reverse();
      if (!target.length) return;
      setHistory((h) => h.slice(0, h.length - target.length));
      setToast(null);
      try {
        for (const change of target) await change.undo();
      } catch (e) {
        setError(e instanceof Error ? e.message : "되돌리지 못했어요.");
      }
    },
    [history],
  );

  // ---------- 화면에서 쓰는 동작 ----------

  const toggle = useCallback(
    async (item: JourneyItem) => {
      const done = !item.done;
      try {
        await setDone(item.id, done);
      } catch (e) {
        await setDone(item.id, item.done).catch(() => undefined);
        setError(e instanceof Error ? e.message : "저장하지 못했어요.");
        return;
      }
      record(`‘${item.title}’ ${done ? "완료" : "완료 취소"}`, () => setDone(item.id, !done));
    },
    [record, setDone],
  );

  const remove = useCallback(
    async (item: JourneyItem) => {
      try {
        await deleteIds([item.id]);
      } catch (e) {
        setError(e instanceof Error ? e.message : "빼지 못했어요.");
        return;
      }
      record(`‘${item.title}’ 뺌`, () => bringBack([item]));
    },
    [bringBack, deleteIds, record],
  );

  /** 담긴 할 일을 더하고 몇 초 동안 강조한다 (대화에서 고른 것, 첫 작전도 자동 생성). */
  const addPlanned = useCallback(
    (added: JourneyItem[], label?: string) => {
      const fresh = added.filter((a) => !itemsRef.current.some((i) => i.id === a.id));
      if (!fresh.length) return;
      update((all) => [...all, ...fresh.filter((a) => !all.some((i) => i.id === a.id))]);
      setFresh((old) => new Set([...old, ...fresh.map((a) => a.id)]));
      timers.current.push(
        window.setTimeout(
          () => setFresh((old) => new Set([...old].filter((id) => !fresh.some((a) => a.id === id)))),
          8000,
        ),
      );
      record(label ?? `임무 ${fresh.length}개 담음`, () => deleteIds(fresh.map((a) => a.id)));
    },
    [deleteIds, record, update],
  );

  /** 서버가 바꾼 할 일 하나를 반영한다 (채팅의 '했어요' 버튼 등). */
  const applyItem = useCallback(
    (item: JourneyItem) => {
      const before = find(item.id);
      update((all) => all.map((i) => (i.id === item.id ? item : i)));
      if (before && before.done !== item.done) {
        record(`‘${item.title}’ ${item.done ? "완료" : "완료 취소"}`, () => setDone(item.id, before.done));
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [record, setDone, update],
  );

  /** '내 정보'로 로드맵을 한 번에 채운다. 새로 담긴 개수를 돌려준다. */
  const generate = useCallback(async (): Promise<number> => {
    setGenerating(true);
    setError("");
    const had = new Set(itemsRef.current.map((i) => i.id));
    try {
      let added: JourneyItem[];
      if (demo) {
        await new Promise((r) => setTimeout(r, 800));
        const next = loadDemoJourney();
        update(() => next);
        added = [];
      } else {
        const res = await generateJourney(userId);
        update(() => res.items);
        added = res.items.filter((i) => !had.has(i.id));
      }
      if (added.length) record(`내 정보로 임무 ${added.length}개 담음`, () => deleteIds(added.map((a) => a.id)));
      return added.length;
    } catch (e) {
      setError(e instanceof Error ? e.message : "작전도를 만들지 못했어요.");
      return 0;
    } finally {
      setGenerating(false);
    }
  }, [deleteIds, demo, record, update, userId]);

  return {
    items,
    fresh,
    generating,
    error,
    setError,
    history,
    toast,
    dismissToast: () => setToast(null),
    undoLast,
    toggle,
    remove,
    addPlanned,
    applyItem,
    generate,
  };
}

export type Journey = ReturnType<typeof useJourney>;
