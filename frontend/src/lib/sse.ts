import type { ChatEvent } from "./types";

/** SSE 텍스트 버퍼에서 완성된 이벤트를 꺼낸다. 덜 받은 마지막 조각은 rest로 남긴다. */
export function parseSse(buffer: string): { events: ChatEvent[]; rest: string } {
  const events: ChatEvent[] = [];
  const blocks = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const rest = blocks.pop() ?? "";
  for (const block of blocks) {
    const event = block.match(/^event: (.*)$/m)?.[1];
    const data = block.match(/^data: (.*)$/m)?.[1];
    if (event) events.push({ event, data: data ? JSON.parse(data) : {} } as ChatEvent);
  }
  return { events, rest };
}

export interface ChatRequest {
  message: string;
  thread_id: string | null;
  user_id: string;
}

/** /api/chat 에 질문을 보내고 SSE 이벤트를 하나씩 돌려준다. */
export async function* streamChat(req: ChatRequest, signal?: AbortSignal): AsyncGenerator<ChatEvent> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `서버가 응답하지 않아요 (${res.status}). 잠시 후 다시 시도해 주세요.`);
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    const parsed = parseSse(buffer + value);
    buffer = parsed.rest;
    yield* parsed.events;
  }
}
