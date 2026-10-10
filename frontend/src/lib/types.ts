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
  | { event: "answer"; data: { text: string; sources: Source[]; profile: Profile } }
  | { event: "question"; data: { text: string; profile?: Profile } }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: Record<string, never> };

export interface Turn {
  id: string;
  question: string;
  status: "loading" | "answer" | "question" | "error";
  steps: string[];
  text: string;
  sources: Source[];
  profile: Profile;
}

export const SERVICE_TYPE_LABELS: Record<ServiceType, string> = {
  conscript: "의무복무 병사",
  short_term_officer: "단기 간부",
  long_term: "중·장기 복무",
  merit: "보훈대상자",
};
