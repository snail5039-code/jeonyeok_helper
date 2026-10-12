"use client";

import { MessageCircle, RefreshCw, UserRoundPen, Wand2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { badges as badgesOf, byStage, type Badge } from "@/lib/journey";
import type { Profile, StageKey } from "@/lib/types";

import { Sticker } from "./Doodle";
import { ItemCard, JourneyHero, StageTrack } from "./JourneyParts";
import type { Journey } from "./useJourney";

interface Props {
  journey: Journey;
  profile: Profile;
  onAsk: (question: string) => void;
  onProfile: () => void;
}

/** '내 로드맵' 전체 화면: 마스코트·계급, 단계 지도, 스티커, 단계별 할 일. */
export function JourneyView({ journey, profile, onAsk, onProfile }: Props) {
  const { items, fresh, generating, error, toggle, remove, generate } = journey;
  const groups = byStage(items);
  const [notice, setNotice] = useState("");

  const fill = async () => {
    const added = await generate();
    setNotice(added ? `${added}개를 새로 담았어요. 가 보자고~` : "새로 담을 할 일이 없었어요. 이미 다 담겨 있음 ㅇㅇ");
  };

  const goTo = (key: StageKey) => document.getElementById(`stage-${key}`)?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <main className="flex-1 overflow-y-auto">
      <div className="mx-auto grid max-w-[820px] grid-cols-[minmax(0,1fr)] gap-6 px-4 pt-7 pb-16 lg:pt-10">
        <header className="grid gap-1.5">
          <h1 className="font-fun text-[30px] leading-tight md:text-[36px]">내 전역 로드맵 🗺️</h1>
          <p className="text-[15px] text-fg-2">
            물어볼수록 할 일이 쌓이고, 하나씩 끝낼 때마다 계급이 올라가요. 목표는 민간인 완성!
          </p>
        </header>

        <JourneyHero items={items} />

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={fill}
            disabled={generating || !profile.service_type}
            title={profile.service_type ? "" : "내 정보에서 복무 형태를 먼저 골라 주세요"}
            className="inline-flex h-10 items-center gap-1.5 rounded-xl border-[2.5px] border-[#1b1b1b] bg-[#ffe066] px-3.5 text-[14px] font-bold text-[#1b1b1b] shadow-[3px_3px_0_var(--ink)] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none disabled:opacity-50"
          >
            {generating ? <RefreshCw className="size-4 animate-spin" /> : <Wand2 className="size-4" />}
            {generating ? "할 일 모으는 중… (20초쯤)" : items.length ? "내 정보로 더 채우기" : "내 정보로 한 번에 채우기"}
          </button>
          <button
            type="button"
            onClick={onProfile}
            className="inline-flex h-10 items-center gap-1.5 rounded-xl border border-line-strong px-3.5 text-[14px] font-semibold text-fg-2 hover:border-fg-3"
          >
            <UserRoundPen className="size-4" />내 정보 {profile.service_type ? "고치기" : "입력하기"}
          </button>
        </div>
        {(notice || error) && (
          <p role="status" className={`-mt-3 text-[13.5px] font-semibold ${error ? "text-warn" : "text-fg-2"}`}>
            {error || notice}
          </p>
        )}

        {items.length ? (
          <>
            <section className="rounded-2xl border border-line p-4">
              <StageTrack items={items} onSelect={goTo} />
            </section>
            <BadgeShelf badges={badgesOf(items, profile)} />
            <ol className="grid grid-cols-[minmax(0,1fr)] gap-7">
              {groups.map(({ stage, items: list }) => (
                <li key={stage.key} id={`stage-${stage.key}`} className="grid scroll-mt-4 grid-cols-[minmax(0,1fr)] gap-3">
                  <h2 className="flex items-center gap-2 text-[18px] font-bold">
                    <span className="font-fun text-[22px]">
                      {stage.emoji} {stage.title}
                    </span>
                    <span className="text-[13px] font-semibold text-fg-3 tabular-nums">
                      {list.filter((i) => i.done).length}/{list.length}
                    </span>
                  </h2>
                  <ul className="grid grid-cols-[minmax(0,1fr)] gap-2.5">
                    {list.map((item) => (
                      <ItemCard
                        key={item.id}
                        item={item}
                        fresh={fresh.has(item.id)}
                        onToggle={toggle}
                        onAsk={onAsk}
                        onRemove={remove}
                      />
                    ))}
                  </ul>
                </li>
              ))}
            </ol>
            <p className="text-[13px] text-fg-3">정확한 자격과 기한은 소관 기관에 꼭 확인하세요.</p>
          </>
        ) : (
          <section className="grid justify-items-start gap-3 rounded-2xl border-2 border-dashed border-line-strong p-5">
            <p className="font-fun text-[20px]">텅~ 아직 할 일이 없어요</p>
            <p className="text-[14.5px] text-fg-2">
              내 정보를 적고 위의 노란 버튼을 누르거나, 채팅에서 궁금한 걸 물어보세요. 답변에 나온 할 일이 여기 자동으로
              담겨요.
            </p>
            <button
              type="button"
              onClick={() => onAsk("작년에 전역했는데 지금 뭐부터 챙겨야 해요?")}
              className="inline-flex items-center gap-1.5 text-[14px] font-semibold text-accent"
            >
              <MessageCircle className="size-4" />
              “전역했는데 뭐부터 챙겨야 해요?” 물어보기
            </button>
          </section>
        )}
      </div>
    </main>
  );
}

/** 스티커 모음. 새로 받은 스티커는 튀어나오고 잠깐 축하 문구가 뜬다. */
export function BadgeShelf({ badges, compact = false }: { badges: Badge[]; compact?: boolean }) {
  const [fresh, setFresh] = useState<string | null>(null);
  const earned = badges.filter((b) => b.earned);
  const earnedKey = earned.map((b) => b.id).join(",");
  const seen = useRef<Set<string> | null>(null);

  useEffect(() => {
    const ids = new Set(earnedKey ? earnedKey.split(",") : []);
    // 처음 그릴 때 이미 받은 것은 축하하지 않는다
    const got = seen.current ? [...ids].find((id) => !seen.current!.has(id)) : undefined;
    seen.current = ids;
    if (!got) return;
    const show = window.setTimeout(() => setFresh(got), 0);
    const hide = window.setTimeout(() => setFresh(null), 4000);
    return () => {
      clearTimeout(show);
      clearTimeout(hide);
    };
  }, [earnedKey]);

  const freshBadge = badges.find((b) => b.id === fresh);
  const shown = compact ? [...earned, ...badges.filter((b) => !b.earned)].slice(0, 4) : badges;
  return (
    <section className="grid gap-3">
      <h2 className="flex items-baseline justify-between">
        <span className="font-fun text-[18px]">내 스티커</span>
        <span className="text-[13px] font-semibold text-fg-3 tabular-nums">
          {earned.length}/{badges.length}
        </span>
      </h2>
      {freshBadge && (
        <p role="status" className="font-fun animate-pop justify-self-start rounded-full border-2 border-[#1b1b1b] bg-[#ffe066] px-3 py-1 text-[15px] text-[#1b1b1b]">
          🎉 ‘{freshBadge.name}’ 스티커 획득! {freshBadge.line}
        </p>
      )}
      <div className={`flex flex-wrap gap-x-2 gap-y-3 ${compact ? "justify-between" : ""}`}>
        {shown.map((b) => (
          <Sticker key={b.id} badge={b} fresh={b.id === fresh} />
        ))}
      </div>
    </section>
  );
}
