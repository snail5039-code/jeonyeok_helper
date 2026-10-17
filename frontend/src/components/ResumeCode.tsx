"use client";

import { Copy, KeyRound, RefreshCw, Smartphone } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useState } from "react";

import { fetchResumeCode, makeResumeCode, resumeUrl } from "@/lib/resume";

interface Props {
  userId: string;
  /** 다른 기기에서 받은 코드로 이 브라우저를 그 기록으로 바꾼다. 결과 안내를 돌려준다 */
  onResume: (code: string) => Promise<string>;
}

/** 이어 하기 코드: 이 기록의 열쇠를 보여 주고(코드·QR), 다른 기기에서 받은 코드로 이어 한다. */
export function ResumeCode({ userId, onResume }: Props) {
  const [code, setCode] = useState<string | null>(null);
  const [qr, setQr] = useState("");
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!userId) return;
    let alive = true;
    void fetchResumeCode(userId).then((c) => alive && setCode(c));
    return () => {
      alive = false;
    };
  }, [userId]);

  useEffect(() => {
    if (!code) return;
    let alive = true;
    void QRCode.toDataURL(resumeUrl(code, location.origin), { margin: 1, width: 180 }).then((url) => alive && setQr(url));
    return () => {
      alive = false;
    };
  }, [code]);

  const run = async (work: () => Promise<string>) => {
    setBusy(true);
    setMessage(null);
    try {
      setMessage({ ok: true, text: await work() });
    } catch (e) {
      setMessage({ ok: false, text: e instanceof Error ? e.message : "다시 시도해 주세요." });
    } finally {
      setBusy(false);
    }
  };

  const issue = () =>
    run(async () => {
      if (code && !confirm("새 코드를 만들면 지금 코드로는 더 이상 이어 할 수 없어요. 새로 만들까요?")) {
        return "새 코드 만들기를 취소했어요.";
      }
      setQr("");
      setCode(await makeResumeCode(userId));
      return "코드를 만들었어요. 다른 기기에서 이 코드를 넣거나 QR을 찍으세요.";
    });

  const copy = () =>
    run(async () => {
      await navigator.clipboard.writeText(code ?? "");
      return "코드를 복사했어요.";
    });

  const button =
    "inline-flex h-10 items-center gap-1.5 rounded-[10px] border-2 border-edge bg-bg px-3 text-[14px] font-bold text-fg hover:border-ink disabled:opacity-60";

  return (
    <div className="grid gap-3 border-t-2 border-dashed border-edge pt-4">
      <h3 className="flex items-center gap-1.5 text-[15px] font-extrabold">
        <Smartphone className="size-4 text-olive" strokeWidth={2.2} />
        다른 기기에서 이어 하기
      </h3>
      <p className="text-[13.5px] leading-[1.6] text-fg-2">
        코드는 비밀번호가 아니라 <b className="text-fg">이 기록의 열쇠</b>예요. 코드를 아는 사람은 내 작전도를 볼 수 있으니
        다른 사람에게 보여 주지 마세요. 새로 만들면 이전 코드는 바로 못 쓰게 돼요.
      </p>

      {code ? (
        <div className="flex flex-wrap items-center gap-4">
          {qr && (
            // eslint-disable-next-line @next/next/no-img-element -- 화면에서 만든 data: 주소라 next/image가 필요 없다
            <img src={qr} alt="휴대폰으로 찍으면 이 기록으로 이어져요" width={120} height={120} className="rounded-lg border-2 border-edge bg-white" />
          )}
          <div className="grid gap-2">
            <span className="text-[12.5px] font-bold text-fg-3">내 이어 하기 코드</span>
            <code aria-label="내 이어 하기 코드" className="font-mono text-[22px] font-extrabold tracking-[0.08em]">
              {code}
            </code>
            <div className="flex flex-wrap gap-2">
              <button type="button" disabled={busy} onClick={() => void copy()} className={button}>
                <Copy className="size-4" />
                복사
              </button>
              <button type="button" disabled={busy} onClick={() => void issue()} className={button}>
                <RefreshCw className="size-4" />새 코드 만들기
              </button>
            </div>
          </div>
        </div>
      ) : (
        <button type="button" disabled={busy || !userId} onClick={() => void issue()} className={`${button} w-fit`}>
          <KeyRound className="size-4" />
          이어 하기 코드 받기
        </button>
      )}

      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (typed.trim()) void run(() => onResume(typed.trim()));
        }}
      >
        <label className="grid flex-1 gap-1.5 text-sm font-bold sm:max-w-[260px]">
          다른 기기에서 받은 코드
          <input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder="예: JY-7K3Q-9XPA"
            autoComplete="off"
            className="h-10 w-full rounded-[10px] border-2 border-edge bg-soft px-3 font-mono text-[15px] font-normal tracking-wider uppercase outline-none focus:border-ink"
          />
        </label>
        <button type="submit" disabled={busy || !typed.trim()} className={button}>
          이 코드로 이어 하기
        </button>
      </form>

      {message && (
        <p role={message.ok ? "status" : "alert"} className={`text-[13px] font-semibold ${message.ok ? "text-olive" : "text-warn"}`}>
          {message.text}
        </p>
      )}
    </div>
  );
}
