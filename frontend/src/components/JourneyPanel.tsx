"use client";

import { ArrowRight } from "lucide-react";
import { useState } from "react";

import { badges as badgesOf, currentStage, levelOf, progress, STAGE_BY_KEY } from "@/lib/journey";
import type { Profile, StageKey } from "@/lib/types";

import { ItemCard, JourneyHero, StageTrack } from "./JourneyParts";
import { BadgeShelf } from "./JourneyView";
import type { Journey } from "./useJourney";

interface Props {
  journey: Journey;
  profile: Profile;
  onAsk: (question: string) => void;
  onOpen: () => void;
}

/** 채팅 옆 로드맵 패널: 대화하면 할 일이 담기고, 지금 단계의 할 일을 바로 체크한다. */
export function JourneyPanel({ journey, profile, onAsk, onOpen }: Props) {
  const { items, fresh, toggle } = journey;
  const [picked, setPicked] = useState<StageKey | null>(null);
  const stage = picked ?? currentStage(items);
  // 방금 담긴 할 일이 있으면 그것부터 보여 준다
  const freshItems = items.filter((i) => fresh.has(i.id));
  const list = freshItems.length ? freshItems : items.filter((i) => i.stage === stage);

  return (
    <aside aria-label="내 전역 로드맵" className="sticky top-0 grid max-h-[calc(100dvh-64px-150px)] content-start gap-4 overflow-y-auto pr-1.5 pb-2 [scrollbar-width:thin]">
      <JourneyHero items={items} compact />
      {items.length ? (
        <>
          <StageTrack items={items} selected={stage} onSelect={setPicked} />
          <section className="grid gap-2">
            <h3 className="font-fun text-[16px]">
              {freshItems.length ? "✨ 방금 로드맵에 담았어요" : stage ? `${STAGE_BY_KEY[stage].emoji} ${STAGE_BY_KEY[stage].title}` : ""}
            </h3>
            <ul className="grid gap-2">
              {list.slice(0, 4).map((item) => (
                <ItemCard key={item.id} item={item} fresh={fresh.has(item.id)} compact onToggle={toggle} onAsk={onAsk} />
              ))}
            </ul>
          </section>
          <BadgeShelf badges={badgesOf(items, profile)} compact />
        </>
      ) : (
        <p className="rounded-xl border-2 border-dashed border-line-strong p-3 text-[13px] leading-relaxed text-fg-2">
          답변에 나온 할 일(신청, 등록, 확인)이 여기 자동으로 담겨요. 하나씩 끝내면 계급이 올라감!
        </p>
      )}
      <button
        type="button"
        onClick={onOpen}
        className="inline-flex items-center justify-center gap-1 rounded-xl border border-line-strong py-2 text-[13.5px] font-semibold text-fg-2 hover:border-fg-3"
      >
        로드맵 전체 보기 <ArrowRight className="size-4" />
      </button>
    </aside>
  );
}

/** 모바일·좁은 화면: 채팅 위쪽의 작은 진행 칩. 누르면 로드맵 화면으로. */
export function JourneyChip({ journey, onOpen }: { journey: Journey; onOpen: () => void }) {
  const p = progress(journey.items);
  const freshCount = journey.fresh.size;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="font-fun inline-flex h-9 items-center gap-2 rounded-full border-2 border-[#1b1b1b] bg-paper px-3 text-[14px] text-paper-ink shadow-[2px_2px_0_var(--ink)]"
    >
      🪖 {levelOf(p.percent).rank} · {p.done}/{p.total}
      {freshCount > 0 && <span className="rounded-full bg-accent px-1.5 text-[12px] text-accent-ink">+{freshCount}</span>}
      <ArrowRight className="size-3.5" />
    </button>
  );
}
