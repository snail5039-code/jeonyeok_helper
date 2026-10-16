"use client";

import { ArrowUpRight, Check, Plus } from "lucide-react";
import Image from "next/image";
import { useState } from "react";

import { dischargeMoment, type DischargeMoment } from "@/lib/discharge";
import { nextItem, progress } from "@/lib/journey";
import type { JourneyItem, Profile } from "@/lib/types";

interface Props {
  profile: Profile;
  items: JourneyItem[];
  onJourney: () => void;
  onProfile: () => void;
  moment?: DischargeMoment;
  onMomentChange?: (moment: DischargeMoment) => void;
  className?: string;
}

/** 홈과 대화 화면에서 공통으로 쓰는 실제 데이터 기반 작전 현황. */
export function StatusPanel({ profile, items, onJourney, onProfile, moment: controlled, onMomentChange, className = "" }: Props) {
  const [selected, setSelected] = useState<DischargeMoment | null>(null);
  const moment = controlled ?? selected ?? dischargeMoment(profile.discharge_date);
  const choose = (next: DischargeMoment) => {
    setSelected(next);
    onMomentChange?.(next);
  };
  const p = progress(items);
  const next = nextItem(items);
  const before = moment === "before";
  const image = before ? "/images/soldier-female-before.png" : "/images/soldier-female-after.png";
  const dateMatches = profile.discharge_date && dischargeMoment(profile.discharge_date) === moment;

  return (
    <aside className={`home-tracker ${className}`} aria-label="나의 전역 작전도">
      <div className="home-tracker-head"><span>MY NEXT STEP</span><small>나의 작전도</small></div>
      <div className="home-tracker-tabs" role="group" aria-label="전역 상태">
        <button type="button" aria-pressed={before} onClick={() => choose("before")}>전역 전</button>
        <button type="button" aria-pressed={!before} onClick={() => choose("after")}>전역 후</button>
      </div>
      <div className="home-tracker-profile"><div className="home-avatar"><Image src={image} alt="" fill sizes="120px" /></div><div><b>나의 작전도</b><small>{before ? "전역 준비 중" : "전역 후 · 새 출발 중"}{profile.branch ? ` · ${profile.branch}` : ""}</small></div><button type="button" onClick={onProfile} aria-label="내 정보 수정">···</button></div>
      <div className="home-status"><div><span>{before ? "BEFORE DISCHARGE" : "AFTER DISCHARGE"}</span><i>✦ {before ? "준비 중" : "다음 장"}</i></div><h2>{before ? <>전역 뒤의 계획,<br />지금부터 하나씩.</> : <>이제 내 차례.<br />다음 단계로 가보자.</>}</h2><p>{dateMatches ? `전역${before ? " 예정" : ""} ${profile.discharge_date}` : "내 상황에 맞는 다음 일을 찾아보세요"}</p><span className="home-status-star" aria-hidden>✳</span></div>
      <div className="home-progress"><div><div><small>MY PROGRESS</small><b>{before ? "전역 후 준비" : "전역 후 계획"}</b></div><strong><span>{p.done}</span> / {p.total}</strong></div><div className="home-progress-track" role="progressbar" aria-label="작전도 진행률" aria-valuemin={0} aria-valuemax={100} aria-valuenow={p.percent}><i style={{ width: `${p.percent}%` }} /></div><p>{items.length ? "담아둔 일을 하나씩 끝내 보세요." : "질문하면 내 할 일을 여기에 담아드려요."}</p></div>
      <div className="home-journey"><span className={profile.service_type ? "done" : "current"}>상황 등록</span><span className={items.length && p.done ? "done" : profile.service_type ? "current" : ""}>지원 찾기</span><span className={items.length && p.done ? "current" : ""}>신청 준비</span></div>
      <div className="home-mission"><div className="home-mission-heading"><div><small>NEXT MISSION</small><h3>지금 해볼 일</h3></div><span>추천 1순위</span></div>{next ? <div className="home-mission-row"><span className="home-mission-number">01</span><div><b>{next.title}</b><small>{next.action}</small></div><ArrowUpRight size={17} /></div> : <div className="home-mission-row"><span className="home-mission-number"><Plus size={16} /></span><div><b>받을 수 있는 지원 물어보기</b><small>취업·복학·생활, 편하게 질문하세요</small></div><ArrowUpRight size={17} /></div>}{items.length > 0 && <div className="home-mission-done"><Check size={15} /> 내 작전도에 {items.length}개 담았어요</div>}<button type="button" className="home-cta" onClick={onJourney}>내 작전도 보기 <ArrowUpRight size={17} /></button></div>
    </aside>
  );
}
