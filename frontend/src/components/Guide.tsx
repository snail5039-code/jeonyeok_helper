"use client";

import { Check, Plus, Star } from "lucide-react";
import { useState } from "react";

import { STAGE_BY_KEY } from "@/lib/journey";
import type { QuickReply, Suggestion } from "@/lib/types";

import { Mascot } from "./Doodle";

/** 길잡이 전역이의 말풍선. children에는 버튼·제안 등을 넣는다. */
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
    <div className={`grid items-start gap-2.5 ${big ? "grid-cols-[72px_minmax(0,1fr)]" : "grid-cols-[48px_minmax(0,1fr)]"}`}>
      <Mascot rank={rank} size={big ? 72 : 48} className={busy ? "animate-wobble" : ""} />
      <div className="grid min-w-0 gap-3">{children}</div>
    </div>
  );
}

/** 말풍선 본문 (노란 종이, 굵은 테두리) */
export function Say({ children, big = false }: { children: React.ReactNode; big?: boolean }) {
  return (
    <div
      className={`justify-self-start rounded-[6px_20px_20px_20px] border-[2.5px] border-[#1b1b1b] bg-paper px-4 py-3 leading-relaxed text-paper-ink shadow-[3px_3px_0_var(--ink)] ${
        big ? "text-[17px]" : "text-[15.5px]"
      }`}
    >
      {children}
    </div>
  );
}

export function UserBubble({ text }: { text: string }) {
  return (
    <p className="max-w-[85%] justify-self-end rounded-[20px_6px_20px_20px] bg-accent px-4 py-2.5 text-[15.5px] leading-relaxed whitespace-pre-wrap text-accent-ink">
      {text}
    </p>
  );
}

/** 빠른 답 버튼. disabled면 지난 대화의 버튼이라 누를 수 없다. */
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
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="빠른 답">
      {replies.map((r) => (
        <button
          key={r.label}
          type="button"
          disabled={disabled}
          onClick={() => onReply(r)}
          className={`inline-flex min-h-[34px] items-center rounded-full border-2 px-3 py-1 text-left text-[14px] font-semibold transition-transform disabled:opacity-45 ${
            r.action?.type === "done"
              ? "border-ink bg-[#c9e48a] text-[#1b1b1b] enabled:hover:-translate-y-0.5"
              : "border-line-strong bg-bg text-fg enabled:hover:-translate-y-0.5 enabled:hover:border-ink"
          }`}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}

/** '로드맵에 담을까요?' 고르기. 핵심 할 일은 미리 골라 둔다. */
export function SuggestBox({
  suggest,
  disabled = false,
  onAdd,
}: {
  suggest: Suggestion[];
  disabled?: boolean;
  onAdd: (items: Suggestion[]) => Promise<number>;
}) {
  const [picked, setPicked] = useState<Set<string>>(() => new Set(suggest.map((s) => s.title)));
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
    <section className="grid gap-2 rounded-2xl border-2 border-dashed border-line-strong p-3.5">
      <h3 className="font-fun text-[16px]">🗺️ 로드맵에 담을까요?</h3>
      <ul className="grid gap-1.5">
        {suggest.map((s) => {
          const on = picked.has(s.title);
          return (
            <li key={s.title}>
              <label className={`grid cursor-pointer grid-cols-[22px_minmax(0,1fr)] gap-2.5 rounded-lg px-1 py-1 ${locked ? "cursor-default" : "hover:bg-soft"}`}>
                <input type="checkbox" className="sr-only" checked={on} disabled={locked} onChange={() => toggle(s.title)} />
                <span
                  aria-hidden
                  className={`mt-0.5 grid size-[20px] place-items-center rounded-md border-2 border-ink ${on ? "bg-[#7d8c3c] text-white" : "bg-white"}`}
                >
                  {on && <Check className="size-3.5" strokeWidth={3.5} />}
                </span>
                <span className="grid min-w-0 gap-0.5">
                  <span className="text-[14.5px] font-bold">
                    {s.core && <Star aria-label="핵심" className="mr-1 mb-0.5 inline size-4 fill-[#ffc531] text-[#d99a00]" />}
                    {s.title}
                    <span className="ml-1.5 text-[12px] font-semibold text-fg-3">
                      {STAGE_BY_KEY[s.stage].emoji} {STAGE_BY_KEY[s.stage].title}
                    </span>
                  </span>
                  <span className="text-[13px] text-fg-2">
                    {s.action}
                    {s.deadline && <b className="ml-1 text-warn">⏰ {s.deadline}</b>}
                  </span>
                </span>
              </label>
            </li>
          );
        })}
      </ul>
      {state === "saved" ? (
        <p role="status" className="font-fun text-[15px]">
          {count ? `✨ ${count}개 담았음! 하나씩 끝내면 계급이 올라가요` : "이미 다 담겨 있음 ㅇㅇ"}
        </p>
      ) : (
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={locked || picked.size === 0}
            onClick={add}
            className="inline-flex h-9 items-center gap-1 rounded-xl border-[2.5px] border-[#1b1b1b] bg-[#ffe066] px-3 text-[14px] font-bold text-[#1b1b1b] shadow-[3px_3px_0_var(--ink)] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none disabled:opacity-50"
          >
            <Plus className="size-4" />
            {picked.size}개 담기
          </button>
          {state === "error" && <span className="text-[13px] text-warn">담지 못했어요. 다시 눌러 주세요.</span>}
        </div>
      )}
    </section>
  );
}
