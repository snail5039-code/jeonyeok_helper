import { describe, expect, it } from "vitest";

import { demoRoadmap, progress } from "./roadmap";

describe("roadmap progress", () => {
  it("counts checked items across stages", () => {
    const roadmap = demoRoadmap({ service_type: "conscript", region: "서울" });
    const ids = roadmap.stages.flatMap((s) => s.items.map((i) => i.id));
    expect(progress(roadmap, new Set())).toEqual({ done: 0, total: ids.length });
    expect(progress(roadmap, new Set([ids[0], "다른 로드맵의 항목"]))).toEqual({ done: 1, total: ids.length });
  });
});
