// 전역 로드맵: 프로필 한 번으로 시기별 할 일 목록을 받는다 (백엔드 POST /roadmap).

import { postJson } from "./api";
import { readStorage, writeStorage } from "./storage";
import type { ServiceType, Source } from "./types";

export interface RoadmapInput {
  service_type: ServiceType;
  service_years?: number;
  age?: number;
  region?: string;
}

export interface RoadmapItem {
  id: string;
  title: string;
  action: string;
  detail: string;
  sources: Source[];
}

export interface RoadmapStage {
  key: string;
  title: string;
  items: RoadmapItem[];
}

export interface Roadmap {
  intro: string;
  stages: RoadmapStage[];
}

export const REGIONS = [
  "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기",
  "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]; // prettier-ignore

export async function fetchRoadmap(input: RoadmapInput, signal?: AbortSignal): Promise<Roadmap> {
  const res = await postJson("roadmap", input, "로드맵을 만들지 못했어요. 잠시 후 다시 시도해 주세요.", signal);
  return res.json();
}

// ---------- 완료 체크 (이 브라우저에만 저장) ----------

const DONE_KEY = "jeonyeok.roadmap.done";

export function loadDone(): Set<string> {
  try {
    return new Set(JSON.parse(readStorage(DONE_KEY) ?? "[]"));
  } catch {
    return new Set();
  }
}

export function saveDone(done: Set<string>): void {
  writeStorage(DONE_KEY, JSON.stringify([...done]));
}

export function progress(roadmap: Roadmap, done: Set<string>): { done: number; total: number } {
  const ids = roadmap.stages.flatMap((s) => s.items.map((i) => i.id));
  return { done: ids.filter((id) => done.has(id)).length, total: ids.length };
}

// ---------- 데모 모드 ----------

export function demoRoadmap(input: RoadmapInput): Roadmap {
  const region = input.region ?? "사는 지역";
  return {
    intro: `데모 모드의 예시 로드맵이에요. 실제 서버가 연결되면 ${region}의 혜택과 근거 법령으로 만들어져요.`,
    stages: [
      {
        key: "right_after",
        title: "전역 직후",
        items: [
          {
            id: "right_after:예비군 편성 확인",
            title: "예비군 편성 확인",
            action: "병무청 누리집에서 편성된 부대와 훈련 일정을 확인하세요",
            detail: "전역 다음 날부터 예비군으로 편성돼요.",
            sources: [{ type: "institution", title: "병무청", url: "https://www.mma.go.kr" }],
          },
        ],
      },
      {
        key: "job",
        title: "취업·창업",
        items: [
          {
            id: "job:국민취업지원제도",
            title: "국민취업지원제도",
            action: "고용24에서 온라인으로 신청하세요",
            detail: "취업 상담, 직업훈련, 구직 활동을 지원해요.",
            sources: [{ type: "institution", title: "고용24", url: "https://www.work24.go.kr" }],
          },
        ],
      },
      {
        key: "later",
        title: "나중에 챙길 것",
        items: [
          {
            id: "later:군복무 크레딧",
            title: "군복무 크레딧",
            action: "따로 신청하지 않아도 노령연금 받을 때 반영돼요",
            detail: "군 복무기간 일부를 국민연금 가입기간으로 더해 줘요.",
            sources: [
              {
                type: "regulation",
                title: "국민연금법 제18조(군 복무기간에 대한 노령연금 가입기간 추가 산입)",
                url: "https://www.law.go.kr/법령/국민연금법/제18조",
              },
            ],
          },
        ],
      },
    ],
  };
}
