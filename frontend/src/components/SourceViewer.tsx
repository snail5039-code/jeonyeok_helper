"use client";

import { ExternalLink, FileText, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { dateLabel } from "@/lib/asOf";
import type { Source } from "@/lib/types";

const KIND: Record<Source["type"], string> = {
  regulation: "법령·안내서",
  benefit: "혜택",
  institution: "기관",
};

interface Opened {
  source: Source;
  /** 답변 본문의 [n] 번호 */
  index: number;
}

const OpenSource = createContext<((source: Source, index: number) => void) | null>(null);

/** 근거 원문 보기를 열 수 있으면 여는 함수, 아니면 null (그때는 링크로 연다) */
export function useOpenSource() {
  return useContext(OpenSource);
}

const isHttp = (url: string) => /^https?:\/\//.test(url);

/** 근거 원문 보기: 답변의 [n]이나 근거 자료를 누르면 옆(휴대폰은 아래)에 원문 발췌와 원래 누리집 링크를 연다 */
export function SourceViewer({ children }: { children: React.ReactNode }) {
  const [opened, setOpened] = useState<Opened | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const closeButton = useRef<HTMLButtonElement>(null);

  const open = useCallback((source: Source, index: number) => {
    returnFocus.current = document.activeElement as HTMLElement | null;
    setOpened({ source, index });
  }, []);

  const close = useCallback(() => {
    setOpened(null);
    returnFocus.current?.focus();
  }, []);

  useEffect(() => {
    if (!opened) return;
    closeButton.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [opened, close]);

  return (
    <OpenSource.Provider value={open}>
      {children}
      {/* 답변이 접힌 '자세히 보기' 안에 있어도 보이게 body에 그린다 */}
      {opened &&
        createPortal(
          <>
            <div aria-hidden onClick={close} className="fixed inset-0 z-40 bg-black/30" />
            <aside
              role="dialog"
              aria-modal="true"
              aria-labelledby="source-viewer-title"
              className="fixed inset-x-0 bottom-0 z-50 grid max-h-[80dvh] grid-rows-[auto_minmax(0,1fr)_auto] rounded-t-2xl border-t-[2.5px] border-ink bg-bg shadow-[0_-6px_24px_rgb(0_0_0/0.2)] sm:inset-y-0 sm:right-0 sm:left-auto sm:max-h-none sm:w-[440px] sm:rounded-none sm:border-t-0 sm:border-l-[2.5px]"
            >
              <header className="flex items-start gap-3 border-b-2 border-dashed border-edge p-4">
                <span className="grid h-[24px] min-w-[24px] place-items-center rounded-md bg-sunken px-1 text-[13px] font-bold tabular-nums text-fg-2">
                  {opened.index}
                </span>
                <div className="grid min-w-0 flex-1 gap-1">
                  <span className="text-[12px] font-bold text-fg-3">
                    근거 원문 · {KIND[opened.source.type] ?? "출처"}
                    {opened.source.date && ` · 시행 ${dateLabel(opened.source.date)}`}
                  </span>
                  <h2 id="source-viewer-title" className="text-[16px] leading-snug font-extrabold">
                    {opened.source.title}
                  </h2>
                </div>
                <button
                  ref={closeButton}
                  type="button"
                  onClick={close}
                  aria-label="원문 닫기"
                  className="grid size-9 shrink-0 place-items-center rounded-lg border-2 border-edge hover:border-ink"
                >
                  <X className="size-4" />
                </button>
              </header>

              <div className="overflow-y-auto p-4">
                {opened.source.excerpt ? (
                  <p className="text-[14.5px] leading-[1.75] whitespace-pre-wrap">{opened.source.excerpt}</p>
                ) : (
                  <p className="flex items-start gap-2 text-[14px] leading-relaxed text-fg-2">
                    <FileText className="mt-0.5 size-4 shrink-0" />이 자료는 원문 발췌가 없어요. 아래 원래 누리집에서
                    내용을 확인해 주세요.
                  </p>
                )}
              </div>

              <footer className="grid gap-2 border-t-2 border-dashed border-edge p-4">
                {isHttp(opened.source.url) && (
                  <a
                    href={opened.source.url}
                    target="_blank"
                    rel="noopener"
                    className="inline-flex h-10 items-center justify-center gap-1.5 rounded-[10px] border-[2.5px] border-ink bg-soft px-3.5 text-[14px] font-extrabold hover:bg-sunken"
                  >
                    원래 누리집에서 보기
                    <ExternalLink className="size-4" />
                  </a>
                )}
                <p className="text-[12px] text-fg-3">
                  답변은 이 원문을 근거로 썼어요. 바뀐 내용이 있을 수 있으니 원래 누리집에서도 확인하세요.
                </p>
              </footer>
            </aside>
          </>,
          document.body,
        )}
    </OpenSource.Provider>
  );
}
