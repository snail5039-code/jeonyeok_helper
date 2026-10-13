"use client";

import { BookOpen, Briefcase, Building2, ChevronRight, GraduationCap, IdCard, Landmark, ShieldCheck } from "lucide-react";

import { greeting } from "@/lib/guide";
import type { JourneyItem, Profile, QuickReply } from "@/lib/types";

import { GuideBubble, QuickReplies, Say } from "./Guide";

const POPULAR = [
  { icon: Landmark, q: "군복무 크레딧은 따로 신청해야 하나요?", tag: "연금" },
  { icon: Briefcase, q: "10년 복무하고 전역하면 전직 지원을 받을 수 있나요?", tag: "취업 · 중·장기 복무" },
  { icon: GraduationCap, q: "복학하면 받을 수 있는 학비 지원이 있나요?", tag: "교육" },
  { icon: IdCard, q: "예비군은 전역 후 몇 년 차까지 하나요?", tag: "병역" },
];

const TRUST = [
  { icon: BookOpen, text: "답변마다 근거 조문" },
  { icon: Building2, text: "신청처·연락처까지" },
  { icon: ShieldCheck, text: "로그인 없이, 상담에만 사용" },
];

interface Props {
  profile: Profile;
  items: JourneyItem[];
  rank: string;
  ready: boolean;
  onAsk: (text: string) => void;
  onReply: (reply: QuickReply) => void;
}

/** 대화를 시작하기 전 작전실: 전역이가 먼저 말을 건다 (처음이면 복무 형태부터, 다시 오면 다음 임무) */
export function HomeView({ profile, items, rank, ready, onAsk, onReply }: Props) {
  const { say, replies } = greeting(profile, items);

  return (
    <div className="grid gap-7">
      {ready ? (
        <GuideBubble rank={rank} big>
          <Say big>{say}</Say>
          <QuickReplies replies={replies} onReply={onReply} />
        </GuideBubble>
      ) : (
        <div className="h-[110px]" aria-hidden />
      )}

      <section className="grid gap-2.5">
        <h2 className="font-stencil text-[17px] font-normal text-fg-2">전역자들이 많이 물어봐요</h2>
        <div className="grid gap-2 md:grid-cols-2">
          {POPULAR.map(({ icon: Icon, q, tag }) => (
            <button
              key={q}
              type="button"
              onClick={() => onAsk(q)}
              className="grid grid-cols-[34px_minmax(0,1fr)_auto] items-center gap-3 rounded-xl border-2 border-edge bg-soft px-3.5 py-3 text-left hover:border-ink"
            >
              <span className="grid size-[34px] place-items-center rounded-lg border-2 border-ink bg-bg text-fg">
                <Icon className="size-[18px]" strokeWidth={2.2} />
              </span>
              <span className="min-w-0">
                <b className="block text-[14.5px] leading-[1.45] font-bold">{q}</b>
                <small className="text-[12.5px] font-semibold text-fg-3">{tag}</small>
              </span>
              <ChevronRight className="size-4 text-fg-3" />
            </button>
          ))}
        </div>
      </section>

      <ul className="flex flex-wrap gap-x-5 gap-y-1.5 text-[13px] font-semibold text-fg-3">
        {TRUST.map(({ icon: Icon, text }) => (
          <li key={text} className="inline-flex items-center gap-1.5">
            <Icon className="size-4 text-olive" strokeWidth={2.2} />
            {text}
          </li>
        ))}
      </ul>
    </div>
  );
}
