"use client";

import { Download, KeyRound, ShieldAlert, X } from "lucide-react";
import { useState } from "react";

import { readStorage, writeStorage } from "@/lib/storage";

export const KEEP_NOTICE_KEY = "jeonyeok.keepNoticeSeen";

interface Props {
  onExport: () => Promise<void>;
  onOpenCode: () => void;
}

/** 작전도에 할 일이 생기면 한 번만: 로그인이 없어 기록이 이 브라우저에 묶여 있다고 알리고,
    파일 저장·이어 하기 코드로 바로 이어 준다. 닫거나 하나를 고르면 다시 보이지 않는다.
    브라우저에서만 그린다 (본 적 있는지는 localStorage에 있다). */
export function KeepNotice({ onExport, onOpenCode }: Props) {
  const [seen, setSeen] = useState(() => readStorage(KEEP_NOTICE_KEY) === "1");
  const [error, setError] = useState("");
  if (seen) return null;

  const close = () => {
    writeStorage(KEEP_NOTICE_KEY, "1");
    setSeen(true);
  };

  return (
    <aside
      role="dialog"
      aria-label="내 기록 지키기 안내"
      className="fixed inset-x-3 top-[72px] z-40 mx-auto grid max-w-[420px] gap-2.5 rounded-xl border-[2.5px] border-ink bg-soft p-4 shadow-[4px_4px_0_var(--olive-dark)] lg:inset-x-auto lg:top-auto lg:bottom-6 lg:left-6 lg:mx-0"
    >
      <div className="flex items-start gap-2">
        <ShieldAlert className="mt-0.5 size-5 shrink-0 text-warn" strokeWidth={2.2} />
        <p className="text-[14px] leading-[1.6] text-fg">
          <b>이 기록은 이 브라우저에 묶여 있어요.</b> 로그인이 없어서 브라우저 기록을 지우거나 기기를 바꾸면 작전도가
          사라질 수 있어요. 파일로 저장하거나 이어 하기 코드를 받아 두세요.
        </p>
        <button type="button" onClick={close} aria-label="안내 닫기" className="-mt-1 -mr-1 rounded-md p-1 text-fg-3 hover:text-fg">
          <X className="size-4" />
        </button>
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() =>
            void onExport().then(close, (e) => setError(e instanceof Error ? e.message : "저장하지 못했어요."))
          }
          className="inline-flex h-9 items-center gap-1.5 rounded-[10px] border-[2.5px] border-[#1f2416] bg-done px-3 text-[13.5px] font-extrabold text-[#1f2416]"
        >
          <Download className="size-4" />
          파일로 저장
        </button>
        <button
          type="button"
          onClick={() => {
            close();
            onOpenCode();
          }}
          className="inline-flex h-9 items-center gap-1.5 rounded-[10px] border-2 border-edge bg-bg px-3 text-[13.5px] font-bold text-fg hover:border-ink"
        >
          <KeyRound className="size-4" />
          이어 하기 코드 받기
        </button>
        <button type="button" onClick={close} className="h-9 px-2 text-[13px] font-semibold text-fg-3 hover:text-fg">
          나중에
        </button>
      </div>
      {error && <p role="alert" className="text-[13px] font-semibold text-warn">{error}</p>}
    </aside>
  );
}
