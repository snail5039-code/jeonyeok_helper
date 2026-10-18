"use client";

import { AlarmClock, CalendarPlus, Check, ExternalLink, MessageCircle, MessageCircleQuestion, Sparkles, Star, X } from "lucide-react";

import { calendarEntries } from "@/lib/calendar";
import { STAGES, currentStage, daysLeft, ddayLabel, dueDate, stageDone } from "@/lib/journey";
import type { JourneyItem, Source } from "@/lib/types";

import { StageIcon } from "./StageIcon";

const SOURCE_LABEL: Record<Source["type"], string> = { regulation: "법령", benefit: "혜택", institution: "기관" };

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
      <span aria-hidden className="absolute top-[38px] right-5 left-5 border-t-[3px] border-dashed border-edge" />
      {stages.map((s) => {
        const list = items.filter((i) => i.stage === s.key);
        const done = stageDone(list);
        const current = s.key === now && !done;
        const isSelected = selected === s.key;
        return (
          <li key={s.key} className="relative z-10 grid min-w-[52px] justify-items-center gap-1">
            <button
              type="button"
              onClick={() => onSelect?.(s.key)}
              aria-label={`${s.title} ${list.filter((i) => i.done).length}/${list.length}`}
              aria-pressed={isSelected}
              className={`relative grid size-[44px] place-items-center rounded-full border-[2.5px] border-ink ${
                done ? "bg-done text-[#1f2416]" : current ? "bg-[#ffe066] text-[#1f2416]" : "bg-soft text-fg-2"
              } ${isSelected ? "shadow-[3px_3px_0_var(--ink)]" : ""}`}
            >
              <StageIcon stage={s.key} />
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

/** 신청 기한: 전역일을 알면 D-day, 모르면 문구만 */
export function DeadlineChip({ item, dischargeDate }: { item: JourneyItem; dischargeDate?: string }) {
  if (!item.deadline) return null;
  const due = dueDate(item, dischargeDate);
  const days = due ? daysLeft(due) : null;
  const urgent = days !== null && days <= 60;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[12px] font-bold ${
        urgent ? "bg-warn-soft text-warn" : "bg-sunken text-fg-2"
      }`}
    >
      <AlarmClock className="size-3.5" />
      {item.deadline}
      {days !== null && !item.done && <span className="tabular-nums">· {ddayLabel(days)}</span>}
    </span>
  );
}

export function ItemCard({
  item,
  fresh = false,
  compact = false,
  dischargeDate,
  onToggle,
  onAsk,
  onRemove,
  onCalendar,
}: {
  item: JourneyItem;
  fresh?: boolean;
  compact?: boolean;
  dischargeDate?: string;
  onToggle: (item: JourneyItem) => void;
  onAsk: (question: string) => void;
  onRemove?: (item: JourneyItem) => void;
  /** 이 할 일의 기한을 캘린더 파일로 내려받는다 (마감일을 셀 수 있을 때만 버튼이 보인다) */
  onCalendar?: (item: JourneyItem) => void;
}) {
  const canCalendar = Boolean(onCalendar) && calendarEntries([item], dischargeDate).length > 0;
  return (
    <li
      className={`group grid grid-cols-[26px_minmax(0,1fr)] gap-3 rounded-xl border p-3.5 transition-colors ${
        item.done ? "border-line bg-sunken" : fresh ? "border-accent bg-accent-soft" : "border-edge bg-soft"
      }`}
    >
      <button
        type="button"
        onClick={() => onToggle(item)}
        aria-pressed={item.done}
        aria-label={`${item.title} ${item.done ? "완료 취소" : "완료"}`}
        className={`mt-0.5 grid size-[24px] place-items-center rounded-md border-[2.5px] border-ink ${
          item.done ? "bg-olive text-olive-ink" : "bg-white"
        }`}
      >
        {item.done && <Check className="size-4" strokeWidth={3.5} />}
      </button>
      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-1">
        <div className="flex items-start gap-2">
          <span className={`min-w-0 flex-1 text-[15px] font-bold ${item.done ? "text-fg-3 line-through" : ""}`}>
            {item.core && (
              <Star
                aria-label="핵심"
                className="mr-1 mb-0.5 inline size-4 fill-[#e0a100] text-[#c98a00]"
                strokeWidth={2}
              />
            )}
            {item.title}
          </span>
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
        {!item.done && <div className="text-[14px] font-semibold text-olive">{item.action}</div>}
        {item.deadline && (
          <div className="flex flex-wrap items-center gap-2">
            <DeadlineChip item={item} dischargeDate={dischargeDate} />
            {canCalendar && (
              <button
                type="button"
                onClick={() => onCalendar!(item)}
                aria-label={`${item.title} 기한 캘린더에 넣기`}
                className="inline-flex items-center gap-1 text-[12.5px] font-semibold text-fg-2 hover:text-accent"
              >
                <CalendarPlus className="size-3.5" />
                캘린더에 넣기
              </button>
            )}
          </div>
        )}
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
          <p className="inline-flex items-center gap-1 text-[12px] text-fg-3">
            <MessageCircle className="size-3.5" />“{item.question}” 대화에서 담김
          </p>
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
