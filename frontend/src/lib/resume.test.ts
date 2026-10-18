import { describe, expect, it } from "vitest";

import { resumeUrl, takeResumeParam } from "./resume";

describe("이어 하기 코드", () => {
  it("QR 주소에 코드가 들어간다", () => {
    expect(resumeUrl("JY-7K3Q-9XPA", "https://example.com")).toBe("https://example.com/?resume=JY-7K3Q-9XPA&page=journey");
  });

  it("주소에서 코드를 꺼내고 나머지는 남긴다", () => {
    const { code, cleaned } = takeResumeParam(new URL("https://example.com/?resume=JY-7K3Q-9XPA&page=journey#a"));
    expect(code).toBe("JY-7K3Q-9XPA");
    expect(cleaned).toBe("/?page=journey#a");
  });

  it("코드가 없으면 그대로", () => {
    const { code, cleaned } = takeResumeParam(new URL("https://example.com/"));
    expect(code).toBeNull();
    expect(cleaned).toBe("/");
  });
});
