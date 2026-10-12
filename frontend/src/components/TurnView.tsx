"use client";

import {
  Check,
  ChevronRight,
  CircleHelp,
  Copy,
  CornerDownRight,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { useState } from "react";

import { parseAnswer } from "@/lib/answer";
import type { Rating } from "@/lib/feedback";
import { SERVICE_TYPE_LABELS, type Profile, type Source, type Turn } from "@/lib/types";

import { BenefitList } from "./BenefitList";
import { InlineText } from "./InlineText";
import { SourceList } from "./SourceList";

const CHIP = "inline-flex h-[26px] items-center rounded-full border px-2.5 text-[12.5px] font-medium";
const ASK_BACK = ["병사로 전역했어요", "부사관으로 전역했어요", "장교로 전역했어요", "보훈대상자예요"];

function AppliedProfile({ profile }: { profile: Profile }) {
  const chips: string[] = [];
  if (profile.service_years) chips.push(`${profile.service_years}년 복무`);
  if (profile.discharge_date) chips.push(`${profile.discharge_date} 전역`);
  if (profile.region) chips.push(profile.region);
  if (!profile.service_type && !chips.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[13px] text-fg-3">
      이 조건으로 찾았어요
      {profile.service_type && (
        <span className={`${CHIP} border-accent bg-accent-soft text-accent`}>{SERVICE_TYPE_LABELS[profile.service_type]}</span>
      )}
      {chips.map((c) => (
        <span key={c} className={`${CHIP} border-line-strong text-fg-2`}>
          {c}
        </span>
      ))}
    </div>
  );
}

function summary(sources: Source[], steps: number) {
  const count = (t: Source["type"]) => sources.filter((s) => s.type === t).length;
  const parts = (
    [
      ["법령", count("regulation")],
      ["혜택", count("benefit")],
      ["기관", count("institution")],
    ] as const
  ).filter(([, n]) => n > 0);
  if (!parts.length) return <>{steps}단계를 거쳐 답했어요</>;
  return (
    <>
      {parts.map(([name, n], i) => (
        <span key={name}>
          {i > 0 && ", "}
          {name} <b className="font-semibold text-fg">{n}건</b>
        </span>
      ))}
      을 근거로 답했어요
    </>
  );
}

function Process({ turn }: { turn: Turn }) {
  const [open, setOpen] = useState(false);
  const live = turn.status === "loading" || turn.status === "streaming";
  const showSteps = live || open;
  return (
    <div
      className={`flex flex-wrap gap-2.5 rounded-xl border border-line bg-soft px-3.5 py-2.5 text-[13.5px] text-fg-2 ${
        live ? "items-start" : "items-center"
      }`}
    >
      <ShieldCheck className="size-[18px] shrink-0 text-accent" strokeWidth={1.8} />
      <span>
        {turn.stopped
          ? "답변을 멈췄어요"
          : turn.status === "streaming"
            ? "답변을 쓰고 있어요. 근거 확인이 끝나면 출처가 붙어요"
            : live
              ? "답변을 준비하고 있어요"
              : summary(turn.sources, turn.steps.length)}
      </span>
      {!live && turn.steps.length > 0 && (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="ml-auto hidden items-center gap-0.5 text-[12.5px] text-fg-3 sm:inline-flex"
        >
          과정 보기
          <ChevronRight className={`size-[15px] transition-transform ${open ? "rotate-90" : ""}`} />
        </button>
      )}
      {showSteps && (
        <ol className="grid w-full gap-1.5">
          {turn.steps.map((step, i) => {
            const done = !live || i < turn.steps.length - 1;
            return (
              <li key={i} className="flex items-center gap-2 text-[13px] text-fg-2">
                {done ? (
                  <span className="grid size-3.5 place-items-center rounded-full bg-accent-soft text-[9px] font-black text-accent">✓</span>
                ) : (
                  <span className="step-dot" />
                )}
                {step}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

function Lines({ lines, sources, muted }: { lines: string[]; sources: Source[]; muted?: boolean }) {
  return (
    <div className={`grid gap-2.5 ${muted ? "text-[13px] text-fg-3" : "text-base leading-[1.8]"}`}>
      {lines.map((line, i) => {
        const bullet = line.match(/^[-*•]\s+(.*)$/);
        return (
          <p key={i} className={bullet ? "pl-4 -indent-3" : undefined}>
            {bullet && "• "}
            <InlineText text={(bullet ? bullet[1] : line).replace(/^#+\s*/, "")} sources={sources} />
          </p>
        );
      })}
    </div>
  );
}

export type FeedbackHandler = (turn: Turn, rating: Rating, comment?: string) => Promise<void>;

function Feedback({ turn, onFeedback }: { turn: Turn; onFeedback: FeedbackHandler }) {
  // idle → (아쉬워요: comment) → sending → sent / error
  const [state, setState] = useState<"idle" | "comment" | "sending" | "sent" | "error">("idle");
  const [rating, setRating] = useState<Rating | null>(null);
  const [comment, setComment] = useState("");
  const [copyLabel, setCopyLabel] = useState("복사");
  const base =
    "inline-flex h-[34px] items-center gap-1.5 rounded-lg border px-3 text-[13px] font-semibold disabled:cursor-default";
  const done = state === "sending" || state === "sent";

  const submit = async (r: Rating, text?: string) => {
    setRating(r);
    setState("sending");
    try {
      await onFeedback(turn, r, text?.trim() || undefined);
      setState("sent");
    } catch {
      setState("error");
    }
  };

  const ratingButton = (r: Rating, label: string, Icon: typeof ThumbsUp) => (
    <button
      type="button"
      disabled={done}
      aria-pressed={rating === r}
      onClick={() => (r === "up" ? submit("up") : (setRating("down"), setState("comment")))}
      className={`${base} ${rating === r ? "border-accent text-accent" : "border-transparent text-fg-2"}`}
    >
      <Icon className="size-[15px]" strokeWidth={1.8} />
      {label}
    </button>
  );

  return (
    <div className="grid gap-2 border-b border-line pb-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {ratingButton("up", "도움이 됐어요", ThumbsUp)}
        {ratingButton("down", "아쉬워요", ThumbsDown)}
        <button
          type="button"
          className={`${base} border-transparent text-fg-2`}
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(turn.text);
              setCopyLabel("복사했어요");
            } catch {
              setCopyLabel("복사하지 못했어요");
            }
            setTimeout(() => setCopyLabel("복사"), 1600);
          }}
        >
          <Copy className="size-[15px]" strokeWidth={1.8} />
          {copyLabel}
        </button>
        {state === "sent" && (
          <span role="status" className="inline-flex items-center gap-1 text-[13px] text-fg-3">
            <Check className="size-[15px] text-accent" strokeWidth={2} />
            의견 고마워요
          </span>
        )}
        {state === "error" && (
          <span role="alert" className="text-[13px] text-warn">
            의견을 보내지 못했어요. 다시 눌러 주세요.
          </span>
        )}
      </div>
      {state === "comment" && (
        <form
          className="grid gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            submit("down", comment);
          }}
        >
          <label htmlFor={`${turn.id}-comment`} className="text-[13px] text-fg-2">
            무엇이 부족했나요? (선택)
          </label>
          <textarea
            id={`${turn.id}-comment`}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            maxLength={1000}
            rows={2}
            placeholder="예: 우리 지역 혜택이 빠졌어요, 신청 방법이 없어요"
            className="w-full resize-none rounded-lg border border-line-strong bg-bg px-3 py-2 text-sm"
          />
          <div className="flex gap-1.5">
            <button type="submit" className={`${base} border-accent bg-accent text-accent-ink`}>
              보내기
            </button>
            <button
              type="button"
              onClick={() => (setRating(null), setState("idle"))}
              className={`${base} border-transparent text-fg-2`}
            >
              취소
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

export function TurnView({
  turn,
  onAsk,
  onFeedback,
}: {
  turn: Turn;
  onAsk: (text: string) => void;
  onFeedback: FeedbackHandler;
}) {
  return (
    <article id={turn.id} className="grid scroll-mt-6 gap-5 border-b border-line pb-8 last:border-b-0">
      <h1 className="text-[21px] leading-[1.4] font-bold tracking-[-0.03em] text-balance md:text-[26px]">{turn.question}</h1>

      {turn.status === "answer" && <AppliedProfile profile={turn.profile} />}
      {(turn.status === "loading" || turn.status === "streaming" || turn.status === "answer") && (
        <Process turn={turn} />
      )}

      {turn.status === "loading" && (
        <div className="grid gap-2.5">
          <div className="skeleton-line" />
          <div className="skeleton-line w-[85%]" />
          <div className="skeleton-line w-[60%]" />
        </div>
      )}

      {turn.status === "question" && (
        <>
          <p className="text-base leading-[1.8]">{turn.text}</p>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="복무 형태 고르기">
            {ASK_BACK.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => onAsk(t)}
                className="inline-flex h-[30px] items-center rounded-full border border-line-strong bg-bg px-3 text-[13px] font-medium text-fg-2 hover:border-accent hover:text-accent"
              >
                {t}
              </button>
            ))}
          </div>
        </>
      )}

      {turn.status === "error" && (
        <div className="grid grid-cols-[20px_1fr] gap-2.5 rounded-xl border border-line px-4 py-3.5 text-sm text-fg-2">
          <CircleHelp className="mt-0.5 size-[18px] text-warn" strokeWidth={1.8} />
          <span>{turn.text}</span>
        </div>
      )}

      {turn.status === "streaming" && (
        <Answer turn={turn} onAsk={onAsk} onFeedback={onFeedback} streaming />
      )}
      {turn.status === "answer" && <Answer turn={turn} onAsk={onAsk} onFeedback={onFeedback} />}
    </article>
  );
}

/** streaming: 초안이 들어오는 중. 근거 검증 전이라 출처·피드백은 최종 답변에서만 보인다. */
function Answer({
  turn,
  onAsk,
  onFeedback,
  streaming = false,
}: {
  turn: Turn;
  onAsk: (text: string) => void;
  onFeedback: FeedbackHandler;
  streaming?: boolean;
}) {
  const { lead, benefits, tail } = parseAnswer(turn.text);
  return (
    <div className="grid gap-5" aria-busy={streaming}>
      {lead.length > 0 && <Lines lines={lead} sources={turn.sources} />}
      {benefits.length > 0 && <BenefitList benefits={benefits} sources={turn.sources} />}
      {tail.length > 0 && <Lines lines={tail} sources={turn.sources} muted />}
      {streaming && <span className="stream-caret" aria-hidden />}
      {!streaming && !turn.stopped && turn.sources.length > 0 && (
        // 넓은 화면은 오른쪽 목록에 보이므로 좁은 화면에서만 답변 아래에 둔다.
        <div className="grid gap-2 xl:hidden">
          <h3 className="text-sm font-bold">근거 자료</h3>
          <SourceList sources={turn.sources} />
        </div>
      )}
      {turn.stopped && (
        <p className="grid grid-cols-[18px_1fr] gap-2 rounded-xl border border-line px-3.5 py-3 text-[13px] text-fg-2">
          <CircleHelp className="mt-0.5 size-[16px] text-warn" strokeWidth={1.8} />
          답변을 멈췄어요. 근거 확인 전의 초안이라 정확하지 않을 수 있어요. 필요하면 다시 물어봐 주세요.
        </p>
      )}
      {!streaming && !turn.stopped && <Feedback turn={turn} onFeedback={onFeedback} />}
      {!streaming && turn.followUps.length > 0 && (
        <div className="grid gap-2">
          <h3 className="text-sm font-bold">이어서 물어보기</h3>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="이어서 물어볼 질문">
            {turn.followUps.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => onAsk(q)}
                className="inline-flex min-h-[32px] items-center gap-1 rounded-full border border-line-strong bg-bg px-3 py-1 text-left text-[13px] font-medium text-fg-2 hover:border-accent hover:text-accent"
              >
                <CornerDownRight className="size-[14px] shrink-0" strokeWidth={1.8} />
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
