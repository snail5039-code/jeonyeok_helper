// 이어 하기 코드: 로그인 없이 다른 기기에서 같은 기록(익명 ID)을 연다.

import { requestJson } from "./api";

const enc = encodeURIComponent;

/** 이 브라우저의 기록에 이어 둔 코드 (없으면 null) */
export async function fetchResumeCode(userId: string): Promise<string | null> {
  const res = await fetch(`/api/resume-code/${enc(userId)}`);
  if (!res.ok) return null;
  return (await res.json()).code ?? null;
}

/** 코드를 새로 만든다. 이전 코드는 더 이상 쓸 수 없다 */
export async function makeResumeCode(userId: string): Promise<string> {
  const res = await requestJson("POST", `resume-code/${enc(userId)}`, undefined, "코드를 만들지 못했어요.");
  return (await res.json()).code;
}

/** 코드로 기록의 익명 ID를 찾는다 */
export async function findByCode(code: string): Promise<string> {
  const res = await requestJson("POST", "resume", { code }, "코드에 맞는 기록이 없어요. 코드를 다시 확인해 주세요.");
  return (await res.json()).user_id;
}

/** QR로 찍으면 바로 이어지는 주소 (이어진 것을 바로 보도록 작전도 화면으로 연다) */
export function resumeUrl(code: string, origin: string): string {
  return `${origin}/?resume=${enc(code)}&page=journey`;
}

/** 주소의 ?resume=코드 를 꺼내고, 주소에서는 지운다 (새로고침해도 다시 바꾸지 않게) */
export function takeResumeParam(url: URL): { code: string | null; cleaned: string } {
  const code = url.searchParams.get("resume");
  url.searchParams.delete("resume");
  return { code, cleaned: url.pathname + (url.search ? url.search : "") + url.hash };
}
