import type { Source } from "@/lib/types";

const KIND: Record<Source["type"], [label: string, className: string]> = {
  regulation: ["법령", "bg-law-soft text-law"],
  benefit: ["혜택", "bg-sunken text-fg-2"],
  institution: ["기관", "bg-sunken text-fg-2"],
};

const domain = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
};

/** 번호(i + 1)는 답변 본문의 [n]과 같아야 하므로, 걸러도 원래 번호를 쓴다 */
export function SourceList({ sources, only }: { sources: Source[]; only?: Set<number> }) {
  return (
    <div className="grid gap-2">
      {sources.map((s, i) => {
        if (only && !only.has(i + 1)) return null;
        const [label, kindClass] = KIND[s.type] ?? ["출처", "bg-sunken text-fg-2"];
        const body = (
          <>
            <span className="pt-px text-xs font-bold tabular-nums text-fg-3">{i + 1}</span>
            <span>
              <b className="block text-[13.5px] leading-[1.45] font-semibold">{s.title}</b>
              <small className="mt-1 flex items-center gap-1.5 text-xs text-fg-3">
                <span className={`rounded px-1.5 py-px text-[11px] font-bold ${kindClass}`}>{label}</span>
                {domain(s.url)}
              </small>
            </span>
          </>
        );
        const className =
          "grid grid-cols-[22px_1fr] gap-2.5 rounded-xl border border-line p-3 hover:border-line-strong hover:bg-soft";
        return /^https?:\/\//.test(s.url) ? (
          <a key={i} href={s.url} target="_blank" rel="noopener" className={className}>
            {body}
          </a>
        ) : (
          <div key={i} className={className}>
            {body}
          </div>
        );
      })}
    </div>
  );
}
