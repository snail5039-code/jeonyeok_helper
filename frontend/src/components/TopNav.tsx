"use client";

import { BookOpen, Building2, ChevronDown, Gift, House, Menu, Moon, Plus, Sun, UserRound, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { SERVICE_TYPE_LABELS, type Profile } from "@/lib/types";

import { LogoMark } from "./Logo";

const SHORTCUTS = [
  { icon: Gift, label: "내 혜택", ask: "지금 제 상황에서 받을 수 있는 혜택을 모두 알려주세요" },
  { icon: BookOpen, label: "규정 찾기", ask: "전역자 지원과 관련된 주요 법령을 알려주세요" },
  { icon: Building2, label: "기관 안내", ask: "전역 후 혜택을 신청하거나 문의할 수 있는 기관을 알려주세요" },
];

const PROFILE_ROWS: [keyof Profile, string, (v: NonNullable<Profile[keyof Profile]>) => string][] = [
  ["service_type", "복무 형태", (v) => SERVICE_TYPE_LABELS[v as keyof typeof SERVICE_TYPE_LABELS] ?? String(v)],
  ["service_years", "복무 기간", (v) => `${v}년`],
  ["discharge_date", "전역일", String],
  ["region", "지역", String],
];

function profileSummary(p: Profile): string {
  const parts = [p.service_type && SERVICE_TYPE_LABELS[p.service_type], p.region].filter(Boolean);
  return parts.length ? parts.join(" · ") : "내 복무 정보";
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
            <dd className={`text-right ${known ? "font-semibold" : "text-fg-3"}`}>
              {known ? format(value) : key === "service_type" ? "아직 몰라요" : "-"}
            </dd>
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

interface Props {
  isHome: boolean;
  profile: Profile;
  demo: boolean;
  dark: boolean;
  onToggleTheme: () => void;
  onHome: () => void;
  onAsk: (text: string) => void;
}

export function TopNav({ isHome, profile, demo, dark, onToggleTheme, onHome, onAsk }: Props) {
  const [profileOpen, setProfileOpen, profileRef] = useDismissable();
  const [mobileOpen, setMobileOpen, mobileRef] = useDismissable();

  const navLink = "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-fg-2 hover:bg-sunken hover:text-fg";
  const iconButton = "grid size-9 place-items-center rounded-lg text-fg-2 hover:bg-sunken hover:text-fg";

  const go = (fn: () => void) => () => {
    setMobileOpen(false);
    fn();
  };

  return (
    <header ref={mobileRef} className="relative z-20 shrink-0 border-b border-line bg-bg">
      <div className="mx-auto flex h-16 max-w-[1120px] items-center gap-2 px-4 lg:px-8">
        <button type="button" onClick={onHome} className="mr-4 flex items-center gap-2.5 text-[17px] font-bold tracking-[-0.03em] whitespace-nowrap">
          <LogoMark />
          전역도우미
        </button>

        <nav className="hidden items-center gap-0.5 md:flex" aria-label="메뉴">
          <button type="button" onClick={onHome} className={`${navLink} ${isHome ? "bg-sunken text-fg" : ""}`}>
            <House className="size-4" strokeWidth={1.8} />홈
          </button>
          {SHORTCUTS.map(({ icon: Icon, label, ask }) => (
            <button key={label} type="button" onClick={() => onAsk(ask)} className={navLink}>
              <Icon className="size-4" strokeWidth={1.8} />
              {label}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-1.5">
          {demo && (
            <span title="Gemini 키가 없어 예시 응답을 보여줘요" className="rounded-full bg-warn-soft px-2.5 py-1 text-xs font-bold whitespace-nowrap text-warn">
              데모 모드
            </span>
          )}

          <div ref={profileRef} className="relative hidden md:block">
            <button
              type="button"
              onClick={() => setProfileOpen(!profileOpen)}
              aria-expanded={profileOpen}
              className={`inline-flex h-9 items-center gap-1.5 rounded-full border px-3 text-[13px] font-semibold ${
                profile.service_type ? "border-accent bg-accent-soft text-accent" : "border-line-strong text-fg-2"
              }`}
            >
              <UserRound className="size-[15px]" strokeWidth={1.8} />
              {profileSummary(profile)}
              <ChevronDown className="size-3.5" />
            </button>
            {profileOpen && (
              <div className="absolute right-0 mt-2 w-64 rounded-xl border border-line bg-bg p-4 shadow-card">
                <div className="mb-3 flex items-center justify-between text-[13px] font-semibold">
                  내 복무 정보 <span className="text-xs font-medium text-fg-3">대화하면 채워져요</span>
                </div>
                <ProfileDetails profile={profile} />
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={onHome}
            className="hidden h-9 items-center gap-1.5 rounded-lg bg-accent px-3 text-[13px] font-semibold text-accent-ink md:inline-flex"
          >
            <Plus className="size-[15px]" />새 질문
          </button>
          <button type="button" onClick={onToggleTheme} aria-label="화면 테마 바꾸기" className={iconButton}>
            {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
          <button
            type="button"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label={mobileOpen ? "메뉴 닫기" : "메뉴 열기"}
            aria-expanded={mobileOpen}
            className={`${iconButton} md:hidden`}
          >
            {mobileOpen ? <X className="size-[18px]" /> : <Menu className="size-[18px]" />}
          </button>
        </div>
      </div>

      {/* 모바일: 위에서 펼쳐지는 메뉴 */}
      {mobileOpen && (
        <div className="absolute inset-x-0 top-full grid gap-4 border-b border-line bg-bg px-4 pt-3 pb-5 shadow-card md:hidden">
          <nav className="grid gap-0.5" aria-label="메뉴">
            <button type="button" onClick={go(onHome)} className={navLink}>
              <House className="size-4" strokeWidth={1.8} />홈 · 새 질문
            </button>
            {SHORTCUTS.map(({ icon: Icon, label, ask }) => (
              <button key={label} type="button" onClick={go(() => onAsk(ask))} className={navLink}>
                <Icon className="size-4" strokeWidth={1.8} />
                {label}
              </button>
            ))}
          </nav>
          <section className="rounded-xl border border-line p-3.5">
            <div className="mb-2.5 text-[13px] font-semibold">내 복무 정보</div>
            <ProfileDetails profile={profile} />
          </section>
        </div>
      )}
    </header>
  );
}
