/**
 * 백엔드(/api/...)에 JSON을 POST한다. 실패하면 서버가 준 안내(detail)나 fallback 문장으로
 * 예외를 던진다. 응답 본문은 호출하는 쪽이 읽는다 (JSON 또는 SSE 스트림).
 */
export async function postJson(path: string, body: unknown, fallback: string, signal?: AbortSignal): Promise<Response> {
  const res = await fetch(`/api/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(typeof data.detail === "string" && data.detail ? data.detail : fallback);
  }
  return res;
}
