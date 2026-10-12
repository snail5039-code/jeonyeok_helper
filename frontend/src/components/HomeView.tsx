"use client";

import {
  ArrowRight,
  BookOpen,
  Briefcase,
  Building2,
  Check,
  GraduationCap,
  IdCard,
  Landmark,
  ShieldCheck,
  User,
  UserRoundPen,
} from "lucide-react";
import { useState } from "react";

import { Composer } from "./Composer";
import { Mascot } from "./Doodle";

const SERVICE_CHOICES = ["병사", "부사관", "장교", "보훈대상자"];

const POPULAR = [
  { icon: Landmark, q: "군복무 크레딧은 따로 신청해야 하나요?", tag: "연금" },
  { icon: Briefcase, q: "10년 복무하고 전역하면 전직 지원을 받을 수 있나요?", tag: "취업 · 중·장기 복무" },
  { icon: GraduationCap, q: "복학하면 받을 수 있는 학비 지원이 있나요?", tag: "교육" },
  { icon: IdCard, q: "예비군은 전역 후 몇 년 차까지 하나요?", tag: "병역" },
];

const TIMELINE = [
  { when: "전역 전", what: "전직 교육·상담", where: "제대군인지원센터" },
  { when: "전역 직후", what: "예비군 편성 확인", where: "병무청" },
  { when: "구직할 때", what: "국민취업지원제도", where: "고용24" },
  { when: "복학할 때", what: "국가장학금·학자금", where: "한국장학재단" },
  { when: "연금 받을 때", what: "군복무 크레딧 반영", where: "국민연금공단" },
];

const TRUST = [
  { icon: BookOpen, title: "근거 조문 표시", body: "답변마다 어떤 법 몇 조인지 보여드려요" },
  { icon: Building2, title: "신청처까지 연결", body: "기관 사이트와 대표번호를 함께 안내해요" },
  { icon: User, title: "로그인 없이 사용", body: "복무 정보는 상담에만 쓰여요" },
];

interface Props {
  onAsk: (text: string) => void;
  onRoadmap: () => void;
  onProfile: () => void;
}

export function HomeView({ onAsk, onRoadmap, onProfile }: Props) {
  const [serviceType, setServiceType] = useState<string | null>(null);

  // 고른 복무 형태를 질문에 붙여 보낸다 (이미 말했으면 그대로).
  const askWithType = (text: string) =>
    onAsk(serviceType && !text.includes(serviceType) ? `${text} (복무 형태: ${serviceType})` : text);

  return (
    <main className="flex-1 overflow-y-auto">
      <div className="mx-auto grid max-w-[760px] gap-8 px-4 pt-7 pb-8 md:gap-10 md:px-6 md:pt-[72px] md:pb-12">
        <section className="grid gap-3.5">
          <span className="inline-flex items-center gap-1.5 justify-self-start rounded-full bg-accent-soft px-2.5 py-1 text-[12.5px] font-semibold text-accent">
            <ShieldCheck className="size-[15px]" strokeWidth={1.8} />
            법령 원문과 정부24 혜택 정보로 답해요
          </span>
          <h1 className="text-[26px] leading-[1.3] font-bold tracking-[-0.035em] text-balance md:text-[34px]">
            전역 후 챙길 혜택,
            <br />
            상황만 말해 주세요
          </h1>
          <p className="text-base text-fg-2">
            복무 형태와 사는 곳을 알려주시면 받을 수 있는 혜택과 근거 조문, 신청할 곳까지 찾아드려요.
          </p>
          <Composer
            id="home-input"
            rows={2}
            placeholder="예) 작년에 병장으로 만기 전역했고 서울 살아요. 받을 수 있는 혜택 있어요?"
            onSubmit={askWithType}
            footer={
              <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="복무 형태">
                <span className="mr-0.5 text-[12.5px] text-fg-3">복무 형태</span>
                {SERVICE_CHOICES.map((t) => {
                  const on = serviceType === t;
                  return (
                    <button
                      key={t}
                      type="button"
                      aria-pressed={on}
                      onClick={() => setServiceType(on ? null : t)}
                      className={`inline-flex h-[30px] items-center gap-1.5 rounded-full border px-[11px] text-[13px] font-medium ${
                        on ? "border-accent bg-accent-soft text-accent" : "border-line-strong bg-bg text-fg-2"
                      }`}
                    >
                      {on && <Check className="size-[14px]" strokeWidth={2.2} />}
                      {t}
                    </button>
                  );
                })}
              </div>
            }
          />
        </section>

        <div className="grid gap-3 md:grid-cols-2">
          <button
            type="button"
            onClick={onRoadmap}
            className="grid grid-cols-[48px_1fr] items-center gap-3 rounded-2xl border-[2.5px] border-[#1b1b1b] bg-paper px-4 py-3.5 text-left text-paper-ink shadow-[4px_4px_0_var(--ink)] transition-transform hover:-translate-y-0.5 active:translate-x-[2px] active:translate-y-[2px] active:shadow-none"
          >
            <Mascot rank="이병" size={48} />
            <span className="grid gap-0.5">
              <b className="font-fun text-[18px] leading-tight font-normal">내 전역 로드맵 🗺️</b>
              <span className="text-[13px] opacity-80">물어볼수록 할 일이 쌓이고, 끝낼수록 계급이 올라감</span>
            </span>
          </button>
          <button
            type="button"
            onClick={onProfile}
            className="grid grid-cols-[48px_1fr_auto] items-center gap-3 rounded-2xl border border-line bg-soft px-4 py-3.5 text-left hover:border-accent"
          >
            <span className="grid size-12 place-items-center rounded-xl bg-accent text-accent-ink">
              <UserRoundPen className="size-[22px]" strokeWidth={1.8} />
            </span>
            <span className="grid gap-0.5">
              <b className="text-[15px]">내 정보 자세히 적기</b>
              <span className="text-[13px] text-fg-2">복무·지역·목표를 적어 두면 더 딱 맞게 찾아요</span>
            </span>
            <ArrowRight className="size-5 text-fg-3" />
          </button>
        </div>

        <section>
          <h2 className="mb-3 text-[15px] font-bold">전역자들이 많이 물어봐요</h2>
          <div className="grid gap-2.5 md:grid-cols-2">
            {POPULAR.map(({ icon: Icon, q, tag }) => (
              <button
                key={q}
                type="button"
                onClick={() => askWithType(q)}
                className="grid grid-cols-[36px_1fr] items-start gap-3 rounded-xl border border-line bg-bg px-4 py-3.5 text-left hover:border-line-strong hover:bg-soft"
              >
                <span className="grid size-9 place-items-center rounded-[10px] bg-sunken text-fg-2">
                  <Icon className="size-[18px]" strokeWidth={1.8} />
                </span>
                <span>
                  <b className="block text-[14.5px] leading-[1.45] font-semibold">{q}</b>
                  <small className="text-[12.5px] text-fg-3">{tag}</small>
                </span>
              </button>
            ))}
          </div>
        </section>

        <section>
          <h2 className="mb-3 text-[15px] font-bold">시기별로 놓치기 쉬운 것</h2>
          <ol className="grid overflow-hidden rounded-xl border border-line md:grid-cols-5">
            {TIMELINE.map(({ when, what, where }) => (
              <li
                key={when}
                className="grid grid-cols-[92px_1fr] gap-x-3 gap-y-1 border-b border-line px-3.5 py-3.5 last:border-b-0 md:grid-cols-1 md:content-start md:border-r md:border-b-0 md:last:border-r-0"
              >
                <span className="row-span-2 self-center text-xs font-bold text-accent md:row-span-1">{when}</span>
                <b className="text-sm font-semibold">{what}</b>
                <span className="text-[12.5px] text-fg-3">{where}</span>
              </li>
            ))}
          </ol>
        </section>

        <section className="grid gap-4 border-t border-line pt-6 md:grid-cols-3">
          {TRUST.map(({ icon: Icon, title, body }) => (
            <div key={title} className="grid grid-cols-[20px_1fr] gap-2 text-[13px] text-fg-2">
              <Icon className="mt-0.5 size-[18px] text-accent" strokeWidth={1.8} />
              <span>
                <b className="block text-[13.5px] font-semibold text-fg">{title}</b>
                {body}
              </span>
            </div>
          ))}
        </section>
      </div>
    </main>
  );
}
