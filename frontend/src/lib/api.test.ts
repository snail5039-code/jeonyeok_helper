import { afterEach, describe, expect, it, vi } from "vitest";

import { postJson } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("postJson", () => {
  it("posts JSON to the backend proxy", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await postJson("feedback", { rating: "up" }, "실패");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/feedback");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ rating: "up" });
  });

  it("throws the server's detail, or the fallback when there is none", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ detail: "GOOGLE_API_KEY 없음" }, { status: 503 })));
    await expect(postJson("roadmap", {}, "실패")).rejects.toThrow("GOOGLE_API_KEY 없음");

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Bad Gateway", { status: 502 })));
    await expect(postJson("roadmap", {}, "로드맵을 만들지 못했어요")).rejects.toThrow("로드맵을 만들지 못했어요");
  });
});
