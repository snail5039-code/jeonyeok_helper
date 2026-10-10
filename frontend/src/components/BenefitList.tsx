import { Briefcase, Check, ExternalLink, Gift, GraduationCap, IdCard, Landmark, MapPin, ShieldCheck } from "lucide-react";

import { benefitKind, type BenefitBlock } from "@/lib/answer";
import type { Source } from "@/lib/types";

import { InlineText } from "./InlineText";

const ICONS = {
  pension: Landmark,
  job: Briefcase,
  school: GraduationCap,
  reserve: IdCard,
  merit: ShieldCheck,
  region: MapPin,
  other: Gift,
};

function BenefitCard({ benefit, sources }: { benefit: BenefitBlock; sources: Source[] }) {
  const Icon = ICONS[benefitKind(benefit.title + benefit.org)];
  const target = benefit.fields.filter(([k]) => /대상/.test(k));
  const basis = benefit.fields.filter(([k]) => /근거|법령/.test(k));
  const meta = benefit.fields.filter(([k]) => !/대상|근거|법령/.test(k));
  // 같은 이름의 혜택·기관 출처가 있으면 바로 가는 링크로 쓴다.
  const link = sources.find(
    (s) =>
      s.type !== "regulation" &&
      /^https?:\/\//.test(s.url) &&
      (s.title.includes(benefit.title) || benefit.title.includes(s.title)),
  );

  return (
    <div className="grid grid-cols-[36px_minmax(0,1fr)] items-start gap-3.5 border-b border-line px-3.5 py-4 last:border-b-0 md:grid-cols-[40px_minmax(0,1fr)_auto] md:p-[18px]">
      <span className="grid size-9 place-items-center rounded-[11px] bg-accent-soft text-accent md:size-10">
        <Icon className="size-[18px]" strokeWidth={1.8} />
      </span>
      <div>
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <b className="text-base font-bold">
            <InlineText text={benefit.title} sources={sources} />
          </b>
          {benefit.org && <small className="text-[13px] text-fg-3">{benefit.org}</small>}
        </div>
        {(meta.length > 0 || benefit.extra.length > 0) && (
          <div className="mt-1.5 mb-2.5 grid gap-0.5 text-[14.5px] leading-relaxed text-fg-2">
            {meta.map(([k, v]) => (
              <span key={k}>
                <b className="mr-1.5 font-semibold text-fg-3">{k}</b>
                <InlineText text={v} sources={sources} />
              </span>
            ))}
            {benefit.extra.map((line) => (
              <span key={line}>
                <InlineText text={line} sources={sources} />
              </span>
            ))}
          </div>
        )}
        {(target.length > 0 || basis.length > 0) && (
          <div className="flex flex-wrap gap-1.5">
            {target.map(([, v]) => (
              <span key={v} className="inline-flex h-6 items-center gap-1 rounded-md bg-accent-soft px-2 text-xs font-semibold text-accent">
                <Check className="size-[13px]" strokeWidth={2.2} />
                <InlineText text={v} sources={sources} />
              </span>
            ))}
            {basis.map(([, v]) => (
              <span key={v} className="inline-flex h-6 items-center rounded-md bg-law-soft px-2 text-xs font-semibold text-law">
                <InlineText text={v} sources={sources} />
              </span>
            ))}
          </div>
        )}
      </div>
      {link && (
        <a
          href={link.url}
          target="_blank"
          rel="noopener"
          className="col-start-2 inline-flex h-[34px] items-center gap-1.5 justify-self-start rounded-lg border border-line-strong bg-bg px-3 text-[13px] font-semibold whitespace-nowrap hover:border-fg-3 md:col-start-3 md:mt-0.5"
        >
          자세히
          <ExternalLink className="size-[15px]" strokeWidth={1.8} />
        </a>
      )}
    </div>
  );
}

export function BenefitList({ benefits, sources }: { benefits: BenefitBlock[]; sources: Source[] }) {
  return (
    <section>
      <div className="mb-2.5 flex items-baseline gap-2">
        <h2 className="text-[17px] font-bold">받을 수 있는 혜택</h2>
        <span className="font-bold tabular-nums text-accent">{benefits.length}</span>
      </div>
      <div className="overflow-hidden rounded-[18px] border border-line">
        {benefits.map((b) => (
          <BenefitCard key={b.title} benefit={b} sources={sources} />
        ))}
      </div>
    </section>
  );
}
