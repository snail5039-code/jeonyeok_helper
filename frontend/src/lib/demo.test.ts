import { describe, expect, it } from "vitest";

import { demoReply } from "./demo";

describe("demoReply", () => {
  it("does not reuse the prepared answer for unrelated questions", () => {
    for (const q of ["오늘 점심 뭐 먹지?", "ㅁㄴㅇㄹ", "비트코인 지금 사도 돼요?"]) {
      expect(demoReply(q, true)).toBe("notice");
    }
  });

  it("asks for the service type before answering a benefit question", () => {
    expect(demoReply("혜택 뭐 있어요?", false)).toBe("ask");
    expect(demoReply("병장으로 전역했는데 혜택 있어요?", false)).toBe("answer");
    expect(demoReply("군복무 크레딧이 뭐예요?", true)).toBe("answer");
  });
});
