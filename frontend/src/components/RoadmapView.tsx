"use client";

import { ArrowRight, Check, CircleHelp, ExternalLink, MessageCircleQuestion, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  REGIONS,
  demoRoadmap,
  fetchRoadmap,
  loadDone,
  progress,
  saveDone,
  type Roadmap,
  type RoadmapInput,
} from "@/lib/roadmap";
import { SERVICE_TYPE_LABELS, type Profile, type ServiceType, type Source } from "@/lib/types";

const SOURCE_LABEL: Record<Source["type"], string> = { regulation: "법령", benefit: "혜택", institution: "기관" };
const CHIP = "inline-flex h-9 items-center rounded-full border px-3.5 text-sm font-medium";

// '충청북도' → '충북'처럼 긴 시도 이름을 목록의 이름으로
const LONG_NAMES: Record<string, string> = {
  충청북: "충북", 충청남: "충남", 전라북: "전북", 전라남: "전남", 경상북: "경북", 경상남: "경남",
}; // prettier-ignore

function toInput(p: Profile): Partial<RoadmapInput> {
  // 대화에서 알게 된 지역('서울특별시 강남구', '충청북도')을 시도 이름으로 맞춘다.
  const raw = p.region ?? "";
  const long = Object.keys(LONG_NAMES).find((k) => raw.startsWith(k));
  const region = long ? LONG_NAMES[long] : REGIONS.find((r) => raw.startsWith(r));
  return { service_type: p.service_type, service_years: p.service_years, age: p.age, region };
}

interface Props {
  profile: Profile;
  demo: boolean;
  onAsk: (question: string) => void;
}

export function RoadmapView({ profile, demo, onAsk }: Props) {
  const [input, setInput] = useState<Partial<RoadmapInput>>(() => toInput(profile));
  const [roadmap, setRoadmap] = useState<Roadmap | null>(null);
  const [state, setState] = useState<"form" | "loading" | "done" | "error">("form");
  const [error, setError] = useState("");
  // 메뉴를 눌러야 열리는 화면이라 서버 렌더링 없이 브라우저에서만 그려진다. 바로 읽어도 된다.
  const [done, setDone] = useState<Set<string>>(loadDone);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => () => abort.current?.abort(), []);

  const build = async () => {
    if (!input.service_type) return;
    const req = { ...input, service_type: input.service_type } as RoadmapInput;
    setState("loading");
    setError("");
    if (demo) {
      await new Promise((r) => setTimeout(r, 900));
      setRoadmap(demoRoadmap(req));
      setState("done");
      return;
    }
    abort.current = new AbortController();
    try {
      setRoadmap(await fetchRoadmap(req, abort.current.signal));
      setState("done");
    } catch (e) {
      if (abort.current.signal.aborted) return;
      setError(e instanceof Error ? e.message : "로드맵을 만들지 못했어요.");
      setState("error");
    }
  };

  const toggle = (id: string) => {
    const next = new Set(done);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setDone(next);
    saveDone(next);
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto grid max-w-[760px] grid-cols-[minmax(0,1fr)] gap-8 px-4 pt-8 pb-16 lg:pt-12">
        <header className="grid gap-2">
          <h1 className="text-[26px] leading-[1.35] font-bold tracking-[-0.03em] md:text-[30px]">내 전역 로드맵</h1>
          <p className="text-[15px] text-fg-2">
            복무 정보를 한 번 입력하면, 전역 직후부터 취업·학업·연금까지 할 일을 순서대로 정리해 드려요.
          </p>
        </header>

        {state !== "done" && (
          <ProfileForm
            input={input}
            // 바뀐 값만 받아 이전 상태에 합친다 (연달아 바꿔도 앞의 값이 덮이지 않게)
            onChange={(patch) => setInput((prev) => ({ ...prev, ...patch }))}
            onSubmit={build}
            loading={state === "loading"}
          />
        )}

        {state === "loading" && <Loading />}

        {state === "error" && (
          <div role="alert" className="grid grid-cols-[20px_1fr] gap-2.5 rounded-xl border border-line px-4 py-3.5 text-sm text-fg-2">
            <CircleHelp className="mt-0.5 size-[18px] text-warn" strokeWidth={1.8} />
            <span>{error}</span>
          </div>
        )}

        {state === "done" && roadmap && (
          <Result
            roadmap={roadmap}
            input={input as RoadmapInput}
            done={done}
            onToggle={toggle}
            onEdit={() => setState("form")}
            onAsk={onAsk}
          />
        )}
      </div>
    </div>
  );
}

function ProfileForm({
  input,
  onChange,
  onSubmit,
  loading,
}: {
  input: Partial<RoadmapInput>;
  onChange: (patch: Partial<RoadmapInput>) => void;
  onSubmit: () => void;
  loading: boolean;
}) {
  const num = (v: string) => (v === "" ? undefined : Number(v));
  const field = "h-11 w-full rounded-xl border border-line-strong bg-bg px-3.5 text-[15px] outline-none focus:border-accent";
  return (
    <form
      className="grid gap-6 rounded-2xl border border-line p-5 shadow-card md:p-6"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <fieldset className="grid gap-2.5">
        <legend className="mb-2.5 text-sm font-bold">
          어떻게 전역하셨나요? <span className="font-medium text-warn">필수</span>
        </legend>
        <div className="flex flex-wrap gap-2">
          {(Object.keys(SERVICE_TYPE_LABELS) as ServiceType[]).map((t) => {
            const on = input.service_type === t;
            return (
              <button
                key={t}
                type="button"
                aria-pressed={on}
                onClick={() => onChange({ service_type: t })}
                className={`${CHIP} ${on ? "border-accent bg-accent-soft text-accent" : "border-line-strong text-fg-2 hover:border-accent"}`}
              >
                {on && <Check className="mr-1 size-4" strokeWidth={2.2} />}
                {SERVICE_TYPE_LABELS[t]}
              </button>
            );
          })}
        </div>
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-3">
        <label className="grid gap-1.5 text-sm font-bold">
          사는 지역
          <select
            value={input.region ?? ""}
            onChange={(e) => onChange({ region: e.target.value || undefined })}
            className={field}
          >
            <option value="">선택 안 함</option>
            {REGIONS.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </label>
        <label className="grid gap-1.5 text-sm font-bold">
          나이
          <input
            type="number"
            inputMode="numeric"
            min={15}
            max={100}
            placeholder="예: 24"
            value={input.age ?? ""}
            onChange={(e) => onChange({ age: num(e.target.value) })}
            className={field}
          />
        </label>
        <label className="grid gap-1.5 text-sm font-bold">
          복무 기간(년)
          <input
            type="number"
            inputMode="decimal"
            min={0}
            max={50}
            step={0.5}
            placeholder="예: 1.5"
            value={input.service_years ?? ""}
            onChange={(e) => onChange({ service_years: num(e.target.value) })}
            className={field}
          />
        </label>
      </div>
      <p className="-mt-2 text-[13px] text-fg-3">지역과 나이를 알려 주시면 그 지역 혜택과 청년정책까지 찾아요.</p>

      <button
        type="submit"
        disabled={!input.service_type || loading}
        className="inline-flex h-12 items-center justify-center gap-1.5 rounded-xl bg-accent text-[15px] font-bold text-accent-ink disabled:opacity-50"
      >
        {loading ? "만드는 중…" : "로드맵 만들기"}
        {!loading && <ArrowRight className="size-[18px]" />}
      </button>
    </form>
  );
}

function Loading() {
  return (
    <div className="grid gap-3 rounded-2xl border border-line p-5" aria-live="polite">
      <div className="flex items-center gap-2 text-sm text-fg-2">
        <span className="step-dot" />
        법령, 혜택, 청년정책, 관할 보훈관서를 모아 정리하고 있어요. 20초쯤 걸려요.
      </div>
      <div className="skeleton-line" />
      <div className="skeleton-line w-[80%]" />
      <div className="skeleton-line w-[60%]" />
    </div>
  );
}

function Result({
  roadmap,
  input,
  done,
  onToggle,
  onEdit,
  onAsk,
}: {
  roadmap: Roadmap;
  input: RoadmapInput;
  done: Set<string>;
  onToggle: (id: string) => void;
  onEdit: () => void;
  onAsk: (q: string) => void;
}) {
  const p = progress(roadmap, done);
  const chips = [
    SERVICE_TYPE_LABELS[input.service_type],
    input.region,
    input.age && `${input.age}세`,
    input.service_years && `${input.service_years}년 복무`,
  ].filter(Boolean) as string[];

  if (!roadmap.stages.length) {
    return <p className="rounded-xl border border-line p-4 text-sm text-fg-2">{roadmap.intro}</p>;
  }
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-7">
      <section className="grid gap-3 rounded-2xl bg-soft p-5">
        <div className="flex flex-wrap items-center gap-1.5">
          {chips.map((c) => (
            <span key={c} className="inline-flex h-7 items-center rounded-full border border-line-strong bg-bg px-2.5 text-[13px] font-medium text-fg-2">
              {c}
            </span>
          ))}
          <button type="button" onClick={onEdit} className="ml-auto inline-flex items-center gap-1 text-[13px] font-semibold text-accent">
            <RotateCcw className="size-3.5" />
            조건 바꾸기
          </button>
        </div>
        <p className="text-[15px] leading-relaxed">{roadmap.intro}</p>
        <div className="grid gap-1.5">
          <div className="flex justify-between text-[13px] font-semibold">
            <span>진행 상황</span>
            <span className="tabular-nums text-fg-2">
              {p.done} / {p.total} 완료
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-sunken" role="progressbar" aria-valuenow={p.done} aria-valuemax={p.total}>
            <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${p.total ? (p.done / p.total) * 100 : 0}%` }} />
          </div>
        </div>
      </section>

      <ol className="grid grid-cols-[minmax(0,1fr)] gap-7">
        {roadmap.stages.map((stage, si) => (
          <li key={stage.key} className="grid grid-cols-[minmax(0,1fr)] gap-3">
            <h2 className="flex items-center gap-2.5 text-[17px] font-bold">
              <span className="grid size-7 place-items-center rounded-full bg-accent text-[13px] text-accent-ink tabular-nums">{si + 1}</span>
              {stage.title}
            </h2>
            <ul className="grid grid-cols-[minmax(0,1fr)] gap-2.5 sm:ml-[38px]">
              {stage.items.map((item) => {
                const checked = done.has(item.id);
                return (
                  <li key={item.id} className={`grid grid-cols-[24px_minmax(0,1fr)] gap-3 rounded-xl border p-4 ${checked ? "border-line bg-soft" : "border-line-strong bg-bg"}`}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => onToggle(item.id)}
                      aria-label={`${item.title} 완료`}
                      className="mt-0.5 size-5 accent-[var(--accent)]"
                    />
                    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-1.5">
                      <div className={`text-[15px] font-bold ${checked ? "text-fg-3 line-through" : ""}`}>{item.title}</div>
                      <div className="text-[14.5px] font-semibold text-accent">{item.action}</div>
                      {item.detail && <p className="text-sm leading-relaxed text-fg-2">{item.detail}</p>}
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        {item.sources.map((s) =>
                          s.url ? (
                            <a
                              key={s.title}
                              href={s.url}
                              target="_blank"
                              rel="noopener"
                              className="inline-flex max-w-full items-center gap-1 rounded-md bg-sunken px-2 py-1 text-[12.5px] text-fg-2 hover:text-accent"
                            >
                              <b className={`shrink-0 whitespace-nowrap ${s.type === "regulation" ? "text-law" : ""}`}>{SOURCE_LABEL[s.type]}</b>
                              <span className="min-w-0 truncate">{s.title}</span>
                              <ExternalLink className="size-3 shrink-0" />
                            </a>
                          ) : (
                            <span key={s.title} className="inline-flex max-w-full items-center gap-1 rounded-md bg-sunken px-2 py-1 text-[12.5px] text-fg-2">
                              <b className={`shrink-0 whitespace-nowrap ${s.type === "regulation" ? "text-law" : ""}`}>{SOURCE_LABEL[s.type]}</b>
                              <span className="min-w-0 truncate">{s.title}</span>
                            </span>
                          ),
                        )}
                        <button
                          type="button"
                          onClick={() => onAsk(`${item.title}에 대해 자세히 알려주세요`)}
                          className="ml-auto inline-flex items-center gap-1 text-[12.5px] font-semibold text-fg-2 hover:text-accent"
                        >
                          <MessageCircleQuestion className="size-3.5" />
                          자세히 묻기
                        </button>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ol>
      <p className="text-[13px] text-fg-3">
        체크한 항목은 이 브라우저에만 저장돼요. 정확한 자격과 기한은 소관 기관에 꼭 확인하세요.
      </p>
    </div>
  );
}
