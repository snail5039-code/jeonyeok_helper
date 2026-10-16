"use client";

import { Check, HeartPulse, NotebookPen, Save, Shield, Target, UserRound, Wand2, type LucideIcon } from "lucide-react";
import { useState } from "react";

import { profileCompleteness } from "@/lib/journey";
import { SERVICE_TYPE_LABELS, type Profile, type ServiceType } from "@/lib/types";

import { Book, BookTitle } from "./Book";
import { PhotoAvatar as Mascot } from "./PhotoAvatar";
import { Say } from "./Guide";

export const REGIONS = [
  "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기",
  "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]; // prettier-ignore
// '충청북도' → '충북'처럼 대화에서 알게 된 긴 이름을 목록 이름으로
const LONG_NAMES: Record<string, string> = {
  충청북: "충북", 충청남: "충남", 전라북: "전북", 전라남: "전남", 경상북: "경북", 경상남: "경남", 전남광주통합: "전남",
}; // prettier-ignore

const BRANCHES = ["육군", "해군", "공군", "해병대"];
const RANKS = ["이병", "일병", "상병", "병장", "하사", "중사", "상사", "원사", "준위", "소위", "중위", "대위", "소령", "중령", "대령"];
const EDUCATION = ["고등학교 졸업", "대학 재학·휴학", "대학 졸업", "대학원", "기타"];
const HOUSING = ["부모님과 함께", "자취 (월세)", "자취 (전세)", "기숙사", "내 집", "기타"];
const GOALS = ["취업", "공무원·군무원", "창업", "복학·진학", "귀농·귀어", "아직 모름"];
const INJURY = ["없음", "있음 (치료 중)", "있음 (보훈 심사 중)", "보훈대상자로 등록함"];

function splitRegion(region = ""): [string, string] {
  const long = Object.keys(LONG_NAMES).find((k) => region.startsWith(k));
  const sido = long ? LONG_NAMES[long] : REGIONS.find((r) => region.startsWith(r)) ?? "";
  const rest = region.split(/\s+/).slice(1).join(" ");
  return [sido, rest];
}

function caption(percent: number, hasType: boolean): string {
  if (!hasType) return "복무 형태부터 골라 주세요. 그것만 알아도 찾을 수 있는 게 확 늘어요.";
  if (percent >= 90) return "거의 다 적었어요. 이제 딱 맞는 임무만 골라 드릴게요.";
  if (percent >= 60) return "좋아요. 희망 직무나 자격증까지 적으면 더 정확해져요.";
  if (percent >= 30) return "지역이랑 전역 후 계획을 알려 주면 찾는 범위가 좁혀져요.";
  return "복무 형태 확인했어요. 지역과 전역일도 알려 주세요.";
}

interface Props {
  profile: Profile;
  demo: boolean;
  onSave: (profile: Profile) => Promise<void>;
  onFillJourney: () => void;
}

export function ProfileView({ profile, demo, onSave, onFillJourney }: Props) {
  const [form, setForm] = useState<Profile>(profile);
  const [initialSido, initialRest] = splitRegion(profile.region);
  const [sido, setSido] = useState(initialSido);
  const [area, setArea] = useState(initialRest);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [error, setError] = useState("");

  const set = (patch: Partial<Profile>) => {
    setForm((old) => ({ ...old, ...patch }));
    setState("idle");
  };
  const region = [sido, area.trim()].filter(Boolean).join(" ");
  const current: Profile = { ...form, region: region || undefined };
  const percent = profileCompleteness(current);

  const save = async () => {
    setState("saving");
    setError("");
    try {
      await onSave(current);
      setState("saved");
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장하지 못했어요.");
      setState("error");
    }
  };

  const num = (v: string) => (v === "" ? undefined : Number(v));
  const field = "h-11 w-full rounded-[10px] border-2 border-edge bg-soft px-3.5 text-[15px] font-normal outline-none focus:border-ink";

  return (
    <main className="flex-1 overflow-y-auto px-2.5 pt-4 pb-6 sm:px-5 sm:pt-6 lg:pb-12">
      <Book as="div" rings={16} className="mx-auto grid max-w-[800px] grid-cols-[minmax(0,1fr)] gap-6">
        <header className="grid gap-2">
          <div>
            <BookTitle>내 정보</BookTitle>
          </div>
          <p className="text-[15px] text-fg-2">
            적어 둘수록 답변과 작전도가 나한테 딱 맞게 바뀌어요. 다 안 써도 되고, 대화하면서 알려 줘도 돼요.
          </p>
        </header>

        <section className="grid grid-cols-[56px_minmax(0,1fr)] items-start gap-3">
          <Mascot rank={percent >= 90 ? "병장" : percent >= 50 ? "상병" : "이병"} size={56} />
          <div className="grid gap-2.5">
            <Say>{caption(percent, Boolean(current.service_type))}</Say>
            <div className="flex items-center gap-2 text-[13px] font-bold">
              <span className="text-fg-2">채운 정도</span>
              <div className="h-3 flex-1 overflow-hidden rounded-full border-2 border-ink bg-white">
                <div
                  className="h-full bg-[repeating-linear-gradient(-45deg,#556b2f_0_8px,#6b7f3a_8px_16px)] transition-[width]"
                  style={{ width: `${percent}%` }}
                />
              </div>
              <span className="tabular-nums">{percent}%</span>
            </div>
          </div>
        </section>

        <form
          className="grid grid-cols-[minmax(0,1fr)] gap-7"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <Section title="복무" icon={Shield}>
            <Chips label="복무 형태" required options={Object.keys(SERVICE_TYPE_LABELS)} labels={SERVICE_TYPE_LABELS} value={form.service_type} onPick={(v) => set({ service_type: v as ServiceType })} />
            <Chips label="군" options={BRANCHES} value={form.branch} onPick={(v) => set({ branch: v })} />
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="전역(예정) 계급">
                <input list="ranks" value={form.rank ?? ""} onChange={(e) => set({ rank: e.target.value || undefined })} placeholder="예: 병장" className={field} />
                <datalist id="ranks">{RANKS.map((r) => <option key={r} value={r} />)}</datalist>
              </Field>
              <Field label="복무 기간(년)">
                <input type="number" inputMode="decimal" min={0} max={50} step={0.5} placeholder="예: 1.5" value={form.service_years ?? ""} onChange={(e) => set({ service_years: num(e.target.value) })} className={field} />
              </Field>
              <Field label="전역(예정)일">
                <input type="month" value={form.discharge_date?.slice(0, 7) ?? ""} onChange={(e) => set({ discharge_date: e.target.value || undefined })} className={field} />
              </Field>
            </div>
            <Field label="특기·병과" hint="민간 자격증·직무와 이어지는 경우가 많아요">
              <input value={form.specialty ?? ""} onChange={(e) => set({ specialty: e.target.value || undefined })} placeholder="예: 운전, 정보통신, 취사" className={field} />
            </Field>
          </Section>

          <Section title="나" icon={UserRound}>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="나이">
                <input type="number" inputMode="numeric" min={15} max={100} placeholder="예: 24" value={form.age ?? ""} onChange={(e) => set({ age: num(e.target.value) })} className={field} />
              </Field>
              <Field label="사는 곳 (시·도)">
                <select value={sido} onChange={(e) => { setSido(e.target.value); setState("idle"); }} className={field}>
                  <option value="">선택 안 함</option>
                  {REGIONS.map((r) => <option key={r}>{r}</option>)}
                </select>
              </Field>
              <Field label="시·군·구">
                <input value={area} onChange={(e) => { setArea(e.target.value); setState("idle"); }} placeholder="예: 해운대구" className={field} />
              </Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="학력·학업">
                <Select value={form.education} options={EDUCATION} onChange={(v) => set({ education: v })} className={field} />
              </Field>
              <Field label="주거">
                <Select value={form.housing} options={HOUSING} onChange={(v) => set({ housing: v })} className={field} />
              </Field>
            </div>
          </Section>

          <Section title="전역 후 계획" icon={Target}>
            <Chips
              label="하고 싶은 것 (여러 개)"
              options={GOALS}
              multi
              value={form.goals}
              onPick={(v) => {
                const goals = form.goals ?? [];
                set({ goals: goals.includes(v) ? goals.filter((g) => g !== v) : [...goals, v] });
              }}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="희망 분야·직무">
                <input value={form.desired_job ?? ""} onChange={(e) => set({ desired_job: e.target.value || undefined })} placeholder="예: 시설관리, 경찰, IT 개발" className={field} />
              </Field>
              <Field label="가진 자격증">
                <input value={form.certificates ?? ""} onChange={(e) => set({ certificates: e.target.value || undefined })} placeholder="예: 운전면허 1종, 컴활 2급" className={field} />
              </Field>
            </div>
          </Section>

          <Section title="보훈·건강" icon={HeartPulse}>
            <Chips label="복무 중 다치거나 아픈 적" options={INJURY} value={form.injury} onPick={(v) => set({ injury: v })} />
          </Section>

          <Section title="메모" icon={NotebookPen}>
            <Field label="그 밖에 알려 줄 것" hint="고민이나 상황을 편하게 적어 주세요. 답변할 때 참고해요.">
              <textarea
                rows={3}
                maxLength={1000}
                value={form.memo ?? ""}
                onChange={(e) => set({ memo: e.target.value || undefined })}
                placeholder="예: 월세 살고 있어서 주거 지원이 제일 궁금함. 내년 3월 복학 예정."
                className="w-full resize-y rounded-[10px] border-2 border-edge bg-soft px-3.5 py-2.5 text-[15px] font-normal outline-none focus:border-ink"
              />
            </Field>
          </Section>

          <div className="sticky bottom-2 z-10 grid w-fit max-w-full gap-2 rounded-xl border-2 border-edge bg-soft/95 px-4 py-3 shadow-[3px_3px_0_rgb(0_0_0_/_0.15)] backdrop-blur">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="submit"
                disabled={state === "saving"}
                className="inline-flex h-11 items-center gap-1.5 rounded-[10px] border-[2.5px] border-[#1f2416] bg-done px-4 text-[15px] font-extrabold text-[#1f2416] shadow-[3px_3px_0_var(--ink)] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none disabled:opacity-60"
              >
                {state === "saved" ? <Check className="size-[18px]" /> : <Save className="size-[18px]" />}
                {state === "saving" ? "저장 중…" : state === "saved" ? "저장 완료!" : "저장하기"}
              </button>
              {state === "saved" && current.service_type && (
                <button
                  type="button"
                  onClick={onFillJourney}
                  className="inline-flex h-11 items-center gap-1.5 rounded-[10px] border-2 border-edge bg-bg px-3.5 text-[14px] font-bold text-fg hover:border-ink"
                >
                  <Wand2 className="size-4" />이 정보로 작전도 만들기
                </button>
              )}
              {demo && <span className="text-[12.5px] text-fg-3">데모 모드: 이 브라우저에만 저장돼요</span>}
            </div>
            {error && <p role="alert" className="text-[13px] font-semibold text-warn">{error}</p>}
          </div>
        </form>
      </Book>
    </main>
  );
}

function Section({ title, icon: Icon, children }: { title: string; icon: LucideIcon; children: React.ReactNode }) {
  return (
    <fieldset className="grid gap-4 rounded-xl border-2 border-edge bg-soft/70 p-4 md:p-5">
      <legend className="flex items-center gap-1.5 px-1">
        <Icon className="size-[18px] text-olive" strokeWidth={2.2} />
        <span className="font-stencil text-[19px] font-normal">{title}</span>
      </legend>
      {children}
    </fieldset>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="grid content-start gap-1.5 text-sm font-bold">
      {label}
      {children}
      {hint && <span className="text-[12.5px] font-normal text-fg-3">{hint}</span>}
    </label>
  );
}

function Select({ value, options, onChange, className }: { value?: string; options: string[]; onChange: (v?: string) => void; className: string }) {
  return (
    <select value={value ?? ""} onChange={(e) => onChange(e.target.value || undefined)} className={className}>
      <option value="">선택 안 함</option>
      {options.map((o) => <option key={o}>{o}</option>)}
    </select>
  );
}

function Chips({
  label,
  options,
  labels,
  value,
  multi = false,
  required = false,
  onPick,
}: {
  label: string;
  options: string[];
  labels?: Record<string, string>;
  value?: string | string[];
  multi?: boolean;
  required?: boolean;
  onPick: (v: string) => void;
}) {
  const on = (o: string) => (Array.isArray(value) ? value.includes(o) : value === o);
  return (
    <div className="grid gap-2" role="group" aria-label={label}>
      <span className="text-sm font-bold">
        {label} {required && <span className="font-medium text-warn">필수</span>}
        {multi && <span className="font-medium text-fg-3"> 여러 개 골라도 돼요</span>}
      </span>
      <div className="flex flex-wrap gap-2">
        {options.map((o) => (
          <button
            key={o}
            type="button"
            aria-pressed={on(o)}
            onClick={() => onPick(o)}
            className={`inline-flex h-9 items-center gap-1 rounded-full border-2 px-3.5 text-sm font-semibold ${
              on(o) ? "border-olive bg-olive text-olive-ink" : "border-edge bg-soft text-fg-2 hover:border-ink"
            }`}
          >
            {on(o) && <Check className="size-4" strokeWidth={2.2} />}
            {labels?.[o] ?? o}
          </button>
        ))}
      </div>
    </div>
  );
}
