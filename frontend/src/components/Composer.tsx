"use client";

import { ArrowUp, Square } from "lucide-react";
import { useRef, useState, type ReactNode } from "react";

interface Props {
  placeholder: string;
  disabled?: boolean;
  /** 답변을 받는 중: 보내기 대신 멈춤 버튼을 보여 준다 (onStop이 있을 때) */
  busy?: boolean;
  onStop?: () => void;
  rows?: number;
  onSubmit: (text: string) => void;
  /** 입력창 아래쪽 줄(첫 화면의 복무 형태 버튼 등) */
  footer?: ReactNode;
  compact?: boolean;
  id: string;
}

export function Composer({
  placeholder,
  disabled: disabledProp,
  busy,
  onStop,
  rows = 1,
  onSubmit,
  footer,
  compact,
  id,
}: Props) {
  const disabled = disabledProp || busy;
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  const grow = () => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  const submit = () => {
    const text = value.trim();
    if (!text || disabled) return;
    onSubmit(text);
    setValue("");
    requestAnimationFrame(grow);
  };

  const sendButton =
    busy && onStop ? (
      <button
        type="button"
        onClick={onStop}
        aria-label="답변 멈추기"
        title="답변 멈추기"
        className="grid size-9 shrink-0 place-items-center rounded-[10px] bg-fg text-bg"
      >
        <Square className="size-[13px]" fill="currentColor" strokeWidth={0} />
      </button>
    ) : (
      <button
        type="submit"
        disabled={disabled}
        aria-label="질문 보내기"
        className="grid size-9 shrink-0 place-items-center rounded-[10px] bg-accent text-accent-ink disabled:opacity-50"
      >
        <ArrowUp className="size-[18px]" strokeWidth={2.2} />
      </button>
    );

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className={`grid gap-2.5 rounded-[18px] border border-line-strong bg-bg shadow-card focus-within:border-accent ${
        compact ? "grid-cols-[1fr_auto] items-center py-2 pr-2 pl-[18px]" : "pt-3.5 pr-3.5 pb-2.5 pl-[18px]"
      }`}
    >
      <textarea
        id={id}
        ref={ref}
        rows={rows}
        value={value}
        placeholder={placeholder}
        aria-label={placeholder}
        onChange={(e) => {
          setValue(e.target.value);
          grow();
        }}
        onKeyDown={(e) => {
          // 한글 조합 중 Enter는 무시해야 마지막 글자가 두 번 들어가지 않는다.
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        className="min-h-6 resize-none bg-transparent text-base text-fg outline-none placeholder:text-fg-3"
      />
      {compact ? (
        sendButton
      ) : (
        <div className="flex items-center justify-between gap-2">
          {footer}
          {sendButton}
        </div>
      )}
    </form>
  );
}
