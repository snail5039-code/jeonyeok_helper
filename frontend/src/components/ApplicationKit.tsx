"use client";

import {
  AlarmClock,
  Building2,
  Check,
  ClipboardCheck,
  Copy,
  ExternalLink,
  FileCheck2,
  ListOrdered,
  Phone,
  ShieldCheck,
  UserRoundPen,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { fetchKit, formText, loadChecked, saveChecked, type Kit } from "@/lib/applications";
import { daysLeft, ddayLabel } from "@/lib/journey";

interface Props {
  programId: string;
  userId: string;
  onClose: () => void;
  onProfile: () => void;
}

const FIT_STYLE: Record<Kit["fit"]["level"], [string, string]> = {
  ok: ["대상으로 보여요", "bg-done/40 text-fg"],
  check: ["대상인지 확인해 보세요", "bg-sunken text-fg"],
  unlikely: ["대상이 아닐 수 있어요", "bg-warn-soft text-warn"],
};

const isHttp = (url?: string) => Boolean(url && /^https?:\/\//.test(url));

/** 신청 서류 도우미: 챙길 서류(체크), 내 정보로 채운 신청 내용(복사), 낼 곳, 순서, 근거 */
export function ApplicationKit({ programId, userId, onClose, onProfile }: Props) {
  const [kit, setKit] = useState<Kit | null>(null);
  const [error, setError] = useState("");
  const [checked, setChecked] = useState<string[]>(() => loadChecked(userId, programId));
  const [copied, setCopied] = useState(false);
  const closeButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let alive = true;
    fetchKit(programId, userId)
      .then((k) => alive && setKit(k))
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [programId, userId]);

  useEffect(() => {
    closeButton.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const toggle = (name: string) => {
    const next = checked.includes(name) ? checked.filter((n) => n !== name) : [...checked, name];
    setChecked(next);
    saveChecked(userId, programId, next);
  };

  const copy = async () => {
    if (!kit) return;
    try {
      await navigator.clipboard.writeText(formText(kit));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  const mine = kit?.documents.filter((d) => d.by === "me") ?? [];
  const office = kit?.documents.filter((d) => d.by === "office") ?? [];
  const done = mine.filter((d) => checked.includes(d.name)).length;
  const due = kit?.deadline.date ? daysLeft(new Date(`${kit.deadline.date}T00:00:00`)) : null;
  const section = "grid gap-2.5 rounded-xl border-2 border-edge bg-soft p-4";
  const heading = "flex items-center gap-2 text-[15.5px] font-extrabold";

  return createPortal(
    <>
      <div aria-hidden onClick={onClose} className="fixed inset-0 z-40 bg-black/35" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="kit-title"
        className="fixed inset-x-0 bottom-0 z-50 grid max-h-[92dvh] grid-rows-[auto_minmax(0,1fr)] rounded-t-2xl border-t-[2.5px] border-ink bg-bg shadow-[0_-6px_24px_rgb(0_0_0/0.2)] sm:inset-auto sm:top-1/2 sm:left-1/2 sm:max-h-[88dvh] sm:w-[640px] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:border-[2.5px]"
      >
        <header className="flex items-start gap-3 border-b-2 border-dashed border-edge p-4">
          <ClipboardCheck className="mt-0.5 size-5 shrink-0 text-olive" strokeWidth={2.2} />
          <div className="grid min-w-0 flex-1 gap-1">
            <span className="text-[12px] font-bold text-fg-3">신청 서류 도우미</span>
            <h2 id="kit-title" className="text-[18px] leading-snug font-extrabold">
              {kit?.title ?? "불러오는 중…"}
            </h2>
          </div>
          <button
            ref={closeButton}
            type="button"
            onClick={onClose}
            aria-label="서류 도우미 닫기"
            className="grid size-9 shrink-0 place-items-center rounded-lg border-2 border-edge hover:border-ink"
          >
            <X className="size-4" />
          </button>
        </header>

        <div className="grid content-start gap-4 overflow-y-auto p-4">
          {error && (
            <p role="alert" className="text-[14px] font-semibold text-warn">
              {error}
            </p>
          )}
          {kit && (
            <>
              <p className="text-[14.5px] leading-relaxed">{kit.summary}</p>
              <div className="flex flex-wrap gap-2">
                <span className={`rounded-md px-2 py-1 text-[13px] font-bold ${FIT_STYLE[kit.fit.level][1]}`}>
                  {FIT_STYLE[kit.fit.level][0]}
                </span>
                <span className="inline-flex items-center gap-1 rounded-md bg-sunken px-2 py-1 text-[13px] font-bold">
                  <AlarmClock className="size-3.5" />
                  {kit.deadline.text}
                  {due !== null && <span className="tabular-nums">· {ddayLabel(due)}</span>}
                </span>
              </div>
              <p className="text-[13px] leading-relaxed text-fg-2">{kit.fit.text}</p>

              <section className={section} aria-labelledby="kit-docs">
                <h3 id="kit-docs" className={heading}>
                  <FileCheck2 className="size-[18px] text-olive" />
                  챙길 서류
                  <span className="text-[12.5px] font-semibold text-fg-3 tabular-nums">
                    {done}/{mine.length} 챙김
                  </span>
                </h3>
                <ul className="grid gap-2">
                  {mine.map((d) => {
                    const on = checked.includes(d.name);
                    return (
                      <li key={d.name}>
                        <button
                          type="button"
                          onClick={() => toggle(d.name)}
                          aria-pressed={on}
                          className="grid w-full grid-cols-[24px_minmax(0,1fr)] gap-2.5 rounded-lg p-1.5 text-left hover:bg-sunken"
                        >
                          <span
                            className={`mt-0.5 grid size-[22px] place-items-center rounded-md border-[2.5px] border-ink ${on ? "bg-olive text-olive-ink" : "bg-white"}`}
                          >
                            {on && <Check className="size-3.5" strokeWidth={3.5} />}
                          </span>
                          <span className="grid gap-0.5">
                            <b className={`text-[14.5px] ${on ? "text-fg-3 line-through" : ""}`}>{d.name}</b>
                            {d.how && <span className="text-[13px] leading-relaxed text-fg-2">{d.how}</span>}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
                {office.length > 0 && (
                  <p className="flex items-start gap-1.5 rounded-lg bg-sunken px-3 py-2 text-[13px] leading-relaxed text-fg-2">
                    <ShieldCheck className="mt-0.5 size-4 shrink-0" />
                    <span>
                      <b className="text-fg">기관이 직접 확인해서 안 내도 돼요:</b> {office.map((d) => d.name).join(", ")}
                    </span>
                  </p>
                )}
              </section>

              <section className={section} aria-labelledby="kit-form">
                <h3 id="kit-form" className={heading}>
                  <UserRoundPen className="size-[18px] text-olive" />
                  신청서에 쓸 내 정보
                </h3>
                <dl className="grid gap-1.5">
                  {kit.form.map((f) => (
                    <div key={f.label} className="grid grid-cols-[minmax(0,9.5em)_minmax(0,1fr)] gap-3 border-b border-dashed border-line pb-1.5 text-[14px]">
                      <dt className="font-semibold text-fg-2">{f.label}</dt>
                      <dd className={f.value ? "font-bold" : "text-[13px] text-fg-3"}>{f.value || f.hint || "직접 적기"}</dd>
                    </div>
                  ))}
                </dl>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void copy()}
                    className="inline-flex h-9 items-center gap-1.5 rounded-[10px] border-2 border-edge bg-bg px-3 text-[13.5px] font-bold hover:border-ink"
                  >
                    {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
                    {copied ? "복사했어요" : "글로 복사"}
                  </button>
                  {kit.form.some((f) => f.from_profile && !f.value) && (
                    <button
                      type="button"
                      onClick={onProfile}
                      className="inline-flex h-9 items-center gap-1.5 rounded-[10px] border-2 border-edge bg-bg px-3 text-[13.5px] font-bold hover:border-ink"
                    >
                      <UserRoundPen className="size-4" />
                      빈칸 내 정보에서 채우기
                    </button>
                  )}
                </div>
                <p className="text-[12px] text-fg-3">이름·주민등록번호 같은 개인정보는 전역도우미에 저장하지 않아요. 신청서에 직접 적어 주세요.</p>
              </section>

              <section className={section} aria-labelledby="kit-submit">
                <h3 id="kit-submit" className={heading}>
                  <Building2 className="size-[18px] text-olive" />
                  낼 곳
                </h3>
                {kit.submit.offices.length > 0 ? (
                  <ul className="grid gap-2">
                    {kit.submit.offices.map((o) => (
                      <li key={o.name} className="grid gap-0.5 rounded-lg bg-bg p-2.5 text-[14px]">
                        <b>{o.name}</b>
                        {o.address && <span className="text-fg-2">{o.address}</span>}
                        <span className="flex flex-wrap gap-3">
                          {o.phone && (
                            <a href={`tel:${o.phone}`} className="inline-flex items-center gap-1 font-semibold text-accent">
                              <Phone className="size-3.5" />
                              {o.phone}
                            </a>
                          )}
                          {isHttp(o.url) && (
                            <a href={o.url} target="_blank" rel="noopener" className="inline-flex items-center gap-1 font-semibold text-accent">
                              찾아가는 길 <ExternalLink className="size-3.5" />
                            </a>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-[14px] font-bold">
                    {kit.submit.where || "사는 곳 관할 보훈(지)청 (내 정보에 지역을 넣으면 찾아 드려요)"}
                  </p>
                )}
                <p className="text-[13.5px] text-fg-2">내는 방법: {kit.submit.ways.join(", ")}</p>
                <div className="flex flex-wrap gap-3 text-[13.5px]">
                  {kit.submit.online && isHttp(kit.submit.online.url) && (
                    <a href={kit.submit.online.url} target="_blank" rel="noopener" className="inline-flex items-center gap-1 font-bold text-accent">
                      {kit.submit.online.name} <ExternalLink className="size-3.5" />
                    </a>
                  )}
                  {kit.submit.phone && (
                    <a href={`tel:${kit.submit.phone.split(" ")[0]}`} className="inline-flex items-center gap-1 font-bold text-accent">
                      <Phone className="size-3.5" />
                      {kit.submit.phone}
                    </a>
                  )}
                </div>
              </section>

              <section className={section} aria-labelledby="kit-steps">
                <h3 id="kit-steps" className={heading}>
                  <ListOrdered className="size-[18px] text-olive" />
                  신청 순서
                </h3>
                <ol className="grid list-decimal gap-1.5 pl-5 text-[14px] leading-relaxed">
                  {kit.steps.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ol>
              </section>

              <section className="grid gap-1.5" aria-label="근거">
                <span className="text-[12.5px] font-bold text-fg-3">근거 자료</span>
                <ul className="grid gap-1 text-[13px]">
                  {kit.sources.map((s) =>
                    isHttp(s.url) ? (
                      <li key={s.title}>
                        <a href={s.url} target="_blank" rel="noopener" className="text-fg-2 underline-offset-2 hover:text-accent hover:underline">
                          {s.title}
                        </a>
                      </li>
                    ) : (
                      <li key={s.title} className="text-fg-2">
                        {s.title}
                      </li>
                    ),
                  )}
                </ul>
                <p className="text-[12px] text-fg-3">서류와 기한은 바뀔 수 있어요. 내기 전에 낼 곳에 한 번 더 확인하세요.</p>
              </section>
            </>
          )}
        </div>
      </div>
    </>,
    document.body,
  );
}
