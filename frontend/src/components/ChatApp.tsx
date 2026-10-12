"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { demoChat } from "@/lib/demo";
import { sendFeedback, type Rating } from "@/lib/feedback";
import { streamChat } from "@/lib/sse";
import { getUserId, writeStorage } from "@/lib/storage";
import type { ChatEvent, Profile, Turn } from "@/lib/types";

import { Composer } from "./Composer";
import { HomeView } from "./HomeView";
import { SourceList } from "./SourceList";
import { TopNav } from "./TopNav";
import { TurnView } from "./TurnView";

const today = () => {
  const d = new Date();
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")} 조회`;
};

// 테마: 사용자가 고른 값(html[data-theme])이 있으면 그것, 없으면 시스템 설정을 따른다.
const darkQuery = () => matchMedia("(prefers-color-scheme: dark)");
function subscribeTheme(onChange: () => void) {
  const mq = darkQuery();
  mq.addEventListener("change", onChange);
  window.addEventListener("themechange", onChange);
  return () => {
    mq.removeEventListener("change", onChange);
    window.removeEventListener("themechange", onChange);
  };
}
function isDark() {
  const chosen = document.documentElement.dataset.theme;
  return chosen ? chosen === "dark" : darkQuery().matches;
}

function useTheme() {
  const dark = useSyncExternalStore(subscribeTheme, isDark, () => false);
  const toggle = () => {
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    writeStorage("jeonyeok.theme", next);
    window.dispatchEvent(new Event("themechange"));
  };
  return { dark, toggle };
}

export function ChatApp() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [profile, setProfile] = useState<Profile>({});
  const [demo, setDemo] = useState(false);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const threadId = useRef<string | null>(null);
  const userId = useRef("");
  const { dark, toggle } = useTheme();

  const updateTurn = (id: string, patch: (t: Turn) => Partial<Turn>) =>
    setTurns((all) => all.map((t) => (t.id === id ? { ...t, ...patch(t) } : t)));

  const mergeProfile = (p?: Profile) => p && setProfile((old) => ({ ...old, ...p }));

  const ask = useCallback(
    async (question: string) => {
      if (busy) return;
      setBusy(true);
      const id = `turn-${Date.now()}`;
      setTurns((all) => [...all, { id, question, status: "loading", steps: [], text: "", sources: [], profile: {} }]);
      requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ block: "start" }));

      const handle = (e: ChatEvent) => {
        switch (e.event) {
          case "thread":
            threadId.current = e.data.thread_id;
            break;
          case "step":
            updateTurn(id, (t) => ({ steps: [...t.steps, e.data.label] }));
            break;
          case "delta":
            updateTurn(id, (t) => ({ status: "streaming", text: t.text + e.data.text }));
            break;
          case "answer":
            updateTurn(id, () => ({ status: "answer", text: e.data.text, sources: e.data.sources ?? [], profile: e.data.profile ?? {} }));
            mergeProfile(e.data.profile);
            break;
          case "question":
            updateTurn(id, () => ({ status: "question", text: e.data.text }));
            mergeProfile(e.data.profile);
            break;
          case "error":
            updateTurn(id, () => ({ status: "error", text: e.data.message }));
            break;
        }
      };

      try {
        const events = demo
          ? demoChat(question, Boolean(profile.service_type))
          : streamChat({ message: question, thread_id: threadId.current, user_id: userId.current });
        for await (const e of events) handle(e);
      } catch (err) {
        updateTurn(id, () => ({
          status: "error",
          text: err instanceof Error ? err.message : "연결이 끊겼어요. 잠시 후 다시 시도해 주세요.",
        }));
      } finally {
        setBusy(false);
      }
    },
    [busy, demo, profile.service_type],
  );

  const feedback = useCallback(
    async (turn: Turn, rating: Rating, comment?: string) => {
      if (demo) return; // 데모 답변은 저장하지 않는다
      await sendFeedback({
        rating,
        comment,
        question: turn.question,
        answer: turn.text,
        thread_id: threadId.current,
        user_id: userId.current,
      });
    },
    [demo],
  );

  // 시작: 서버 에이전트가 준비됐는지 보고, 아니면 데모 모드로 연다.
  useEffect(() => {
    userId.current = getUserId();
    const params = new URLSearchParams(location.search);
    let useDemo = params.has("demo");
    (async () => {
      try {
        const health = await (await fetch("/api/health")).json();
        if (!health.agent_ready) useDemo = true;
        if (!useDemo) {
          const res = await fetch(`/api/profile/${encodeURIComponent(userId.current)}`);
          mergeProfile((await res.json()).profile);
        }
      } catch {
        useDemo = true;
      }
      setDemo(useDemo);
      setReady(true);
    })();
  }, []);

  // 공유 링크: ?q=질문 으로 들어오면 서버 상태를 확인한 뒤 한 번 물어본다.
  const sharedAsked = useRef(false);
  useEffect(() => {
    if (!ready || sharedAsked.current) return;
    sharedAsked.current = true;
    const q = new URLSearchParams(location.search).get("q");
    if (q) void ask(q);
  }, [ready, ask]);

  const goHome = () => {
    setTurns([]);
    threadId.current = null;
  };

  const isHome = turns.length === 0;
  const latest = [...turns].reverse().find((t) => t.status === "answer");

  return (
    <div className="flex h-full flex-col">
      <TopNav
        isHome={isHome}
        profile={profile}
        demo={demo}
        dark={dark}
        onToggleTheme={toggle}
        onHome={goHome}
        onAsk={ask}
      />

      {isHome ? (
        <HomeView onAsk={ask} />
      ) : (
        <div className="relative flex min-h-0 flex-1 flex-col">
          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto grid max-w-[1120px] gap-7 px-4 pt-6 pb-[120px] lg:px-8 lg:pt-10 lg:pb-[140px] xl:grid-cols-[minmax(0,1fr)_288px] xl:gap-12">
              <div className="grid min-w-0 content-start gap-8">
                {turns.map((t) => (
                  <TurnView key={t.id} turn={t} onAsk={ask} onFeedback={feedback} />
                ))}
              </div>
              <aside aria-label="근거 자료" className="sticky top-0 hidden content-start gap-3.5 xl:grid">
                <div className="flex items-baseline justify-between">
                  <h2 className="text-sm font-bold">근거 자료</h2>
                  {latest?.sources.length ? <span className="text-xs tabular-nums text-fg-3">{today()}</span> : null}
                </div>
                {latest?.sources.length ? (
                  <SourceList sources={latest.sources} />
                ) : (
                  <p className="rounded-xl border border-dashed border-line-strong p-3 text-[13px] leading-relaxed text-fg-3">
                    답변이 나오면 근거로 쓴 법령과 기관이 여기에 모여요.
                  </p>
                )}
              </aside>
            </div>
          </div>
          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-b from-transparent to-bg to-40% px-3 pt-4 pb-[calc(12px+env(safe-area-inset-bottom,0px))] lg:px-8 lg:pb-[calc(20px+env(safe-area-inset-bottom,0px))]">
            <div className="mx-auto max-w-[1056px]">
              <Composer id="chat-input" compact placeholder="이어서 물어보세요" disabled={busy} onSubmit={ask} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
