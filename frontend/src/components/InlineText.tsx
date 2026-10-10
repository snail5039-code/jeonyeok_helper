import { splitInline } from "@/lib/answer";
import type { Source } from "@/lib/types";

const isHttp = (url: string) => /^https?:\/\//.test(url);

/** 답변 한 줄: **굵게**와 [n] 출처 번호를 링크로 그린다. */
export function InlineText({ text, sources }: { text: string; sources: Source[] }) {
  return (
    <>
      {splitInline(text).map((part, i) => {
        if (part.kind === "text") return part.value;
        if (part.kind === "bold") return <strong key={i}>{part.value}</strong>;
        const src = sources[part.index - 1];
        if (!src) return `[${part.index}]`;
        const className =
          "mx-px inline-grid h-[18px] min-w-[18px] place-items-center rounded-[5px] bg-sunken px-1 align-[2px] text-[11px] font-bold tabular-nums text-fg-2";
        return isHttp(src.url) ? (
          <a
            key={i}
            href={src.url}
            target="_blank"
            rel="noopener"
            title={src.title}
            className={`${className} hover:bg-accent-soft hover:text-accent`}
          >
            {part.index}
          </a>
        ) : (
          <span key={i} title={src.title} className={className}>
            {part.index}
          </span>
        );
      })}
    </>
  );
}
