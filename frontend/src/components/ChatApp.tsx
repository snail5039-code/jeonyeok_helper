"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { demoChat } from "@/lib/demo";
import { sendFeedback, type Rating } from "@/lib/feedback";
import { addItems, levelOf, saveProfile } from "@/lib/journey";
import { streamChat } from "@/lib/sse";
import { getUserId, readStorage, writeStorage } from "@/lib/storage";
import type { ChatAction, ChatEvent, Guide, JourneyItem, Profile, QuickReply, Suggestion, Turn } from "@/lib/types";

import { Composer } from "./Composer";
import { HomeView } from "./HomeView";
import { JourneyChip, JourneyPanel } from "./JourneyPanel";
import { JourneyView } from "./JourneyView";
import { ProfileView } from "./ProfileView";
import { TopNav } from "./TopNav";
import { TurnView } from "./TurnView";
import { useJourney } from "./useJourney";

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

const DEMO_PROFILE_KEY = "jeonyeok.demo.profile";

export type Page = "chat" | "journey" | "profile";

export function ChatApp() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [profile, setProfile] = useState<Profile>({});
  const [demo, setDemo] = useState(false);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [page, setPage] = useState<Page>("chat");
  const [userId, setUserId] = useState("");
  const threadId = useRef<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const { dark, toggle } = useTheme();
  const journey = useJourney(userId, demo, ready);
  const { addPlanned, applyItem, toggle: toggleItem } = journey;
  const rank = levelOf(journey.items).rank;

  const updateTurn = (id: string, patch: (t: Turn) => Partial<Turn>) =>
    setTurns((all) => all.map((t) => (t.id === id ? { ...t, ...patch(t) } : t)));

  const mergeProfile = (p?: Profile) => p && setProfile((old) => ({ ...old, ...p }));

  const ask = useCallback(
    async (question: string, action?: ChatAction) => {
      if (busy) return;
      setPage("chat");
      setBusy(true);
      const id = `turn-${Date.now()}`;
      const controller = new AbortController();
      abort.current = controller;
      setTurns((all) => [
        ...all,
        { id, question, status: "loading", steps: [], text: "", sources: [], profile: {}, followUps: [] },
      ]);
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
            updateTurn(id, () => ({
              status: "answer",
              text: e.data.text,
              sources: e.data.sources ?? [],
              profile: e.data.profile ?? {},
              followUps: e.data.follow_ups ?? [],
            }));
            mergeProfile(e.data.profile);
            break;
          case "guide": {
            const g: Guide = e.data;
            mergeProfile(g.profile);
            updateTurn(id, (t) => {
              // 한 대화에서 길잡이가 두 번 말하면(예: 로드맵 완성 안내) 이어서 보여 준다
              if (t.guide) return { moreGuides: [...(t.moreGuides ?? []), g] };
              return g.mode === "talk" ? { status: "talk", text: g.say, guide: g } : { guide: g };
            });
            break;
          }
          case "journey":
            if (e.data.added.length) addPlanned(e.data.added);
            if (e.data.done) applyItem(e.data.done);
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

      // 멈추면 그때까지 써진 초안은 남기고(근거 확인 전이라는 표시와 함께), 없으면 멈췄다고만 알린다.
      const stopped = () =>
        updateTurn(id, (t) =>
          t.text
            ? { status: "answer", stopped: true, sources: [], followUps: [] }
            : { status: "error", text: "질문을 멈췄어요." },
        );

      try {
        const events = demo
          ? demoChat(question, Boolean(profile.service_type), action)
          : streamChat({ message: question, thread_id: threadId.current, user_id: userId, action }, controller.signal);
        for await (const e of events) {
          if (controller.signal.aborted) break;
          handle(e);
        }
        if (controller.signal.aborted) stopped();
      } catch (err) {
        if (controller.signal.aborted) stopped();
        else
          updateTurn(id, () => ({
            status: "error",
            text: err instanceof Error ? err.message : "연결이 끊겼어요. 잠시 후 다시 시도해 주세요.",
          }));
      } finally {
        abort.current = null;
        setBusy(false);
      }
    },
    [busy, demo, profile.service_type, userId, addPlanned, applyItem],
  );

  const openJourney = () => setPage("journey");

  /** 길잡이 버튼: 화면 열기, 또는 버튼 말을 보내며 동작(했어요·나중에)을 함께 보낸다 */
  const reply = useCallback(
    (r: QuickReply) => {
      if (r.open) return setPage(r.open);
      if (demo && r.action?.type === "done") {
        const item = journey.items.find((i) => i.id === r.action!.item_id);
        if (item && !item.done) void toggleItem(item);
      }
      if (r.message) void ask(r.message, r.action);
    },
    [ask, demo, journey.items, toggleItem],
  );

  /** 길잡이가 제안한 할 일 중 고른 것을 로드맵에 담고, 새로 담긴 개수를 돌려준다 */
  const addSuggest = useCallback(
    async (turn: Turn, picked: Suggestion[]) => {
      const known = new Set(journey.items.map((i) => i.title));
      const fresh = picked.filter((s) => !known.has(s.title));
      const added: JourneyItem[] = demo
        ? fresh.map((s) => ({
            ...s,
            id: `demo:${s.title}`,
            origin: "chat",
            question: turn.question,
            done: false,
            created_at: null,
            done_at: null,
          }))
        : await addItems(userId, fresh, turn.question);
      addPlanned(added);
      return added.length;
    },
    [addPlanned, demo, journey.items, userId],
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
        user_id: userId,
      });
    },
    [demo, userId],
  );

  const saveMyProfile = async (next: Profile) => {
    if (demo) {
      writeStorage(DEMO_PROFILE_KEY, JSON.stringify(next));
      setProfile(next);
      return;
    }
    setProfile(await saveProfile(userId, next));
  };

  // 시작: 서버 에이전트가 준비됐는지 보고, 아니면 데모 모드로 연다.
  useEffect(() => {
    const id = getUserId();
    const params = new URLSearchParams(location.search);
    let useDemo = params.has("demo");
    (async () => {
      try {
        const health = await (await fetch("/api/health")).json();
        if (!health.agent_ready) useDemo = true;
        if (!useDemo) {
          const res = await fetch(`/api/profile/${encodeURIComponent(id)}`);
          mergeProfile((await res.json()).profile);
        }
      } catch {
        useDemo = true;
      }
      if (useDemo) {
        try {
          mergeProfile(JSON.parse(readStorage(DEMO_PROFILE_KEY) ?? "{}"));
        } catch {
          // 저장된 데모 프로필이 깨졌으면 무시
        }
      }
      const start = params.get("page");
      if (start === "journey" || start === "profile") setPage(start);
      setUserId(id);
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
    setPage("chat");
    setTurns([]);
    threadId.current = null;
  };
  const isHome = turns.length === 0;
  const view = page === "chat" ? (isHome ? "home" : "chat") : page;

  return (
    <div className="flex h-full flex-col">
      <TopNav
        view={view}
        profile={profile}
        journey={journey.items}
        demo={demo}
        dark={dark}
        onToggleTheme={toggle}
        onHome={goHome}
        onJourney={openJourney}
        onProfile={() => setPage("profile")}
        onAsk={ask}
      />

      {page === "journey" ? (
        <JourneyView journey={journey} profile={profile} onAsk={ask} onProfile={() => setPage("profile")} />
      ) : page === "profile" ? (
        <ProfileView
          key={ready ? "ready" : "loading"}
          profile={profile}
          demo={demo}
          onSave={saveMyProfile}
          onFillJourney={() => {
            setPage("journey");
            void journey.generate();
          }}
        />
      ) : isHome ? (
        <HomeView
          profile={profile}
          items={journey.items}
          rank={rank}
          ready={ready}
          onAsk={ask}
          onReply={reply}
          onRoadmap={openJourney}
          onProfile={() => setPage("profile")}
        />
      ) : (
        <div className="relative flex min-h-0 flex-1 flex-col">
          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto grid max-w-[1180px] gap-7 px-4 pt-5 pb-[120px] lg:px-8 lg:pt-8 lg:pb-[140px] xl:grid-cols-[minmax(0,1fr)_340px] xl:gap-10">
              <div className="grid min-w-0 content-start gap-8">
                <div className="sticky top-0 z-10 -mx-1 flex justify-end bg-gradient-to-b from-bg via-bg to-transparent px-1 pb-2 xl:hidden">
                  <JourneyChip journey={journey} onOpen={openJourney} />
                </div>
                {turns.map((t, i) => (
                  <TurnView
                    key={t.id}
                    turn={t}
                    rank={rank}
                    latest={i === turns.length - 1 && !busy}
                    onAsk={ask}
                    onReply={reply}
                    onAddSuggest={addSuggest}
                    onFeedback={feedback}
                  />
                ))}
              </div>
              <div className="hidden xl:block">
                <JourneyPanel journey={journey} profile={profile} onAsk={ask} onOpen={openJourney} />
              </div>
            </div>
          </div>
          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-b from-transparent to-bg to-40% px-3 pt-4 pb-[calc(12px+env(safe-area-inset-bottom,0px))] lg:px-8 lg:pb-[calc(20px+env(safe-area-inset-bottom,0px))]">
            <div className="mx-auto max-w-[1116px]">
              <Composer
                id="chat-input"
                compact
                placeholder="전역이에게 이어서 말해 보세요"
                busy={busy}
                onStop={() => abort.current?.abort()}
                onSubmit={ask}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
