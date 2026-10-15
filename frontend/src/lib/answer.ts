// 에이전트 답변 글을 화면 구조로 바꾼다.
// 답변 프롬프트가 혜택마다 아래 블록을 쓰도록 되어 있다 (agents/prompts.py RESPOND_PROMPT).
//   ### 혜택명 | 소관기관
//   - 대상: ...
//   - 내용: ...
//   - 신청: ...
//   - 근거: ...

export interface BenefitBlock {
  title: string;
  org: string;
  fields: [label: string, value: string][];
  extra: string[];
}

export interface ParsedAnswer {
  lead: string[];
  benefits: BenefitBlock[];
  tail: string[];
}

/** 답변을 [요약 문단] [혜택 블록들] [마무리 문단]으로 나눈다. */
export function parseAnswer(text: string): ParsedAnswer {
  const lead: string[] = [];
  const benefits: BenefitBlock[] = [];
  const tail: string[] = [];
  let current: BenefitBlock | null = null;

  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;

    const heading = line.match(/^#{2,4}\s+(?:\d+\.\s*)?(.+)$/);
    if (heading) {
      const [title, org = ""] = heading[1].split("|").map((s) => s.trim());
      current = { title, org, fields: [], extra: [] };
      benefits.push(current);
      continue;
    }

    const bullet = line.match(/^[-*•]\s+(.*)$/);
    if (current && bullet) {
      const kv = bullet[1].match(/^\*{0,2}([^:：*]{1,8})\*{0,2}\s*[:：]\s*(.+)$/);
      if (kv) current.fields.push([kv[1].trim(), kv[2].trim()]);
      else current.extra.push(bullet[1]);
      continue;
    }

    // 제목 바로 아래 문장은 그 블록의 설명이다 (예: '경기도 지역 채용 정보' 아래 안내 문장과 공고 목록)
    if (current && !current.fields.length && !current.extra.length) {
      current.extra.push(line);
      continue;
    }
    if (current) {
      current = null; // 블록 밖의 문단이 나오면 블록이 끝난 것
      tail.push(line);
      continue;
    }
    (benefits.length ? tail : lead).push(line);
  }
  return { lead, benefits, tail };
}

export type InlinePart =
  | { kind: "text"; value: string }
  | { kind: "bold"; value: string }
  | { kind: "cite"; index: number };

/** **굵게**와 [n] 출처 번호를 나눠서, 컴포넌트가 안전하게 그릴 수 있게 한다. */
export function splitInline(text: string): InlinePart[] {
  const parts: InlinePart[] = [];
  // [1]뿐 아니라 [2, 3]처럼 여러 번호를 묶은 것도 번호마다 배지로 (묶음은 글자 그대로 보였음)
  const re = /\*\*(.+?)\*\*|\[(\d+(?:\s*,\s*\d+)*)\]/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index > last) parts.push({ kind: "text", value: text.slice(last, m.index) });
    if (m[1] !== undefined) parts.push({ kind: "bold", value: m[1] });
    else for (const n of m[2].split(",")) parts.push({ kind: "cite", index: Number(n.trim()) });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ kind: "text", value: text.slice(last) });
  return parts;
}

/** 혜택 이름으로 아이콘 종류를 고른다. */
export function benefitKind(text: string): "pension" | "job" | "school" | "reserve" | "merit" | "region" | "other" {
  if (/연금|크레딧/.test(text)) return "pension";
  if (/취업|일자리|전직|구직|훈련/.test(text)) return "job";
  if (/학|장학|등록금/.test(text)) return "school";
  if (/예비군|병역|병무|병적/.test(text)) return "reserve";
  if (/보훈|유공/.test(text)) return "merit";
  if (/서울|경기|부산|지역|청년/.test(text)) return "region";
  return "other";
}

/** 답변 본문의 [1], [2, 3] 같은 근거 번호 (1부터) */
export function citedNumbers(text: string): Set<number> {
  const out = new Set<number>();
  for (const m of text.matchAll(/\[(\d+(?:\s*,\s*\d+)*)\]/g)) {
    for (const n of m[1].split(",")) out.add(Number(n.trim()));
  }
  return out;
}

/** 답변이 인용한 근거 수. 번호를 하나도 못 찾으면(번호 없는 짧은 답) 전체를 센다. */
export function citedCount(text: string, total: number): number {
  const used = [...citedNumbers(text)].filter((n) => n >= 1 && n <= total).length;
  return used > 0 ? used : total;
}
