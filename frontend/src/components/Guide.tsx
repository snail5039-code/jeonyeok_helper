"use client";

import { Check, CircleHelp, Map, Plus, SkipForward, Star, UserRound } from "lucide-react";
import { useState } from "react";

import { STAGE_BY_KEY } from "@/lib/journey";
import type { QuickReply, Suggestion } from "@/lib/types";

import { PhotoAvatar as Mascot } from "./PhotoAvatar";
import { StageIcon } from "./StageIcon";

/** 길잡이 전역이의 말풍선 줄. children에는 말풍선·버튼·제안 등을 넣는다. */
export function GuideBubble({
  rank,
  children,
  busy = false,
  big = false,
}: {
  rank: string;
  children: React.ReactNode;
  busy?: boolean;
  big?: boolean;
}) {
  return (
    <div
      className={`grid items-start gap-2.5 sm:gap-3 ${big ? "grid-cols-[52px_minmax(0,1fr)] sm:grid-cols-[68px_minmax(0,1fr)]" : "grid-cols-[44px_minmax(0,1fr)] sm:grid-cols-[56px_minmax(0,1fr)]"}`}
    >
      <Mascot rank={rank} size={big ? 64 : 54} className={`h-auto w-full ${busy ? "animate-wobble" : ""}`} />
      <div className="grid min-w-0 gap-2.5">{children}</div>
    </div>
  );
}

/** 말풍선 본문 (노란 쪽지, 굵은 테두리) */
export function Say({ children, big = false }: { children: React.ReactNode; big?: boolean }) {
  return (
    <div
      className={`max-w-[640px] justify-self-start rounded-[6px_20px_20px_20px] border-[2.5px] border-[#1f2416] bg-bubble px-4 py-3 leading-[1.7] text-[#1f2416] shadow-[4px_4px_0_var(--ink)] ${
        big ? "text-[16.5px]" : "text-[15.5px]"
      }`}
    >
      {children}
    </div>
  );
}

export function UserBubble({ text }: { text: string }) {
  return (
    <p className="max-w-[80%] justify-self-end rounded-[20px_6px_20px_20px] bg-accent px-4 py-2.5 text-[15.5px] leading-relaxed whitespace-pre-wrap text-accent-ink shadow-[3px_3px_0_rgb(23_61_122_/_0.8)]">
      {text}
    </p>
  );
}

/** 버튼 종류에 맞는 아이콘 (이모지 대신) */
function ReplyIcon({ reply }: { reply: QuickReply }) {
  const cls = "size-4 shrink-0";
  if (reply.action?.type === "done") return <Check className={cls} strokeWidth={2.6} />;
  if (reply.action?.type === "later") return <SkipForward className={cls} strokeWidth={2.2} />;
  if (reply.open === "journey") return <Map className={cls} strokeWidth={2.2} />;
  if (reply.open === "profile") return <UserRound className={cls} strokeWidth={2.2} />;
  if (reply.message?.includes("어떻게")) return <CircleHelp className={cls} strokeWidth={2.2} />;
  return null;
}

/** 빠른 답 버튼. '했어요'가 주 버튼, 나머지는 보조. disabled면 지난 대화의 버튼이다. */
export function QuickReplies({
  replies,
  disabled = false,
  onReply,
}: {
  replies: QuickReply[];
  disabled?: boolean;
  onReply: (reply: QuickReply) => void;
}) {
  if (!replies.length) return null;
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="빠른 답">
      {replies.map((r) => {
        const primary = r.action?.type === "done";
        return (
          <button
            key={r.label}
            type="button"
            disabled={disabled}
            onClick={() => onReply(r)}
            className={`inline-flex min-h-[38px] items-center gap-1.5 rounded-full border-2 px-3.5 py-1 text-left text-[14.5px] font-bold transition-transform disabled:opacity-45 ${
              primary
                ? "border-[#1f2416] bg-done text-[#1f2416] shadow-[3px_3px_0_var(--ink)] enabled:active:translate-x-[2px] enabled:active:translate-y-[2px] enabled:active:shadow-none"
                : r.open
                  ? "border-dashed border-edge bg-transparent text-fg-2 enabled:hover:border-ink"
                  : "border-edge bg-soft text-fg enabled:hover:border-ink"
            }`}
          >
            <ReplyIcon reply={r} />
            {r.label}
          </button>
        );
      })}
    </div>
  );
}

/** '작전도에 담을까요?' 고르기. 핵심 임무는 미리 골라 둔다. */
export function SuggestBox({
  suggest,
  disabled = false,
  onAdd,
}: {
  suggest: Suggestion[];
  disabled?: boolean;
  onAdd: (items: Suggestion[]) => Promise<number>;
}) {
  const [picked, setPicked] = useState<Set<string>>(() => new Set(suggest.filter((s) => s.core).map((s) => s.title)));
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [count, setCount] = useState(0);
  if (!suggest.length) return null;

  const toggle = (title: string) =>
    setPicked((old) => {
      const next = new Set(old);
      if (next.has(title)) next.delete(title);
      else next.add(title);
      return next;
    });

  const add = async () => {
    setState("saving");
    try {
      setCount(await onAdd(suggest.filter((s) => picked.has(s.title))));
      setState("saved");
    } catch {
      setState("error");
    }
  };

  const locked = disabled || state === "saving" || state === "saved";
  return (
    <section className="grid gap-1.5 rounded-2xl border-[2.5px] border-[#1f2416] bg-[#fff6d6] p-3.5 text-[#1f2416] shadow-[4px_4px_0_var(--olive-dark)]">
      <h3 className="flex items-baseline gap-2 text-[15px] font-extrabold">
        작전도에 담을까요?
        <span className="text-[12.5px] font-semibold text-[#7a7055]">고른 것만 담겨요</span>
      </h3>
      <ul className="grid">
        {suggest.map((s) => {
          const on = picked.has(s.title);
          return (
            <li key={s.title}>
              <label
                className={`grid grid-cols-[22px_minmax(0,1fr)] gap-2.5 rounded-lg px-1 py-1.5 ${locked ? "" : "cursor-pointer hover:bg-white/60"}`}
              >
                <input type="checkbox" className="sr-only" checked={on} disabled={locked} onChange={() => toggle(s.title)} />
                <span
                  aria-hidden
                  className={`mt-0.5 grid size-[21px] place-items-center rounded-[5px] border-[2.5px] border-[#1f2416] ${on ? "bg-[#556b2f] text-white" : "bg-white"}`}
                >
                  {on && <Check className="size-3.5" strokeWidth={3.5} />}
                </span>
                <span className="grid min-w-0 gap-0.5">
                  <span className="flex flex-wrap items-center gap-x-1.5 text-[15px] font-bold">
                    {s.core && <Star aria-label="핵심" className="size-4 fill-[#e0a100] text-[#c98a00]" />}
                    {s.title}
                    <span className="inline-flex items-center gap-1 text-[12px] font-semibold text-[#7a7055]">
                      <StageIcon stage={s.stage} className="size-3.5" />
                      {STAGE_BY_KEY[s.stage].title}
                    </span>
                  </span>
                  <span className="text-[13.5px] text-[#4f4a3a]">
                    {s.action}
                    {s.deadline && <b className="ml-1.5 rounded bg-[#f8e1d8] px-1.5 text-[12.5px] text-[#b8322a]">{s.deadline}</b>}
                  </span>
                </span>
              </label>
            </li>
          );
        })}
      </ul>
      {state === "saved" ? (
        <p role="status" className="flex items-center gap-1.5 text-[14px] font-bold">
          <Check className="size-4 text-[#556b2f]" strokeWidth={3} />
          {count ? `${count}개 담았어요. 끝낼 때마다 계급이 올라가요.` : "이미 작전도에 있는 임무예요."}
        </p>
      ) : (
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={locked || picked.size === 0}
            onClick={add}
            className="inline-flex h-10 items-center gap-1.5 rounded-[10px] border-[2.5px] border-[#1f2416] bg-[#c9e48a] px-4 text-[14.5px] font-extrabold shadow-[3px_3px_0_#1f2416] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none disabled:opacity-50"
          >
            <Plus className="size-4" strokeWidth={2.6} />
            {picked.size ? `${picked.size}개 담기` : "담을 임무를 골라 주세요"}
          </button>
          {state === "error" ? (
            <span className="text-[13px] font-semibold text-[#b8322a]">담지 못했어요. 다시 눌러 주세요.</span>
          ) : (
            suggest.some((s) => s.core) && <span className="text-[12.5px] text-[#7a7055]">핵심 임무는 미리 골라 뒀어요</span>
          )}
        </div>
      )}
    </section>
  );
}
