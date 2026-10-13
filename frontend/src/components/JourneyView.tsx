"use client";

import { MessageCircle, RefreshCw, UserRoundPen, Wand2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { badges as badgesOf, byStage, type Badge } from "@/lib/journey";
import type { Profile, StageKey } from "@/lib/types";

import { Book, BookTitle, Stamp } from "./Book";
import { MedalCard } from "./Doodle";
import { RankCard, RankTrack } from "./JourneyPanel";
import { ItemCard, StageTrack } from "./JourneyParts";
import { StageIcon } from "./StageIcon";
import type { Journey } from "./useJourney";

interface Props {
  journey: Journey;
  profile: Profile;
  onAsk: (question: string) => void;
  onProfile: () => void;
}

/** '나의 전역 작전도' 전체 화면: 계급, 단계 지도, 훈장, 단계별 임무 */
export function JourneyView({ journey, profile, onAsk, onProfile }: Props) {
  const { items, fresh, generating, error, toggle, remove, generate } = journey;
  const groups = byStage(items);
  const [notice, setNotice] = useState("");

  const fill = async () => {
    const added = await generate();
    setNotice(added ? `임무 ${added}개를 새로 담았어요.` : "새로 담을 임무가 없었어요. 이미 다 담겨 있어요.");
  };

  const goTo = (key: StageKey) => document.getElementById(`stage-${key}`)?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <main className="flex-1 overflow-y-auto px-2.5 pt-4 pb-6 sm:px-5 sm:pt-6 lg:pb-12">
      <Book as="div" rings={14} className="mx-auto grid max-w-[880px] grid-cols-[minmax(0,1fr)] gap-6">
        <Stamp className="absolute -top-3 right-4 rotate-[7deg] sm:right-8">임무 수행 중</Stamp>
        <header className="grid gap-2">
          <div>
            <BookTitle>나의 전역 작전도</BookTitle>
          </div>
          <p className="text-[15px] text-fg-2">핵심 임무(별표)를 모두 끝내면 민간인이 돼요. 하나씩 끝낼 때마다 계급이 올라가요.</p>
        </header>

        <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] md:items-center">
          <RankCard items={items} />
          <RankTrack items={items} />
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={fill}
            disabled={generating || !profile.service_type}
            title={profile.service_type ? "" : "내 정보에서 복무 형태를 먼저 골라 주세요"}
            className="inline-flex h-10 items-center gap-1.5 rounded-[10px] border-[2.5px] border-[#1f2416] bg-done px-3.5 text-[14px] font-extrabold text-[#1f2416] shadow-[3px_3px_0_var(--ink)] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none disabled:opacity-50"
          >
            {generating ? <RefreshCw className="size-4 animate-spin" /> : <Wand2 className="size-4" />}
            {generating ? "임무 모으는 중… (20초쯤)" : items.length ? "내 정보로 임무 더 찾기" : "내 정보로 작전도 만들기"}
          </button>
          <button
            type="button"
            onClick={onProfile}
            className="inline-flex h-10 items-center gap-1.5 rounded-[10px] border-2 border-edge bg-soft px-3.5 text-[14px] font-bold text-fg-2 hover:border-ink"
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
            <section className="rounded-xl border-2 border-edge bg-soft p-4">
              <StageTrack items={items} onSelect={goTo} />
            </section>
            <BadgeShelf badges={badgesOf(items, profile)} />
            <ol className="grid grid-cols-[minmax(0,1fr)] gap-7">
              {groups.map(({ stage, items: list }) => (
                <li key={stage.key} id={`stage-${stage.key}`} className="grid scroll-mt-4 grid-cols-[minmax(0,1fr)] gap-3">
                  <h2 className="flex items-center gap-2">
                    <span className="grid size-8 place-items-center rounded-lg border-2 border-ink bg-soft">
                      <StageIcon stage={stage.key} className="size-[18px]" />
                    </span>
                    <span className="font-stencil text-[21px] font-normal">{stage.title}</span>
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
                        dischargeDate={profile.discharge_date}
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
          <section className="grid justify-items-start gap-3 rounded-xl border-2 border-dashed border-edge p-5">
            <p className="font-stencil text-[20px]">아직 임무가 없어요</p>
            <p className="text-[14.5px] text-fg-2">
              위의 초록 버튼을 누르거나, 작전실에서 전역이와 대화해 보세요. 대화에서 고른 임무가 여기 담겨요.
            </p>
            <button
              type="button"
              onClick={() => onAsk("전역했는데 이제 뭐부터 해야 돼요?")}
              className="inline-flex items-center gap-1.5 text-[14px] font-bold text-accent"
            >
              <MessageCircle className="size-4" />
              “전역했는데 뭐부터 해야 돼요?” 물어보기
            </button>
          </section>
        )}
      </Book>
    </main>
  );
}

/** 훈장 모음. 새로 받은 훈장은 튀어나오고 잠깐 축하 문구가 뜬다. */
export function BadgeShelf({ badges }: { badges: Badge[] }) {
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
  return (
    <section className="grid gap-3">
      <h2 className="flex items-baseline justify-between">
        <span className="font-stencil text-[19px] font-normal">훈장</span>
        <span className="text-[13px] font-semibold text-fg-3 tabular-nums">
          {earned.length}/{badges.length}
        </span>
      </h2>
      {freshBadge && (
        <p
          role="status"
          className="animate-pop justify-self-start rounded-full border-2 border-[#1f2416] bg-[#ffe066] px-3 py-1 text-[14.5px] font-bold text-[#1f2416]"
        >
          ‘{freshBadge.name}’ 훈장을 받았어요. {freshBadge.line}
        </p>
      )}
      <div className="flex flex-wrap gap-x-2 gap-y-3">
        {badges.map((b) => (
          <MedalCard key={b.id} badge={b} fresh={b.id === fresh} />
        ))}
      </div>
    </section>
  );
}
