"use client";

import { Check, CircleHelp, Star } from "lucide-react";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { fetchPrograms, type ProgramSummary } from "@/lib/applications";
import { downloadBackup, fetchBackup, makeBackup, parseBackup, restoreBackup } from "@/lib/backup";
import { demoChat } from "@/lib/demo";
import { findByCode, takeResumeParam } from "@/lib/resume";
import { loadCopy, saveCopy, shouldRestore } from "@/lib/localCopy";
import { sendFeedback, type Rating } from "@/lib/feedback";
import { stepReplies } from "@/lib/guide";
import { addItems, levelOf, nextItem, saveDemoJourney, saveProfile } from "@/lib/journey";
import { streamChat } from "@/lib/sse";
import { getUserId, readStorage, USER_ID_KEY, writeStorage } from "@/lib/storage";
import type { ChatAction, ChatEvent, Guide, JourneyItem, Profile, QuickReply, Suggestion, Turn } from "@/lib/types";

import { Book, BookTitle } from "./Book";
import { Composer } from "./Composer";
import { HelpView } from "./HelpView";
import { HomeView } from "./HomeView";
import { DeadlineChip } from "./JourneyParts";
import { ApplicationKit } from "./ApplicationKit";
import { JourneyView } from "./JourneyView";
import { KeepNotice } from "./KeepNotice";
import { ProfileView } from "./ProfileView";
import { StatusPanel } from "./StatusPanel";
import { MobileTabs, TopNav } from "./TopNav";
import { TurnView } from "./TurnView";
import { UndoToast } from "./UndoToast";
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

export type Page = "chat" | "journey" | "profile" | "help";

export function ChatApp() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [profile, setProfile] = useState<Profile>({});
  const [demo, setDemo] = useState(false);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [page, setPage] = useState<Page>("chat");
  // 신청 서류 도우미로 연 제도 (null이면 닫힘)
  const [kit, setKit] = useState<string | null>(null);
  const [programs, setPrograms] = useState<ProgramSummary[]>([]);
  const [userId, setUserId] = useState("");
  // 기록을 되살리면 '내 정보' 입력칸을 새 값으로 다시 그린다
  const [profileVersion, setProfileVersion] = useState(0);
  const [recordsNotice, setRecordsNotice] = useState("");
  // 브라우저 사본: 서버 기록과 맞춘 뒤부터 사본을 갱신한다 (그 전에 빈 목록으로 덮어쓰지 않게)
  const [copySynced, setCopySynced] = useState(false);
  const [offlineNotice, setOfflineNotice] = useState("");
  const copyChecked = useRef(false);
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
          case "found":
            updateTurn(id, (t) => ({ found: [...(t.found ?? []), ...e.data.sources] }));
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
              asOf: e.data.as_of,
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
      if (r.open?.startsWith("kit:")) return setKit(r.open.slice(4));
      if (r.open === "journey" || r.open === "profile") return setPage(r.open);
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

  /** 내 기록 파일로 내려받기. 서버 기록이 기준이고, 데모 모드면 이 브라우저의 기록 */
  const exportRecords = async () => {
    downloadBackup(demo ? makeBackup(profile, journey.items) : await fetchBackup(userId));
  };

  /** 기록 파일로 이 브라우저의 기록을 바꾼다. 지금 기록이 있으면 먼저 묻는다 */
  const importRecords = async (file: File): Promise<string> => {
    const backup = parseBackup(await file.text());
    const hasNow = journey.items.length > 0 || Boolean(profile.service_type);
    if (hasNow && !confirm(`지금 기록을 이 파일 내용(임무 ${backup.items.length}개)으로 바꿀까요? 지금 기록은 사라져요.`)) {
      return "불러오기를 취소했어요.";
    }
    let restored = { profile: backup.profile, items: backup.items };
    if (demo) {
      writeStorage(DEMO_PROFILE_KEY, JSON.stringify(backup.profile));
      saveDemoJourney(backup.items);
    } else {
      restored = await restoreBackup(userId, backup);
    }
    setProfile(restored.profile);
    journey.replaceAll(restored.items);
    const done = `기록을 되살렸어요. 임무 ${restored.items.length}개, 완료 ${restored.items.filter((i) => i.done).length}개.`;
    setRecordsNotice(done);
    setProfileVersion((v) => v + 1);
    return done;
  };

  /** 다른 기기에서 받은 코드로 이 브라우저를 그 기록으로 바꾸고 작전도를 연다 */
  const resumeWithCode = async (code: string): Promise<string> => {
    const found = await findByCode(code);
    if (found === userId) return "이미 이 기록을 쓰고 있어요.";
    const hasNow = journey.items.length > 0 || Boolean(profile.service_type);
    if (hasNow && !confirm("이 브라우저의 지금 기록 대신 코드의 기록으로 바꿀까요? 지금 기록은 파일로 저장해 두지 않으면 다시 열 수 없어요.")) {
      return "이어 하기를 취소했어요.";
    }
    writeStorage(USER_ID_KEY, found);
    // 익명 ID가 바뀌었으니 화면 상태를 처음부터 다시 읽는다 (작전도 화면으로)
    history.replaceState(null, "", "/?page=journey");
    location.reload();
    return "기록을 여는 중…";
  };

  // 시작: 서버 에이전트가 준비됐는지 보고, 아니면 데모 모드로 연다.
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    let useDemo = params.has("demo");
    (async () => {
      // QR(?resume=코드)로 들어오면 그 기록으로 바꾸고 주소에서는 코드를 지운다
      const { code, cleaned } = takeResumeParam(new URL(location.href));
      if (code) {
        history.replaceState(null, "", cleaned);
        try {
          writeStorage(USER_ID_KEY, await findByCode(code));
        } catch {
          // 틀린 코드면 이 브라우저의 기록 그대로 연다
        }
      }
      const id = getUserId();
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
      if (start === "journey" || start === "profile" || start === "help") setPage(start);
      setUserId(id);
      setDemo(useDemo);
      setReady(true);
    })();
  }, []);

  // 시작할 때 한 번: 서버 기록이 비었는데 브라우저 사본이 있으면 사본으로 서버를 되살리고,
  // 서버에서 작전도를 못 불러왔으면 사본으로 보여 준다.
  const { status: journeyStatus, replaceAll } = journey;
  useEffect(() => {
    if (!ready || demo || copyChecked.current || journeyStatus === "loading") return;
    copyChecked.current = true;
    const copy = loadCopy(userId);
    if (journeyStatus === "failed") {
      if (copy?.items.length) {
        replaceAll(copy.items);
        setProfile((p) => (Object.keys(p).length ? p : copy.profile));
        setOfflineNotice("서버에 연결하지 못해 이 브라우저에 저장해 둔 작전도를 보여 드려요. 바꾼 내용은 저장되지 않을 수 있어요.");
      }
      return;
    }
    if (!shouldRestore({ profile, items: journey.items }, copy)) {
      setCopySynced(true);
      return;
    }
    void restoreBackup(userId, makeBackup(copy.profile, copy.items))
      .then((restored) => {
        setProfile(restored.profile);
        replaceAll(restored.items);
      })
      .catch(() => {
        replaceAll(copy.items);
        setProfile(copy.profile);
      })
      .finally(() => setCopySynced(true));
  }, [ready, demo, userId, journeyStatus, replaceAll, profile, journey.items]);

  // 서버 기록과 맞춘 뒤로는 바뀔 때마다 사본을 갱신한다
  useEffect(() => {
    if (copySynced && !demo && userId) saveCopy(userId, profile, journey.items);
  }, [copySynced, demo, userId, profile, journey.items]);

  // 신청 서류 도우미가 있는 제도 목록 (작전도 할 일에 '서류 챙기기' 버튼을 붙이는 데 쓴다)
  useEffect(() => {
    if (!ready || demo) return;
    let alive = true;
    void fetchPrograms().then((p) => alive && setPrograms(p));
    return () => {
      alive = false;
    };
  }, [ready, demo]);

  // 되살린 결과 안내는 '내 정보' 화면을 떠나면 지운다 (다시 왔을 때 지난 안내가 보이지 않게)
  useEffect(() => {
    if (page !== "profile") setRecordsNotice("");
  }, [page]);

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
  const next = nextItem(journey.items);

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
        onChat={() => setPage("chat")}
        onJourney={openJourney}
        onProfile={() => setPage("profile")}
        onHelp={() => setPage("help")}
        onAsk={ask}
      />

      {offlineNotice && (
        <p role="status" className="mx-auto mt-2 w-[min(100%-20px,1320px)] rounded-[10px] border-2 border-warn/60 bg-soft px-3.5 py-2 text-[13.5px] font-semibold text-warn">
          {offlineNotice}
        </p>
      )}

      {page === "chat" && isHome ? (
        <HomeView
          profile={profile}
          items={journey.items}
          ready={ready}
          busy={busy}
          onAsk={ask}
          onReply={reply}
          onJourney={openJourney}
          onProfile={() => setPage("profile")}
        />
      ) : page === "help" ? (
        <HelpView onAsk={ask} onJourney={openJourney} onProfile={() => setPage("profile")} />
      ) : page === "journey" ? (
        <JourneyView journey={journey} profile={profile} userId={userId} demo={demo} programs={programs} onKit={setKit} onAsk={ask} onProfile={() => setPage("profile")} />
      ) : page === "profile" ? (
        <ProfileView
          key={ready ? `ready-${profileVersion}` : "loading"}
          profile={profile}
          demo={demo}
          onSave={saveMyProfile}
          onExport={exportRecords}
          onImport={importRecords}
          recordsNotice={recordsNotice}
          userId={userId}
          onResume={resumeWithCode}
          onFillJourney={() => {
            setPage("journey");
            void journey.generate();
          }}
        />
      ) : (
        // 위아래 여백은 padding 대신 빈 칸으로: sticky(지금 할 일·입력창)가 padding만큼 떨어져 그 틈으로 글이 비친다
        <main className="flex-1 overflow-y-auto px-2.5 sm:px-5">
          <div aria-hidden className="h-4 sm:h-6" />
          <div className="mx-auto grid max-w-[1320px] items-start gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
            {/* 왼쪽 수첩: 작전실 (대화) */}
            <Book label="작전실" rings={14} className="flex min-h-[calc(100dvh-150px)] min-w-0 flex-col">
              <div className="mb-4 flex items-center justify-between gap-3">
                <BookTitle accent="작전실">전역 생활</BookTitle>
              </div>

              {/* 지금 할 일: 대화를 내려도 위에 남는다 */}
              {/* 첫 화면에서는 전역이 인사가 다음 임무를 말해 주므로 대화 중에만 */}
              {ready && next && !isHome && (
                // 위에 붙어 있는 동안 뒤로 대화가 비치지 않게 종이색 띠를 깐다 (아래로 갈수록 흐려짐)
                <div className="z-10 mb-5 -mr-4 -ml-2 pr-4 pl-2 sm:sticky sm:top-0 sm:-mr-7 sm:bg-bg sm:pt-3 sm:pr-7 sm:pb-1 sm:shadow-[0_14px_12px_-4px_var(--bg)]">
                  <NowCard item={next} profile={profile} busy={busy} onReply={reply} />
                </div>
              )}

              <div className="grid flex-1 content-start gap-7 pt-1">
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

              <div className="sticky bottom-0 z-10 mt-6 -mr-4 -ml-2 grid gap-1.5 bg-bg pt-3 pr-4 pb-2.5 pl-2 shadow-[0_-16px_14px_-4px_var(--bg)] sm:-mr-7 sm:pr-7">
                <Composer
                  id="chat-input"
                  compact
                  placeholder={isHome ? "전역이에게 아무거나 물어보세요" : "전역이에게 이어서 말해 보세요"}
                  busy={busy}
                  onStop={() => abort.current?.abort()}
                  onSubmit={ask}
                />
                <p className="hidden px-1 text-[12.5px] text-fg-3 sm:block">근거가 있는 내용만 답해요. 정확한 자격과 기한은 기관에 꼭 확인하세요.</p>
              </div>
            </Book>

            <StatusPanel
              className="sticky top-6 hidden lg:block"
              profile={profile}
              items={journey.items}
              onJourney={openJourney}
              onProfile={() => setPage("profile")}
            />
          </div>
          <div aria-hidden className="h-4 lg:h-6" />
        </main>
      )}

      <UndoToast journey={journey} />

      {kit && (
        <ApplicationKit
          programId={kit}
          userId={userId}
          onClose={() => setKit(null)}
          onProfile={() => {
            setKit(null);
            setPage("profile");
          }}
        />
      )}

      {/* 작전도에 할 일이 생기면 한 번만, 기록이 이 브라우저에 묶여 있다고 알린다 */}
      {ready && !demo && journey.items.length > 0 && (
        <KeepNotice
          onExport={exportRecords}
          onOpenCode={() => {
            setPage("profile");
            // '내 정보' 화면이 그려질 때까지 기다렸다가 '내 기록 지키기' 칸으로 내린다
            let tries = 0;
            const scroll = () => {
              const el = document.getElementById("keep-records");
              if (el) el.scrollIntoView({ block: "start" });
              else if (tries++ < 20) setTimeout(scroll, 50);
            };
            setTimeout(scroll, 50);
          }}
        />
      )}

      <MobileTabs
        view={view}
        journey={journey.items}
        onChat={() => setPage("chat")}
        onJourney={openJourney}
        onProfile={() => setPage("profile")}
        onHelp={() => setPage("help")}
        onHome={goHome}
      />
    </div>
  );
}

/** 지금 할 일 카드: 다음 임무 하나와 [방법 보기] [했어요] */
function NowCard({
  item,
  profile,
  busy,
  onReply,
}: {
  item: JourneyItem;
  profile: Profile;
  busy: boolean;
  onReply: (r: QuickReply) => void;
}) {
  const [done, how] = stepReplies(item);
  return (
    <section
      aria-label="지금 할 일"
      className="now-card rounded-[14px] border-[2.5px] border-ink bg-soft px-4 py-3.5 shadow-[4px_4px_0_var(--olive-dark)]"
    >
      <span className="now-card-label font-stencil justify-self-start -rotate-3 rounded-md bg-warn px-2 py-1 text-[13px] text-white">지금 할 일</span>
      <div className="min-w-0">
        <h3 className="flex items-start gap-1.5 text-[17px] leading-[1.4] font-extrabold">
          {item.core && <Star aria-label="핵심" className="size-4 shrink-0 fill-[#e0a100] text-[#c98a00]" />}
          <span>{item.title}</span>
        </h3>
        <p className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[13px] leading-[1.5] text-fg-2">
          <span className="min-w-0">{item.action}</span>
          <DeadlineChip item={item} dischargeDate={profile.discharge_date} />
        </p>
      </div>
      <div className="now-card-actions flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => onReply(how)}
          className="inline-flex h-10 flex-1 items-center justify-center gap-1.5 rounded-[10px] border-2 border-edge bg-bg px-3.5 text-[14px] font-bold text-fg-2 hover:border-ink disabled:opacity-50 sm:flex-none"
        >
          <CircleHelp className="size-4" strokeWidth={2.2} />
          방법 보기
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onReply(done)}
          className="inline-flex h-10 flex-1 items-center justify-center gap-1.5 rounded-[10px] border-[2.5px] border-[#1f2416] bg-done px-4 text-[14.5px] font-extrabold text-[#1f2416] shadow-[3px_3px_0_var(--ink)] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none disabled:opacity-50 sm:flex-none"
        >
          <Check className="size-4" strokeWidth={2.8} />
          했어요
        </button>
      </div>
    </section>
  );
}
