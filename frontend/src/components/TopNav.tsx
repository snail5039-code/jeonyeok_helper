"use client";

import { BookOpen, Building2, ChevronDown, Map, MessageSquare, Moon, Plus, Sun, UserRound, UserRoundPen } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { levelOf, progress } from "@/lib/journey";
import { SERVICE_TYPE_LABELS, type JourneyItem, type Profile } from "@/lib/types";

import { Mascot } from "./Doodle";

const SHORTCUTS = [
  { icon: BookOpen, label: "규정 찾기", ask: "전역자 지원과 관련된 주요 법령을 알려주세요" },
  { icon: Building2, label: "기관 안내", ask: "전역 후 혜택을 신청하거나 문의할 수 있는 기관을 알려주세요" },
];

const PROFILE_ROWS: [keyof Profile, string, (v: NonNullable<Profile[keyof Profile]>) => string][] = [
  ["service_type", "복무 형태", (v) => SERVICE_TYPE_LABELS[v as keyof typeof SERVICE_TYPE_LABELS] ?? String(v)],
  ["service_years", "복무 기간", (v) => `${v}년`],
  ["discharge_date", "전역일", String],
  ["region", "지역", String],
];

/** 위에 늘 보이는 내 조건: 병사 · 서울 · 25년 전역 */
export function profileSummary(p: Profile): string {
  const type = p.service_type && SERVICE_TYPE_LABELS[p.service_type].replace("의무복무 ", "");
  const year = p.discharge_date?.match(/^\d{4}/)?.[0];
  const parts = [type, p.region?.split(" ")[0], year && `${year.slice(2)}년 전역`].filter(Boolean);
  return parts.length ? parts.join(" · ") : "내 조건 알려 주기";
}

function ProfileDetails({ profile }: { profile: Profile }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[13px]">
      {PROFILE_ROWS.map(([key, label, format]) => {
        const value = profile[key];
        const known = value !== undefined && value !== null && value !== "";
        return (
          <div key={key} className="contents">
            <dt className="text-fg-3">{label}</dt>
            <dd className={`text-right ${known ? "font-semibold" : "text-fg-3"}`}>{known ? format(value) : "-"}</dd>
          </div>
        );
      })}
    </dl>
  );
}

/** 바깥을 누르거나 Esc를 누르면 닫히는 열림 상태 */
function useDismissable() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return [open, setOpen, ref] as const;
}

export type View = "home" | "chat" | "journey" | "profile";

interface Props {
  view: View;
  profile: Profile;
  journey: JourneyItem[];
  demo: boolean;
  dark: boolean;
  onToggleTheme: () => void;
  onHome: () => void;
  onChat: () => void;
  onJourney: () => void;
  onProfile: () => void;
  onAsk: (text: string) => void;
}

export function TopNav({ view, profile, journey, demo, dark, onToggleTheme, onHome, onChat, onJourney, onProfile, onAsk }: Props) {
  const [open, setOpen, ref] = useDismissable();
  const p = progress(journey);
  const rank = levelOf(journey).rank;

  const link = (on: boolean) =>
    `inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-[14.5px] font-bold ${
      on ? "bg-olive text-olive-ink shadow-[inset_0_-3px_0_var(--olive-dark)]" : "text-fg-2 hover:bg-olive/10 hover:text-fg"
    }`;

  return (
    <header className="relative z-20 shrink-0 border-b-[3px] border-olive-dark bg-[linear-gradient(#f3ead2,#e9dfc0)] shadow-[0_3px_0_rgb(0_0_0_/_0.2)] dark:bg-[linear-gradient(#2c3122,#23271b)]">
      <div className="mx-auto flex h-[60px] max-w-[1320px] items-center gap-3 px-3 sm:px-6">
        <button
          type="button"
          onClick={onHome}
          aria-label="전역도우미 처음으로"
          className="font-stencil flex shrink-0 -rotate-2 items-center gap-2 rounded-[10px_22px_22px_10px] border-[2.5px] border-[#1f2416] bg-[linear-gradient(135deg,#ececE6,#bcbdb3)] py-1 pr-3.5 pl-2.5 text-[19px] text-[#1f2416] shadow-[3px_3px_0_var(--ink)] sm:text-[21px]"
        >
          <span aria-hidden className="size-2 rounded-full border-2 border-[#1f2416] bg-[#f3ead2]" />
          전역도우미
        </button>

        <nav className="ml-2 hidden items-center gap-0.5 lg:flex" aria-label="메뉴">
          <button
            type="button"
            onClick={onChat}
            aria-current={view === "home" || view === "chat" ? "page" : undefined}
            className={link(view === "home" || view === "chat")}
          >
            <MessageSquare className="size-4" strokeWidth={2.2} />
            작전실
          </button>
          <button type="button" onClick={onJourney} aria-current={view === "journey" ? "page" : undefined} className={link(view === "journey")}>
            <Map className="size-4" strokeWidth={2.2} />
            작전도
            {p.total > 0 && (
              <span className="rounded-full border-[1.5px] border-[#1f2416] bg-[#ffe066] px-1.5 text-[11.5px] leading-[17px] font-extrabold text-[#1f2416]">
                {rank} {p.coreDone}/{p.coreTotal}
              </span>
            )}
          </button>
          <button type="button" onClick={onProfile} aria-current={view === "profile" ? "page" : undefined} className={link(view === "profile")}>
            <UserRound className="size-4" strokeWidth={2.2} />내 정보
          </button>
          {SHORTCUTS.map(({ icon: Icon, label, ask }) => (
            <button key={label} type="button" onClick={() => onAsk(ask)} className={link(false)}>
              <Icon className="size-4" strokeWidth={2.2} />
              {label}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex min-w-0 items-center gap-1.5 sm:gap-2">
          {demo && (
            <span title="Gemini 키가 없어 예시 응답을 보여줘요" className="rounded-full bg-warn-soft px-2.5 py-1 text-xs font-bold whitespace-nowrap text-warn">
              데모
            </span>
          )}

          <div ref={ref} className="relative min-w-0">
            <button
              type="button"
              onClick={() => setOpen(!open)}
              aria-expanded={open}
              aria-label={`내 조건: ${profileSummary(profile)}`}
              className="inline-flex h-10 max-w-[240px] min-w-0 items-center gap-1.5 rounded-full border-2 border-ink bg-soft py-0 pr-2.5 pl-1 text-[13.5px] font-extrabold"
            >
              <span className="grid size-7 shrink-0 place-items-end overflow-hidden rounded-full bg-sunken">
                <Mascot rank={rank} size={26} />
              </span>
              <span className="truncate">{profileSummary(profile)}</span>
              <ChevronDown className="size-3.5 shrink-0" />
            </button>
            {open && (
              <div className="absolute right-0 mt-2 w-64 rounded-xl border-2 border-ink bg-soft p-4 shadow-[4px_4px_0_var(--olive-dark)]">
                <div className="mb-3 flex items-center justify-between text-[13px] font-bold">
                  내 조건 <span className="text-xs font-medium text-fg-3">대화하거나 직접 적어요</span>
                </div>
                <ProfileDetails profile={profile} />
                <button
                  type="button"
                  onClick={() => {
                    setOpen(false);
                    onProfile();
                  }}
                  className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-lg border-2 border-edge py-2 text-[13px] font-bold text-fg-2 hover:border-ink"
                >
                  <UserRoundPen className="size-4" />
                  자세히 적기
                </button>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={onHome}
            className="hidden h-10 shrink-0 items-center gap-1 rounded-[10px] border-2 border-edge bg-soft px-3 text-[13.5px] font-bold text-fg-2 hover:border-ink md:inline-flex"
          >
            <Plus className="size-4" strokeWidth={2.4} />새 대화
          </button>
          <button
            type="button"
            onClick={onToggleTheme}
            aria-label={dark ? "밝은 화면으로" : "어두운 화면으로"}
            className="grid size-10 shrink-0 place-items-center rounded-[10px] text-fg-2 hover:bg-olive/10 hover:text-fg"
          >
            {dark ? <Sun className="size-[18px]" /> : <Moon className="size-[18px]" />}
          </button>
        </div>
      </div>
    </header>
  );
}

/** 좁은 화면: 아래 탭바 */
export function MobileTabs({
  view,
  journey,
  onChat,
  onJourney,
  onProfile,
  onHome,
}: {
  view: View;
  journey: JourneyItem[];
  onChat: () => void;
  onJourney: () => void;
  onProfile: () => void;
  onHome: () => void;
}) {
  const p = progress(journey);
  const rank = levelOf(journey).rank;
  const tab = (on: boolean) => `grid flex-1 justify-items-center gap-0.5 py-1 text-[11.5px] font-bold ${on ? "text-olive" : "text-fg-3"}`;
  return (
    <nav
      aria-label="메뉴"
      className="fixed inset-x-0 bottom-0 z-30 flex border-t-[3px] border-olive-dark bg-[#f3ead2] px-1 pt-1.5 pb-[calc(6px+env(safe-area-inset-bottom,0px))] lg:hidden dark:bg-[#2c3122]"
    >
      <button type="button" onClick={onChat} aria-current={view === "home" || view === "chat" ? "page" : undefined} className={tab(view === "home" || view === "chat")}>
        <MessageSquare className="size-[22px]" strokeWidth={2.2} />
        작전실
      </button>
      <button type="button" onClick={onJourney} aria-current={view === "journey" ? "page" : undefined} className={tab(view === "journey")}>
        <Map className="size-[22px]" strokeWidth={2.2} />
        {p.total ? (
          <span className="rounded-full border-[1.5px] border-[#1f2416] bg-[#ffe066] px-1.5 text-[10.5px] leading-[15px] text-[#1f2416]">
            {rank} {p.coreDone}/{p.coreTotal}
          </span>
        ) : (
          "작전도"
        )}
      </button>
      <button type="button" onClick={onProfile} aria-current={view === "profile" ? "page" : undefined} className={tab(view === "profile")}>
        <UserRound className="size-[22px]" strokeWidth={2.2} />내 정보
      </button>
      <button type="button" onClick={onHome} className={tab(false)}>
        <Plus className="size-[22px]" strokeWidth={2.2} />새 대화
      </button>
    </nav>
  );
}
