"use client";

import { AlertTriangle, Gauge, KeyRound, RefreshCw, ThumbsDown, Timer } from "lucide-react";
import { useEffect, useState, useSyncExternalStore } from "react";

import { fetchSummary, KIND_NAMES, NODE_NAMES, seconds, TOKEN_KEY, type AdminSummary } from "@/lib/admin";

const card = "grid content-start gap-3 rounded-xl border-2 border-edge bg-soft p-4";
const heading = "flex items-center gap-2 text-[16px] font-extrabold";

function readToken(): string {
  try {
    return sessionStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

// 열쇠는 이 탭에만 둔다 (sessionStorage, 탭을 닫으면 사라짐). 바뀌면 화면에 알린다.
const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => void listeners.delete(listener);
};

function writeToken(token: string): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* 저장할 수 없는 환경 */
  }
  listeners.forEach((l) => l());
}

const when = (iso: string) =>
  new Date(iso).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });

/** 운영 대시보드: 최근 며칠의 👎 피드백, 느린 단계, 실패한 도구 호출을 한 화면에 */
export function AdminDashboard() {
  const token = useSyncExternalStore(subscribe, readToken, () => "");
  const [typed, setTyped] = useState("");
  const [days, setDays] = useState(7);
  const [tick, setTick] = useState(0); // 새로고침
  const [data, setData] = useState<AdminSummary | null>(null);
  const [error, setError] = useState("");
  const request = `${token}:${days}:${tick}`;
  const [loaded, setLoaded] = useState("");
  const busy = Boolean(token) && loaded !== request;

  useEffect(() => {
    if (!token) return;
    let alive = true;
    fetchSummary(token, days)
      .then((d) => {
        if (!alive) return;
        setData(d);
        setError("");
      })
      .catch((e: Error) => {
        if (!alive) return;
        setError(e.message);
        if (e.message.includes("열쇠가 맞지")) writeToken("");
      })
      .finally(() => alive && setLoaded(request));
    return () => {
      alive = false;
    };
  }, [token, days, request]);

  if (!token) {
    return (
      <main className="grid min-h-dvh place-items-center bg-bg px-4">
        <form
          className={`${card} w-full max-w-[380px]`}
          onSubmit={(e) => {
            e.preventDefault();
            setError("");
            writeToken(typed.trim());
          }}
        >
          <h1 className={heading}>
            <KeyRound className="size-5 text-olive" />
            운영 대시보드
          </h1>
          <label className="grid gap-1.5 text-sm font-bold">
            관리자 열쇠
            <input
              type="password"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
              className="h-10 rounded-[10px] border-2 border-edge bg-bg px-3 font-normal outline-none focus:border-ink"
            />
          </label>
          <p className="text-[12.5px] text-fg-3">서버 backend/.env의 ADMIN_TOKEN 값이에요. 이 탭을 닫으면 잊어요.</p>
          {error && (
            <p role="alert" className="text-[13px] font-semibold text-warn">
              {error}
            </p>
          )}
          <button type="submit" disabled={!typed.trim()} className="h-10 rounded-[10px] border-[2.5px] border-ink bg-done font-extrabold text-[#1f2416] disabled:opacity-50">
            열기
          </button>
        </form>
      </main>
    );
  }

  const max = Math.max(1, ...(data?.daily.map((d) => d.count) ?? [1]));
  const downRate = data && data.feedback.up + data.feedback.down > 0
    ? Math.round((data.feedback.down / (data.feedback.up + data.feedback.down)) * 100)
    : null;

  return (
    <main className="min-h-dvh bg-bg px-3 py-5 sm:px-6">
      <div className="mx-auto grid max-w-[1100px] gap-4">
        <header className="flex flex-wrap items-center gap-3">
          <h1 className="font-stencil text-[24px] font-normal">운영 대시보드</h1>
          <div className="ml-auto flex items-center gap-2">
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              aria-label="기간"
              className="h-9 rounded-[10px] border-2 border-edge bg-soft px-2 text-[14px] font-bold"
            >
              <option value={1}>오늘까지 1일</option>
              <option value={7}>최근 7일</option>
              <option value={30}>최근 30일</option>
            </select>
            <button
              type="button"
              onClick={() => setTick((t) => t + 1)}
              disabled={busy}
              className="inline-flex h-9 items-center gap-1.5 rounded-[10px] border-2 border-edge bg-soft px-3 text-[14px] font-bold hover:border-ink disabled:opacity-50"
            >
              <RefreshCw className={`size-4 ${busy ? "animate-spin" : ""}`} />
              새로고침
            </button>
            <button
              type="button"
              onClick={() => {
                writeToken("");
                setData(null);
              }}
              className="h-9 rounded-[10px] border-2 border-edge px-3 text-[14px] font-bold text-fg-2 hover:border-ink"
            >
              잠그기
            </button>
          </div>
        </header>
        {error && (
          <p role="alert" className="text-[14px] font-semibold text-warn">
            {error}
          </p>
        )}

        {data && (
          <>
            <section className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="요약">
              {[
                ["질문", `${data.chats.total}건`, Object.entries(data.chats.by_kind).map(([k, n]) => `${KIND_NAMES[k] ?? k} ${n}`).join(" · ")],
                ["첫 글자 (중간값)", seconds(data.latency.first_p50_ms), `90%: ${seconds(data.latency.first_p90_ms)} · ${data.latency.cases}건`],
                ["전체 답변 (중간값)", seconds(data.latency.total_p50_ms), `90%: ${seconds(data.latency.total_p90_ms)}`],
                ["👎 비율", downRate == null ? "-" : `${downRate}%`, `👍 ${data.feedback.up} · 👎 ${data.feedback.down}`],
              ].map(([label, value, sub]) => (
                <div key={label} className={card}>
                  <span className="text-[12.5px] font-bold text-fg-3">{label}</span>
                  <b className="text-[24px] leading-none tabular-nums">{value}</b>
                  <span className="text-[12px] text-fg-3">{sub}</span>
                </div>
              ))}
            </section>

            <section className={card} aria-labelledby="daily">
              <h2 id="daily" className={heading}>
                <Gauge className="size-[18px] text-olive" />
                날짜별 질문 수
              </h2>
              <ol className="flex h-28 items-end gap-1.5">
                {data.daily.map((d) => (
                  <li key={d.day} className="grid flex-1 justify-items-center gap-1" title={`${d.day}: ${d.count}건`}>
                    <span className="text-[11px] tabular-nums text-fg-3">{d.count}</span>
                    <span className="w-full rounded-t bg-olive" style={{ height: `${(d.count / max) * 72}px`, minHeight: d.count ? 2 : 0 }} />
                    <span className="text-[10.5px] tabular-nums text-fg-3">{d.day.slice(5)}</span>
                  </li>
                ))}
              </ol>
            </section>

            <div className="grid gap-4 lg:grid-cols-2">
              <section className={card} aria-labelledby="slow">
                <h2 id="slow" className={heading}>
                  <Timer className="size-[18px] text-olive" />
                  느린 단계 <span className="text-[12px] font-semibold text-fg-3">앞 단계가 끝난 뒤부터 걸린 시간</span>
                </h2>
                {data.slow_steps.length ? (
                  <table className="w-full text-[13.5px]">
                    <thead className="text-left text-[12px] text-fg-3">
                      <tr>
                        <th className="py-1 font-semibold">단계</th>
                        <th className="py-1 text-right font-semibold">중간값</th>
                        <th className="py-1 text-right font-semibold">90%</th>
                        <th className="py-1 text-right font-semibold">횟수</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.slow_steps.map((s) => (
                        <tr key={s.node} className="border-t border-dashed border-line">
                          <td className="py-1.5 font-semibold">{NODE_NAMES[s.node] ?? s.node}</td>
                          <td className="py-1.5 text-right tabular-nums">{seconds(s.p50_ms)}</td>
                          <td className="py-1.5 text-right tabular-nums">{seconds(s.p90_ms)}</td>
                          <td className="py-1.5 text-right tabular-nums text-fg-3">{s.count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="text-[13.5px] text-fg-3">아직 자료를 찾아 답한 기록이 없어요.</p>
                )}
              </section>

              <section className={card} aria-labelledby="fails">
                <h2 id="fails" className={heading}>
                  <AlertTriangle className="size-[18px] text-warn" />
                  실패한 도구 호출 <span className="text-[12px] font-semibold text-fg-3">{data.failures.count}건</span>
                </h2>
                {Object.keys(data.failures.by_where).length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(data.failures.by_where).map(([where, n]) => (
                      <span key={where} className="rounded-md bg-warn-soft px-2 py-0.5 text-[12.5px] font-bold text-warn">
                        {where} {n}
                      </span>
                    ))}
                  </div>
                )}
                <ul className="grid gap-2">
                  {[...data.failures.recent.map((f) => ({ ...f, label: f.where })), ...data.errors.map((e) => ({ ...e, label: "답변 오류" }))]
                    .slice(0, 20)
                    .map((f, i) => (
                      <li key={i} className="grid gap-0.5 border-t border-dashed border-line pt-2 text-[13px]">
                        <span className="text-[12px] text-fg-3">
                          {when(f.at)} · <b className="text-fg-2">{f.label}</b>
                        </span>
                        <span className="font-semibold text-warn">{f.error}</span>
                        <span className="truncate text-fg-2">{f.question}</span>
                      </li>
                    ))}
                  {data.failures.count === 0 && data.errors.length === 0 && <li className="text-[13.5px] text-fg-3">실패가 없어요.</li>}
                </ul>
              </section>
            </div>

            <section className={card} aria-labelledby="down">
              <h2 id="down" className={heading}>
                <ThumbsDown className="size-[18px] text-warn" />
                👎 받은 답변
              </h2>
              {data.feedback.top_down_questions.length > 0 && (
                <div className="grid gap-1">
                  <span className="text-[12.5px] font-bold text-fg-3">👎가 많은 질문</span>
                  <ol className="grid gap-1 text-[13.5px]">
                    {data.feedback.top_down_questions.map((q) => (
                      <li key={q.question} className="flex gap-2">
                        <b className="tabular-nums text-warn">{q.count}</b>
                        <span>{q.question}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
              <ul className="grid gap-3">
                {data.feedback.recent_down.map((f, i) => (
                  <li key={i} className="grid gap-1 border-t border-dashed border-line pt-2 text-[13.5px]">
                    <span className="text-[12px] text-fg-3">{when(f.at)}</span>
                    <b>{f.question}</b>
                    <span className="line-clamp-2 text-fg-2">{f.answer}</span>
                    {f.comment && <span className="rounded-md bg-sunken px-2 py-1 text-[13px]">의견: {f.comment}</span>}
                  </li>
                ))}
                {data.feedback.recent_down.length === 0 && <li className="text-[13.5px] text-fg-3">👎가 없어요.</li>}
              </ul>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
