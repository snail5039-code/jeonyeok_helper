"use client";

import { Check, ExternalLink, MessageCircleQuestion, Sparkles, X } from "lucide-react";

import { STAGES, currentStage, levelOf, progress } from "@/lib/journey";
import type { JourneyItem, Source } from "@/lib/types";

import { Bubble, Mascot } from "./Doodle";

const SOURCE_LABEL: Record<Source["type"], string> = { regulation: "법령", benefit: "혜택", institution: "기관" };

/** 마스코트 + 계급 + 진행률. 노란 종이 위에 그려서 다크 모드에서도 그림이 잘 보인다. */
export function JourneyHero({ items, compact = false }: { items: JourneyItem[]; compact?: boolean }) {
  const p = progress(items);
  const level = levelOf(p.percent);
  const empty = !items.length;
  return (
    <section
      className={`relative grid items-end overflow-hidden rounded-2xl border-[2.5px] border-[#1b1b1b] bg-paper text-paper-ink shadow-[4px_4px_0_var(--ink)] ${
        compact ? "grid-cols-[72px_minmax(0,1fr)] gap-3 p-3.5" : "grid-cols-[84px_minmax(0,1fr)] gap-3 p-4 sm:grid-cols-[130px_minmax(0,1fr)] sm:gap-4 sm:p-6"
      }`}
    >
      <Mascot
        rank={level.rank}
        size={compact ? 72 : 130}
        className={`animate-wobble justify-self-center ${compact ? "" : "max-sm:h-auto max-sm:w-[84px]"}`}
      />
      <div className="grid min-w-0 gap-3">
        <Bubble className={compact ? "text-[14px]" : ""}>
          {empty ? "할 일이 아직 없음. 물어보면 내가 적어 둘게!" : level.line}
        </Bubble>
        <div className="grid gap-1.5">
          <div className="flex items-baseline justify-between gap-2">
            <span className="font-fun text-[20px] leading-none">
              {level.rank}
              {level.next > 0 && !empty && (
                <span className="ml-1.5 font-sans text-[12px] font-semibold opacity-70">다음 계급까지 {level.next}%</span>
              )}
            </span>
            <span className="text-[13px] font-bold tabular-nums">
              {p.done}/{p.total} · {p.percent}%
            </span>
          </div>
          <div
            className="h-3.5 overflow-hidden rounded-full border-2 border-[#1b1b1b] bg-white"
            role="progressbar"
            aria-label="전역 로드맵 달성률"
            aria-valuenow={p.percent}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div
              className="h-full bg-[repeating-linear-gradient(-45deg,#7d8c3c_0_8px,#93a24c_8px_16px)] transition-[width] duration-700"
              style={{ width: `${p.percent}%` }}
            />
          </div>
        </div>
      </div>
    </section>
  );
}

/** 단계를 길 위의 정거장처럼: 끝난 단계는 도장, 지금 단계는 강조. */
export function StageTrack({
  items,
  selected,
  onSelect,
}: {
  items: JourneyItem[];
  selected?: string | null;
  onSelect?: (key: (typeof STAGES)[number]["key"]) => void;
}) {
  const now = currentStage(items);
  const stages = STAGES.filter((s) => items.some((i) => i.stage === s.key));
  if (!stages.length) return null;
  return (
    <ol className="relative flex items-start justify-between gap-1 overflow-x-auto pt-4 pb-1">
      {/* 점선 길 */}
      <span aria-hidden className="absolute top-[38px] right-5 left-5 border-t-[3px] border-dashed border-line-strong" />
      {stages.map((s) => {
        const list = items.filter((i) => i.stage === s.key);
        const done = list.every((i) => i.done);
        const current = s.key === now && !done;
        const isSelected = selected === s.key;
        return (
          <li key={s.key} className="relative z-10 grid min-w-[52px] justify-items-center gap-1">
            <button
              type="button"
              onClick={() => onSelect?.(s.key)}
              aria-label={`${s.title} ${list.filter((i) => i.done).length}/${list.length}`}
              aria-pressed={isSelected}
              className={`relative grid size-[44px] place-items-center rounded-full border-[2.5px] border-ink text-[20px] transition-transform hover:-translate-y-0.5 ${
                done ? "bg-[#c9e48a]" : current ? "bg-[#ffe066]" : "bg-bg"
              } ${isSelected ? "shadow-[3px_3px_0_var(--ink)]" : ""}`}
            >
              {s.emoji}
              {done && (
                <span className="font-fun absolute -top-2 -right-3 -rotate-12 rounded-md border-2 border-[#c0392b] bg-white px-1 text-[10px] leading-tight text-[#c0392b]">
                  완료
                </span>
              )}
              {current && (
                <span className="font-fun absolute -top-3.5 rounded-full bg-ink px-1.5 text-[10px] leading-[16px] text-bg">
                  지금
                </span>
              )}
            </button>
            <span className={`text-center text-[11.5px] leading-tight font-semibold ${current ? "text-fg" : "text-fg-2"}`}>
              {s.title}
            </span>
            <span className="text-[11px] text-fg-3 tabular-nums">
              {list.filter((i) => i.done).length}/{list.length}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function ItemCard({
  item,
  fresh = false,
  compact = false,
  onToggle,
  onAsk,
  onRemove,
}: {
  item: JourneyItem;
  fresh?: boolean;
  compact?: boolean;
  onToggle: (item: JourneyItem) => void;
  onAsk: (question: string) => void;
  onRemove?: (item: JourneyItem) => void;
}) {
  return (
    <li
      className={`group grid grid-cols-[26px_minmax(0,1fr)] gap-3 rounded-xl border p-3.5 transition-colors ${
        item.done ? "border-line bg-soft" : fresh ? "border-accent bg-accent-soft" : "border-line-strong bg-bg"
      }`}
    >
      <button
        type="button"
        onClick={() => onToggle(item)}
        aria-pressed={item.done}
        aria-label={`${item.title} ${item.done ? "완료 취소" : "완료"}`}
        className={`mt-0.5 grid size-[24px] place-items-center rounded-md border-[2.5px] border-[#1b1b1b] ${
          item.done ? "bg-[#7d8c3c] text-white" : "bg-white"
        }`}
      >
        {item.done && <Check className="size-4" strokeWidth={3.5} />}
      </button>
      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-1">
        <div className="flex items-start gap-2">
          <span className={`min-w-0 flex-1 text-[15px] font-bold ${item.done ? "text-fg-3 line-through" : ""}`}>{item.title}</span>
          {fresh && (
            <span className="font-fun inline-flex shrink-0 items-center gap-0.5 rounded-full bg-accent px-2 text-[12px] leading-[20px] text-accent-ink">
              <Sparkles className="size-3" />방금 담김
            </span>
          )}
          {onRemove && (
            <button
              type="button"
              onClick={() => onRemove(item)}
              aria-label={`${item.title} 빼기`}
              className="shrink-0 rounded p-0.5 text-fg-3 opacity-0 group-hover:opacity-100 hover:text-fg focus:opacity-100"
            >
              <X className="size-4" />
            </button>
          )}
        </div>
        {!item.done && <div className="text-[14px] font-semibold text-accent">{item.action}</div>}
        {!compact && item.detail && <p className="text-[13.5px] leading-relaxed text-fg-2">{item.detail}</p>}
        {!compact && (
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {item.sources.slice(0, 3).map((s) => (
              <SourceChip key={`${s.type}:${s.title}`} source={s} />
            ))}
            <button
              type="button"
              onClick={() => onAsk(`${item.title}, 어떻게 진행하면 돼요?`)}
              className="ml-auto inline-flex items-center gap-1 text-[12.5px] font-semibold text-fg-2 hover:text-accent"
            >
              <MessageCircleQuestion className="size-3.5" />
              이 단계 진행하기
            </button>
          </div>
        )}
        {!compact && item.origin === "chat" && item.question && (
          <p className="text-[12px] text-fg-3">💬 “{item.question}” 대화에서 담김</p>
        )}
      </div>
    </li>
  );
}

function SourceChip({ source: s }: { source: Source }) {
  const body = (
    <>
      <b className={`shrink-0 whitespace-nowrap ${s.type === "regulation" ? "text-law" : ""}`}>{SOURCE_LABEL[s.type]}</b>
      <span className="min-w-0 truncate">{s.title}</span>
    </>
  );
  const cls = "inline-flex max-w-full items-center gap-1 rounded-md bg-sunken px-2 py-1 text-[12px] text-fg-2";
  return s.url ? (
    <a href={s.url} target="_blank" rel="noopener" className={`${cls} hover:text-accent`}>
      {body}
      <ExternalLink className="size-3 shrink-0" />
    </a>
  ) : (
    <span className={cls}>{body}</span>
  );
}
