"use client";

import { Undo2, X } from "lucide-react";

import type { Journey } from "./useJourney";

/** 방금 한 변경을 알리고 바로 되돌릴 수 있게 하는 알림. 10초 뒤 사라지지만 기록은 작전도에 남는다. */
export function UndoToast({ journey }: { journey: Journey }) {
  const { toast, undoLast, dismissToast } = journey;
  if (!toast) return null;
  return (
    <div
      role="status"
      className="pointer-events-none fixed inset-x-0 bottom-[84px] z-40 flex justify-center px-3 lg:bottom-6"
    >
      <div className="pointer-events-auto flex max-w-[560px] items-center gap-2 rounded-xl border-[2.5px] border-[#1f2416] bg-[#fbeaa9] py-2 pr-2 pl-3.5 text-[14px] font-bold text-[#1f2416] shadow-[4px_4px_0_var(--olive-dark)]">
        <span className="min-w-0 truncate">{toast.label}</span>
        <button
          type="button"
          onClick={() => void undoLast(1)}
          className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border-2 border-[#1f2416] bg-white px-3 text-[14px] font-extrabold"
        >
          <Undo2 className="size-4" strokeWidth={2.4} />
          되돌리기
        </button>
        <button
          type="button"
          onClick={dismissToast}
          aria-label="알림 닫기"
          className="grid size-8 shrink-0 place-items-center rounded-lg text-[#4f4a3a]"
        >
          <X className="size-4" />
        </button>
      </div>
    </div>
  );
}
