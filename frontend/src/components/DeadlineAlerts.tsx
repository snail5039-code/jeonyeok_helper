"use client";

import { BellOff, BellRing, Download, Send, Share } from "lucide-react";
import { useEffect, useState } from "react";

import {
  currentEnv,
  currentSubscription,
  fetchPushKey,
  pushSupport,
  registerWorker,
  saveSubscription,
  sendTest,
  turnOff,
  turnOn,
  type PushSupport,
} from "@/lib/push";

interface Props {
  userId: string;
  /** 캘린더에 넣을 수 있는(전역일로 마감일을 셀 수 있는) 기한 수 */
  dueCount: number;
}

/** 크롬·엣지·삼성 인터넷이 주는 '설치' 이벤트 (표준 타입에 아직 없다) */
interface InstallPrompt extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const button =
  "inline-flex h-10 items-center gap-1.5 rounded-[10px] border-2 border-edge bg-bg px-3 text-[14px] font-bold text-fg hover:border-ink disabled:opacity-60";

/** 기한 알림 받기: 브라우저 알림(30·7·1일 전)과 홈 화면에 추가 */
export function DeadlineAlerts({ userId, dueCount }: Props) {
  const [key, setKey] = useState<string | null>(null);
  const [support, setSupport] = useState<PushSupport | null>(null);
  const [sub, setSub] = useState<PushSubscription | null>(null);
  const [install, setInstall] = useState<InstallPrompt | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    let alive = true;
    const s = pushSupport(currentEnv());
    void fetchPushKey().then(async (k) => {
      if (!alive) return;
      setKey(k);
      setSupport(s);
      if (!k || s !== "ready") return;
      await registerWorker().catch(() => undefined);
      const existing = await currentSubscription().catch(() => null);
      if (!alive || !existing) return;
      setSub(existing);
      // 이어 하기로 익명 ID가 바뀌었을 수 있어 지금 ID로 다시 알린다
      void saveSubscription(userId, existing).catch(() => undefined);
    });
    const onPrompt = (e: Event) => {
      e.preventDefault();
      setInstall(e as InstallPrompt);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    return () => {
      alive = false;
      window.removeEventListener("beforeinstallprompt", onPrompt);
    };
  }, [userId]);

  if (!key || !support) return null; // 알림 기능이 꺼진 서버

  const run = async (work: () => Promise<string>) => {
    setBusy(true);
    setMessage(null);
    try {
      setMessage({ ok: true, text: await work() });
    } catch (e) {
      setMessage({ ok: false, text: e instanceof Error ? e.message : "다시 시도해 주세요." });
    } finally {
      setBusy(false);
    }
  };

  const on = () =>
    run(async () => {
      setSub(await turnOn(userId, key));
      return "알림을 켰어요. 기한 30일·7일·1일 전 아침에 알려 드릴게요.";
    });
  const off = () =>
    run(async () => {
      if (sub) await turnOff(userId, sub);
      setSub(null);
      return "알림을 껐어요.";
    });
  const test = () =>
    run(async () => {
      const n = await sendTest(userId);
      return n ? "시험 알림을 보냈어요. 잠시 뒤 알림이 오는지 확인해 보세요." : "알림을 받을 기기가 없어요. 알림을 다시 켜 주세요.";
    });
  const installApp = () =>
    run(async () => {
      if (!install) return "";
      await install.prompt();
      const { outcome } = await install.userChoice;
      setInstall(null);
      return outcome === "accepted" ? "홈 화면에 추가했어요." : "홈 화면 추가를 취소했어요.";
    });

  return (
    <section className="grid gap-3 rounded-xl border-2 border-edge bg-soft p-4" aria-labelledby="deadline-alerts">
      <h2 id="deadline-alerts" className="flex items-center gap-2">
        <BellRing className="size-[18px] text-olive" strokeWidth={2.2} />
        <span className="font-stencil text-[17px] font-normal">기한 알림</span>
        {sub && <span className="rounded-full bg-done px-2 text-[12px] font-bold leading-[20px] text-[#1f2416]">켜짐</span>}
      </h2>
      <p className="text-[13.5px] leading-[1.6] text-fg-2">
        신청 기한 <b className="text-fg">30일·7일·1일 전</b>에 이 기기로 알려 드려요. 로그인 없이, 이 브라우저에만 켜져요.
        {dueCount === 0 && " 지금은 알릴 기한이 없어요(내 정보에 전역일을 넣으면 기한이 계산돼요)."}
      </p>

      {support === "ios-install" && (
        <p className="flex flex-wrap items-center gap-1 rounded-lg bg-sunken px-3 py-2 text-[13.5px] leading-[1.6]">
          아이폰은 홈 화면에 추가한 앱에서만 알림을 받을 수 있어요. 사파리 아래의
          <Share className="inline size-4" aria-label="공유" />
          공유 → <b>홈 화면에 추가</b>를 누른 뒤, 홈 화면의 전역도우미에서 알림을 켜 주세요.
        </p>
      )}
      {support === "unsupported" && (
        <p className="text-[13.5px] text-fg-2">이 브라우저는 알림을 지원하지 않아요. 캘린더에 넣기를 이용해 주세요.</p>
      )}

      <div className="flex flex-wrap gap-2">
        {support === "ready" &&
          (sub ? (
            <>
              <button type="button" disabled={busy} onClick={() => void test()} className={button}>
                <Send className="size-4" />
                시험 알림 보내기
              </button>
              <button type="button" disabled={busy} onClick={() => void off()} className={button}>
                <BellOff className="size-4" />
                알림 끄기
              </button>
            </>
          ) : (
            <button type="button" disabled={busy} onClick={() => void on()} className={button}>
              <BellRing className="size-4" />
              알림 켜기
            </button>
          ))}
        {install && (
          <button type="button" disabled={busy} onClick={() => void installApp()} className={button}>
            <Download className="size-4" />
            홈 화면에 추가
          </button>
        )}
      </div>

      {message && message.text && (
        <p role={message.ok ? "status" : "alert"} className={`text-[13px] font-semibold ${message.ok ? "text-olive" : "text-warn"}`}>
          {message.text}
        </p>
      )}
    </section>
  );
}
