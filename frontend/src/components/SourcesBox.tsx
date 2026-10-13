import { citedCount, citedNumbers } from "@/lib/answer";
import type { Source } from "@/lib/types";

import { SourceList } from "./SourceList";

/** 근거 자료: 답변이 실제로 인용한 것만 먼저 보이고, 검색에 걸렸지만 인용하지 않은 것은 따로 접어 둔다 */
export function SourcesBox({ text, sources }: { text: string; sources: Source[] }) {
  const cited = citedNumbers(text);
  const used = citedCount(text, sources.length);
  // 번호를 하나도 못 찾으면(예: 번호 없는 짧은 답) 걸러 내지 않고 모두 보여 준다
  const filtered = used > 0 && used < sources.length;
  return (
    <details className="group grid gap-2 rounded-xl border border-line px-3.5 py-2.5">
      <summary className="cursor-pointer list-none text-sm font-bold">
        근거 자료 {filtered ? used : sources.length}개 <span className="font-medium text-fg-3 group-open:hidden">펼치기</span>
      </summary>
      <div className="mt-2 grid gap-3">
        <SourceList sources={sources} only={filtered ? cited : undefined} />
        {filtered && (
          <details className="grid gap-2">
            <summary className="cursor-pointer list-none text-[12.5px] font-semibold text-fg-3">
              인용하지 않은 참고 자료 {sources.length - used}개
            </summary>
            <div className="mt-2 opacity-80">
              <SourceList sources={sources} only={new Set(sources.map((_, i) => i + 1).filter((n) => !cited.has(n)))} />
            </div>
          </details>
        )}
      </div>
    </details>
  );
}
