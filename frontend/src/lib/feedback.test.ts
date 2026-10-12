import { afterEach, describe, expect, it, vi } from "vitest";

import { sendFeedback } from "./feedback";

afterEach(() => vi.unstubAllGlobals());

describe("sendFeedback", () => {
  it("posts the rating to /api/feedback", async () => {
    const fetchMock = vi.fn(async () => Response.json({ id: 1 }, { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    await sendFeedback({ rating: "down", question: "q", answer: "a", comment: "지역 혜택 없음" });

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/feedback");
    expect(JSON.parse(init.body as string)).toMatchObject({ rating: "down", comment: "지역 혜택 없음" });
  });

  it("throws a readable message when saving fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 502 })));
    await expect(sendFeedback({ rating: "up", question: "q", answer: "a" })).rejects.toThrow("의견을 보내지 못했어요");
  });
});
