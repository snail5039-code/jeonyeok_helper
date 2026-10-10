import { afterEach, describe, expect, it, vi } from "vitest";

import { parseSse, streamChat } from "./sse";

const sse = (event: string, data: object) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

describe("parseSse", () => {
  it("완성된 이벤트만 꺼내고 덜 받은 조각은 남긴다", () => {
    const buffer = sse("step", { label: "법령 검색" }) + "event: answ";
    const { events, rest } = parseSse(buffer);
    expect(events).toEqual([{ event: "step", data: { label: "법령 검색" } }]);
    expect(rest).toBe("event: answ");
  });

  it("CRLF 줄바꿈도 처리한다", () => {
    const { events } = parseSse("event: done\r\ndata: {}\r\n\r\n");
    expect(events).toEqual([{ event: "done", data: {} }]);
  });
});

describe("streamChat", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("조각나서 도착한 스트림을 이벤트 순서대로 돌려준다", async () => {
    const body = sse("thread", { thread_id: "t1" }) + sse("answer", { text: "답", sources: [], profile: {} });
    // 이벤트 경계와 상관없이 7바이트씩 잘라 보낸다.
    const chunks = body.match(/[\s\S]{1,7}/g)!;
    const stream = new ReadableStream({
      start(controller) {
        const enc = new TextEncoder();
        chunks.forEach((c) => controller.enqueue(enc.encode(c)));
        controller.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(stream, { status: 200 })));

    const events = [];
    for await (const e of streamChat({ message: "q", thread_id: null, user_id: "u" })) events.push(e);

    expect(events.map((e) => e.event)).toEqual(["thread", "answer"]);
  });

  it("서버 오류는 서버가 준 이유와 함께 예외로 알린다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ detail: "GOOGLE_API_KEY가 설정되지 않았습니다." }, { status: 503 })),
    );
    const run = async () => {
      for await (const _ of streamChat({ message: "q", thread_id: null, user_id: "u" })) void _;
    };
    await expect(run()).rejects.toThrow("GOOGLE_API_KEY");
  });
});
