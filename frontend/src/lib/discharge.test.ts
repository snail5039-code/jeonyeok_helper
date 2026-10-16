import { describe, expect, it } from "vitest";

import { dischargeMoment } from "./discharge";

describe("dischargeMoment", () => {
  const today = new Date(2026, 9, 16);

  it("전역 당일은 전역 전, 다음 날부터 전역 후로 보여 준다", () => {
    expect(dischargeMoment("2026-10-16", today)).toBe("before");
    expect(dischargeMoment("2026-10-15", today)).toBe("after");
  });

  it("월까지만 알면 그 달 마지막 날을 기준으로 한다", () => {
    expect(dischargeMoment("2026-10", today)).toBe("before");
    expect(dischargeMoment("2026-09", today)).toBe("after");
  });

  it("날짜가 없거나 잘못되면 전역을 단정하지 않는다", () => {
    expect(dischargeMoment(undefined, today)).toBe("before");
    expect(dischargeMoment("2026-02-30", today)).toBe("before");
  });
});
