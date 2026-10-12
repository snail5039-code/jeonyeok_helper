// 백엔드(FastAPI /chat SSE)와 주고받는 데이터 모양

export type SourceType = "regulation" | "benefit" | "institution";

export interface Source {
  type: SourceType;
  title: string;
  url: string;
}

export type ServiceType = "conscript" | "short_term_officer" | "long_term" | "merit";

export interface Profile {
  service_type?: ServiceType;
  service_years?: number;
  discharge_date?: string;
  age?: number;
  region?: string;
  merit_status?: string;
}

export type ChatEvent =
  | { event: "thread"; data: { thread_id: string } }
  | { event: "step"; data: { node?: string; label: string } }
  // 답변 초안 조각. 이어 붙여 바로 보여 주고, 검증을 마친 answer가 오면 그것으로 바꾼다.
  | { event: "delta"; data: { text: string } }
  | {
      event: "answer";
      data: { text: string; sources: Source[]; profile: Profile; follow_ups?: string[] };
    }
  | { event: "question"; data: { text: string; profile?: Profile } }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: Record<string, never> };

export interface Turn {
  id: string;
  question: string;
  status: "loading" | "streaming" | "answer" | "question" | "error";
  steps: string[];
  text: string;
  sources: Source[];
  profile: Profile;
  /** 이어서 물어볼 만한 질문 (최종 답변과 함께 온다) */
  followUps: string[];
  /** 사용자가 답변 도중 멈춤 */
  stopped?: boolean;
}

export const SERVICE_TYPE_LABELS: Record<ServiceType, string> = {
  conscript: "의무복무 병사",
  short_term_officer: "단기 간부",
  long_term: "중·장기 복무",
  merit: "보훈대상자",
};
