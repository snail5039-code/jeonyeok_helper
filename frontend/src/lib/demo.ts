// 데모 모드: 서버 에이전트가 준비되지 않았을 때(Gemini 키 없음) 화면을 확인하는 예시 응답.

import type { ChatEvent, Profile, Source } from "./types";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const DEMO_PROFILE: Profile = { service_type: "conscript", discharge_date: "2025-12", region: "서울" };

const DEMO_SOURCES: Source[] = [
  {
    type: "regulation",
    title: "국민연금법 제18조(군 복무기간에 대한 노령연금 가입기간 추가 산입)",
    url: "https://www.law.go.kr/법령/국민연금법/제18조",
  },
  { type: "institution", title: "국민연금공단", url: "https://www.nps.or.kr" },
  { type: "institution", title: "고용24", url: "https://www.work24.go.kr" },
  { type: "institution", title: "온통청년", url: "https://www.youthcenter.go.kr" },
  { type: "institution", title: "병무청", url: "https://www.mma.go.kr" },
];

const DEMO_TEXT = [
  "의무복무를 마친 서울 거주자라면 지금 챙길 수 있는 혜택이 4가지 있어요. 연금처럼 나중에 반영되는 것도 있고 [1], 취업 지원처럼 지금 신청해야 하는 것도 있어요 [3].",
  "### 군복무 크레딧 | 국민연금공단",
  "- 대상: 병역 이행자",
  "- 내용: 군 복무기간 일부를 국민연금 가입기간으로 추가 인정 [1]",
  "- 신청: 노령연금 청구 시 반영, 자세한 내용은 국민연금공단 [2]",
  "- 근거: 국민연금법 제18조",
  "### 국민취업지원제도 | 고용노동부",
  "- 대상: 구직 중인 청년",
  "- 내용: 취업 상담, 직업훈련, 구직 활동 지원",
  "- 신청: 고용24에서 온라인 신청 [3]",
  "### 서울시 청년 정책 | 서울특별시",
  "- 대상: 서울 거주 청년",
  "- 내용: 주거, 자산형성, 마음건강 정책 모음",
  "- 신청: 온통청년에서 지역을 서울로 골라 확인 [4]",
  "### 예비군 편성 확인 | 병무청",
  "- 대상: 전역자",
  "- 내용: 전역 후 예비군 편성과 훈련 일정 확인 [5]",
  "※ 데모 화면이에요. 실제 답변은 법령과 공공서비스 조회 결과로 만들어져요. 정확한 자격과 기한은 소관 기관에 꼭 확인하세요.",
].join("\n");

const SERVICE_WORDS = /병장|병사|하사|중사|상사|소위|중위|대위|소령|간부|부사관|장교|복무|유공|보훈/;

export async function* demoChat(message: string, knowsServiceType: boolean): AsyncGenerator<ChatEvent> {
  yield { event: "step", data: { label: "복무 정보를 정리하고 있어요" } };
  await sleep(500);
  if (!knowsServiceType && !SERVICE_WORDS.test(message)) {
    yield {
      event: "question",
      data: { text: "혜택이 복무 형태에 따라 많이 달라요. 어떻게 전역하셨나요? 사는 지역도 알려주시면 더 정확해요." },
    };
    return;
  }
  for (const label of [
    "관련 법령을 찾고 있어요",
    "받을 수 있는 혜택을 조회하고 있어요",
    "신청 기관을 찾고 있어요",
    "답변을 정리하고 있어요",
    "근거를 확인하고 있어요",
  ]) {
    yield { event: "step", data: { label } };
    await sleep(550);
  }
  yield { event: "answer", data: { text: DEMO_TEXT, sources: DEMO_SOURCES, profile: DEMO_PROFILE } };
}
