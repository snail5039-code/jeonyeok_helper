"use client";

import { Check, ChevronRight, Star } from "lucide-react";
import { useState } from "react";

import { MIN_CORE, STAGE_BY_KEY, toCivilian, badges as badgesOf, levelOf, nextItem, progress, sortItems } from "@/lib/journey";
import type { JourneyItem, Profile } from "@/lib/types";

import { Stamp } from "./Book";
import { Mascot, Medal, RankStripes } from "./Doodle";
import { DeadlineChip } from "./JourneyParts";
import { StageIcon } from "./StageIcon";
import type { Journey } from "./useJourney";

const RANKS = ["이병", "일병", "상병", "병장"] as const;

/** 계급 카드: 마스코트 사진, 계급, 핵심 임무 진행, 남은 개수 */
export function RankCard({ items }: { items: JourneyItem[] }) {
  const p = progress(items);
  const level = levelOf(items);
  const left = toCivilian(items) ?? 0;
  return (
    <section className="grid grid-cols-[84px_minmax(0,1fr)] items-center gap-3.5 rounded-xl border-[2.5px] border-ink bg-soft p-3 shadow-[4px_4px_0_var(--olive-dark)]">
      <div className="grid place-items-center rounded-lg border-2 border-edge bg-sunken pt-1">
        <Mascot rank={level.rank} size={72} />
      </div>
      <div className="grid min-w-0 gap-1.5">
        <h3 className="flex items-baseline gap-2">
          <span className="font-fun text-[25px] leading-none">{level.rank}</span>
          {p.coreTotal > 0 && <span className="text-[13px] font-bold text-fg-3">핵심 임무 {p.coreDone}/{p.coreTotal}</span>}
        </h3>
        <div
          className="h-3 overflow-hidden rounded-full border-2 border-ink bg-white"
          role="progressbar"
          aria-label="핵심 임무 진행률"
          aria-valuenow={p.percent}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className="h-full bg-[repeating-linear-gradient(-45deg,#556b2f_0_8px,#6b7f3a_8px_16px)] transition-[width] duration-700"
            style={{ width: `${p.percent}%` }}
          />
        </div>
        <p className="text-[13.5px] text-fg-2">
          {!items.length ? (
            "대화하면서 임무를 담아 보세요."
          ) : p.coreTotal < MIN_CORE ? (
            `핵심 임무를 ${MIN_CORE}개 이상 담으면 민간인에 도전할 수 있어요.`
          ) : level.finished ? (
            "핵심 임무 완료. 민간인 됐어요!"
          ) : (
            <>
              <b className="text-fg">{left}개</b>만 더 끝내면 민간인이에요.
            </>
          )}
        </p>
      </div>
    </section>
  );
}

/** 이병 → 민간인 계급 줄 */
export function RankTrack({ items }: { items: JourneyItem[] }) {
  const level = levelOf(items);
  const at = level.finished ? 4 : RANKS.indexOf(level.rank as (typeof RANKS)[number]);
  return (
    <ol className="relative grid grid-cols-5 py-1" aria-label={`지금 계급 ${level.rank}`}>
      <span aria-hidden className="absolute top-[24px] right-[10%] left-[10%] border-t-[3px] border-dashed border-edge" />
      {RANKS.map((r, i) => (
        <li key={r} className={`relative grid justify-items-center gap-1 text-[13px] font-bold ${i > at ? "text-fg-3" : ""}`}>
          <span
            className={`grid size-[42px] place-items-center rounded-full border-[2.5px] ${
              i === at
                ? "border-ink bg-[#ffe066] shadow-[0_0_0_4px_rgb(255_224_102_/_0.45)]"
                : i < at
                  ? "border-ink bg-soft"
                  : "border-dashed border-edge bg-sunken"
            }`}
          >
            <RankStripes rank={r} muted={i > at} />
          </span>
          {r}
        </li>
      ))}
      <li className={`relative grid justify-items-center gap-1 text-[13px] font-bold ${at < 4 ? "text-fg-3" : ""}`}>
        <span
          className={`grid size-[42px] place-items-end overflow-hidden rounded-full border-[2.5px] ${
            at === 4 ? "border-ink bg-[#ffe066]" : "border-dashed border-edge bg-sunken"
          }`}
        >
          <Mascot rank="민간인" size={34} className={at < 4 ? "opacity-60 grayscale" : ""} />
        </span>
        민간인
      </li>
    </ol>
  );
}

/** 임무 목록: 남은 / 완료 탭. 다음 할 일은 빨간 줄로 표시. */
export function MissionList({
  journey,
  profile,
  limit,
  onOpen,
}: {
  journey: Journey;
  profile: Profile;
  limit?: number;
  onOpen?: () => void;
}) {
  const { items, fresh, toggle } = journey;
  const [tab, setTab] = useState<"open" | "done">("open");
  const open = sortItems(items.filter((i) => !i.done));
  const done = items.filter((i) => i.done).sort((a, b) => (b.done_at ?? "").localeCompare(a.done_at ?? ""));
  const next = nextItem(items);
  const list = (tab === "open" ? open : done).slice(0, limit);
  const tabCls = (on: boolean) =>
    `h-10 flex-1 text-[14px] font-bold ${on ? "bg-sunken text-fg shadow-[inset_0_-3px_0_var(--olive)]" : "text-fg-3"}`;

  return (
    <section className="overflow-hidden rounded-xl border-2 border-edge bg-soft">
      <div className="flex border-b-2 border-edge" role="tablist">
        <button type="button" role="tab" aria-selected={tab === "open"} onClick={() => setTab("open")} className={tabCls(tab === "open")}>
          남은 임무 {open.length}
        </button>
        <button type="button" role="tab" aria-selected={tab === "done"} onClick={() => setTab("done")} className={tabCls(tab === "done")}>
          완료 {done.length}
        </button>
      </div>
      {list.length ? (
        <ul>
          {list.map((item) => (
            <li
              key={item.id}
              className={`grid grid-cols-[24px_minmax(0,1fr)] gap-2.5 border-t-[1.5px] border-dashed border-line px-3.5 py-2.5 first:border-t-0 ${
                item.id === next?.id && tab === "open"
                  ? "bg-sunken shadow-[inset_3px_0_0_var(--warn)]"
                  : fresh.has(item.id)
                    ? "bg-accent-soft"
                    : ""
              }`}
            >
              <button
                type="button"
                onClick={() => toggle(item)}
                aria-pressed={item.done}
                aria-label={`${item.title} ${item.done ? "완료 취소" : "완료"}`}
                className={`mt-0.5 grid size-[22px] place-items-center rounded-[5px] border-[2.5px] border-ink ${item.done ? "bg-olive text-olive-ink" : "bg-white"}`}
              >
                {item.done && <Check className="size-3.5" strokeWidth={3.5} />}
              </button>
              <div className="grid min-w-0 gap-1">
                <span className={`flex items-center gap-1.5 text-[14.5px] font-bold ${item.done ? "text-fg-3 line-through" : ""}`}>
                  {item.core && <Star aria-label="핵심" className="size-4 shrink-0 fill-[#e0a100] text-[#c98a00]" />}
                  <span className="min-w-0 truncate">{item.title}</span>
                </span>
                <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[12.5px] font-semibold text-fg-3">
                  {!item.done && <DeadlineChip item={item} dischargeDate={profile.discharge_date} />}
                  <span className="inline-flex items-center gap-1">
                    <StageIcon stage={item.stage} className="size-3.5" />
                    {STAGE_BY_KEY[item.stage].title}
                  </span>
                  {item.sources[0]?.url && (
                    <a href={item.sources[0].url} target="_blank" rel="noopener" className="inline-flex items-center text-accent hover:underline">
                      근거
                      <ChevronRight className="size-3.5" />
                    </a>
                  )}
                </span>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="px-3.5 py-4 text-[13.5px] text-fg-3">
          {tab === "open"
            ? items.length
              ? "남은 임무가 없어요. 수고했어요!"
              : "대화하면 임무가 여기 담겨요."
            : "아직 끝낸 임무가 없어요."}
        </p>
      )}
      {onOpen && (
        <footer className="flex items-center justify-between gap-2 border-t-2 border-edge px-3.5 py-2.5 text-[13px] font-semibold text-fg-2">
          <span className="min-w-0 truncate">{done[0] ? `최근 완료: ${done[0].title}` : "하나씩 끝내면 계급이 올라가요"}</span>
          <button type="button" onClick={onOpen} className="inline-flex shrink-0 items-center font-bold text-olive hover:underline">
            전체 보기
            <ChevronRight className="size-4" />
          </button>
        </footer>
      )}
    </section>
  );
}

/** 받은 훈장 줄 */
export function MedalRow({ items, profile }: { items: JourneyItem[]; profile: Profile }) {
  const all = badgesOf(items, profile);
  const earned = all.filter((b) => b.earned);
  const shown = [...earned, ...all.filter((b) => !b.earned)].slice(0, 6);
  return (
    <div className="flex items-center gap-1.5" aria-label={`받은 훈장 ${earned.length}개, 전체 ${all.length}개`}>
      {shown.map((b) => (
        <span key={b.id} title={b.earned ? `${b.name}: ${b.line}` : `아직: ${b.line}`}>
          <Medal earned={b.earned} size={26} />
        </span>
      ))}
      <span className="ml-1 text-[13px] font-bold text-fg-2">
        훈장 {earned.length}/{all.length}
      </span>
    </div>
  );
}

/** 채팅 옆 '나의 전역 작전도' */
export function JourneyPanel({ journey, profile, onOpen }: { journey: Journey; profile: Profile; onOpen: () => void }) {
  return (
    <div className="relative grid content-start gap-4">
      <Stamp className="absolute -top-9 -right-6 -rotate-[8deg]">임무 수행 중</Stamp>
      <h2 className="font-stencil text-[23px] leading-tight font-normal">나의 전역 작전도</h2>
      <RankCard items={journey.items} />
      <RankTrack items={journey.items} />
      <MissionList journey={journey} profile={profile} limit={5} onOpen={onOpen} />
      <MedalRow items={journey.items} profile={profile} />
    </div>
  );
}
