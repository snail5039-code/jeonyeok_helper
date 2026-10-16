"use client";

import { ArrowUpRight } from "lucide-react";
import Image from "next/image";
import { useState } from "react";

import { dischargeMoment } from "@/lib/discharge";
import { greeting } from "@/lib/guide";
import type { JourneyItem, Profile, QuickReply } from "@/lib/types";

import { Composer } from "./Composer";
import { QuickReplies } from "./Guide";
import { StatusPanel } from "./StatusPanel";

type Moment = "before" | "after";
const QUESTIONS = [
  "전역하고 복학하면 받을 수 있는 학비 지원이 있나요?",
  "군복무 크레딧은 따로 신청해야 하나요?",
  "전역 전 취업 준비는 뭘 먼저 해야 하죠?",
];

interface Props {
  profile: Profile;
  items: JourneyItem[];
  ready: boolean;
  busy: boolean;
  onAsk: (text: string) => void;
  onReply: (reply: QuickReply) => void;
  onJourney: () => void;
  onProfile: () => void;
}

/** 자연어 질문이 중심인 첫 화면. 오른쪽 현황은 실제 내 정보·작전도로 채운다. */
export function HomeView({ profile, items, ready, busy, onAsk, onReply, onJourney, onProfile }: Props) {
  const [selectedMoment, setSelectedMoment] = useState<Moment | null>(null);
  const moment = selectedMoment ?? dischargeMoment(profile.discharge_date);

  const { replies } = greeting(profile, items);
  const before = moment === "before";
  const image = before ? "/images/soldier-female-before.png" : "/images/soldier-female-after.png";

  return (
    <main className="home-page flex-1 overflow-y-auto">
      <div className="home-shell">
        <div className="home-meta"><span>작전실 <b>/</b> 오늘의 질문</span><small>전역 후의 다음을 함께</small></div>
        <div className="home-layout">
          <section className="home-main" aria-label="전역도우미에게 질문하기">
            <div className="home-intro">
              <div className="home-intro-copy">
                <span className="home-sticker">✳ 전역이, 질문 받을 준비 완료</span>
                <h1>전역 후의 일,<br /><em>일단 물어보세요.</em></h1>
                <p>지금 상황을 평소 말하듯 적어 주세요.<br />맞는 지원과 다음 할 일을 같이 찾아드려요.</p>
              </div>
              <div className="home-photo">
                <Image src={image} alt={before ? "전역을 준비하는 여성 군인" : "전역 후 진로를 계획하는 여성"} fill sizes="(max-width: 760px) 100px, 235px" loading="eager" priority />
                <span>다음 작전은<br /><b>내가 정한다!</b></span>
              </div>
            </div>

            <div className="home-ask">
              <span className="home-ask-sticker">질문 접수 중 ★</span>
              <div className="home-ask-heading"><strong>궁금한 거, 던져주세요.</strong><small>길게 적어도 괜찮아요</small></div>
              <Composer
                id="home-input"
                hero
                rows={3}
                placeholder={before
                  ? "예: 내년 6월에 전역하는데, 복학 전까지 받을 수 있는 취업·교육 지원이 뭐가 있나요?"
                  : "예: 지난달 전역했는데, 지금 신청할 수 있는 취업·교육 지원이 뭐가 있나요?"}
                busy={busy}
                onSubmit={onAsk}
                footer={<div className="home-chips"><span>전역 후 혜택</span><span>복학·취업</span><span>신청 방법</span></div>}
              />
            </div>

            <div className="home-hint"><span>✳</span><p><b>날짜나 복무 형태를 몰라도 괜찮아요.</b> 질문을 주시면 필요한 정보를 하나씩 함께 정리해요.</p></div>
            {ready && replies.length > 0 && (
              <div className="home-guide"><b>내 상황부터 알려줄까요?</b><QuickReplies replies={replies} onReply={onReply} /></div>
            )}

            <section className="home-popular" aria-label="예시 질문">
              <div className="home-section-heading"><small>START WITH A QUESTION</small><h2>다른 사람은 이렇게 물어봤어요</h2></div>
              <div className="home-question-list">
                {QUESTIONS.map((question, index) => {
                  const value = moment === "after" && index === 2 ? "전역했는데 취업 지원은 어디서 신청하나요?" : question;
                  return <button key={index} type="button" onClick={() => onAsk(value)}><span>0{index + 1}</span><b>{value}</b><ArrowUpRight size={16} /></button>;
                })}
              </div>
            </section>
            <div className="home-trust"><span>✳ 답변마다 근거 표시</span><span>↗ 신청처까지 연결</span><span>○ 로그인 없이 질문</span></div>
          </section>

          <StatusPanel profile={profile} items={items} moment={moment} onMomentChange={setSelectedMoment} onJourney={onJourney} onProfile={onProfile} />
        </div>
      </div>
    </main>
  );
}
