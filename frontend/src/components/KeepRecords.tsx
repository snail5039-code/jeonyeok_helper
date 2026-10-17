"use client";

import { Download, FolderOpen, ShieldCheck } from "lucide-react";
import { useRef, useState } from "react";

interface Props {
  demo: boolean;
  onExport: () => Promise<void>;
  onImport: (file: File) => Promise<string>;
  /** 기록을 되살린 뒤 화면을 다시 그려도 결과 안내가 남도록 바깥에서 받는다 */
  notice?: string;
}

/** 내 기록 지키기: 로그인이 없으니 기록을 파일로 내려받아 두고, 다른 곳에서 되살린다. */
export function KeepRecords({ demo, onExport, onImport, notice }: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<"" | "export" | "import">("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(
    notice ? { ok: true, text: notice } : null,
  );

  const run = async (kind: "export" | "import", work: () => Promise<string>) => {
    setBusy(kind);
    setMessage(null);
    try {
      setMessage({ ok: true, text: await work() });
    } catch (e) {
      setMessage({ ok: false, text: e instanceof Error ? e.message : "다시 시도해 주세요." });
    } finally {
      setBusy("");
    }
  };

  const button =
    "inline-flex h-11 items-center gap-1.5 rounded-[10px] border-2 border-edge bg-bg px-3.5 text-[14px] font-bold text-fg hover:border-ink disabled:opacity-60";

  return (
    <fieldset id="keep-records" className="grid gap-4 rounded-xl border-2 border-edge bg-soft/70 p-4 md:p-5">
      <legend className="flex items-center gap-1.5 px-1">
        <ShieldCheck className="size-[18px] text-olive" strokeWidth={2.2} />
        <span className="font-stencil text-[19px] font-normal">내 기록 지키기</span>
      </legend>
      <p className="text-[14px] leading-[1.6] text-fg-2">
        로그인 없이 쓰는 대신, 내 정보와 작전도는 <b className="text-fg">이 브라우저</b>에 묶여 있어요. 브라우저 기록을
        지우거나 기기를 바꾸면 사라질 수 있으니 파일로 저장해 두세요. 다른 기기에서 그 파일을 불러오면 완료 표시까지
        그대로 이어져요.
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy !== ""}
          onClick={() =>
            void run("export", async () => {
              await onExport();
              return "기록 파일을 내려받았어요. 잃어버리지 않게 잘 보관해 두세요.";
            })
          }
          className={button}
        >
          <Download className="size-4" />
          {busy === "export" ? "저장 중…" : "파일로 저장하기"}
        </button>
        <button type="button" disabled={busy !== ""} onClick={() => fileInput.current?.click()} className={button}>
          <FolderOpen className="size-4" />
          {busy === "import" ? "불러오는 중…" : "파일에서 불러오기"}
        </button>
        <input
          ref={fileInput}
          type="file"
          accept="application/json,.json"
          className="hidden"
          aria-label="기록 파일 고르기"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = ""; // 같은 파일을 다시 골라도 동작하게
            if (file) void run("import", () => onImport(file));
          }}
        />
      </div>
      {demo && <p className="text-[12.5px] text-fg-3">데모 모드: 이 브라우저에 저장된 데모 기록을 저장·불러와요</p>}
      {message && (
        <p role={message.ok ? "status" : "alert"} className={`text-[13px] font-semibold ${message.ok ? "text-olive" : "text-warn"}`}>
          {message.text}
        </p>
      )}
    </fieldset>
  );
}
