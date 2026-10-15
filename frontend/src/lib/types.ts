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
  // 간부 구분 (대화에서 '중사', '단기복무 장교' 같은 말로 읽은 값)
  cadre?: string;
  // '내 정보' 화면에서 채우는 자세한 정보
  branch?: string;
  rank?: string;
  specialty?: string;
  education?: string;
  goals?: string[];
  desired_job?: string;
  certificates?: string;
  housing?: string;
  injury?: string;
  memo?: string;
}

export type StageKey = "before" | "right_after" | "job" | "study" | "life" | "later";

/** 전역 로드맵의 할 일 하나 (백엔드 journey_item) */
export interface JourneyItem {
  id: string;
  stage: StageKey;
  title: string;
  action: string;
  detail: string;
  sources: Source[];
  /** plan: 내 정보로 한 번에 만듦, chat: 대화에서 담김 */
  origin: "plan" | "chat";
  question: string;
  /** 핵심 할 일: 단계마다 이것만 끝내면 그 단계 완료 */
  core: boolean;
  /** 근거 자료에 적힌 신청 기한 문구 (예: '전역 후 3년 이내') */
  deadline: string;
  /** 전역일 기준 기한(개월). 전역일을 알면 D-day로 보여 준다 */
  due_months: number | null;
  done: boolean;
  created_at: string | null;
  done_at: string | null;
}

/** 길잡이가 제안한 할 일 (사용자가 고르면 로드맵에 담긴다) */
export type Suggestion = Pick<
  JourneyItem,
  "stage" | "title" | "action" | "detail" | "sources" | "core" | "deadline" | "due_months"
>;

/** 길잡이 빠른 답 버튼. 누르면 message를 사용자 말로 보내고, action이 있으면 함께 보낸다 */
export interface QuickReply {
  label: string;
  message?: string;
  action?: ChatAction;
  /** 메시지 대신 화면을 연다 (화면에서만 쓰는 버튼) */
  open?: "journey" | "profile";
}

export interface ChatAction {
  type: "done" | "later";
  item_id: string;
}

/** 길잡이 출력. talk: 검색 없이 바로 한 말, research: 검색 답변 위의 한마디 */
export interface Guide {
  mode: "talk" | "research";
  say: string;
  quick_replies: QuickReply[];
  suggest: Suggestion[];
  /** 아직 모르는 정보 (복무 형태 → 지역 → 전역일 순으로 묻는다) */
  ask: "service_type" | "region" | "discharge_date" | null;
  /** 지금 권한 다음 할 일 */
  step: JourneyItem | null;
  profile?: Profile;
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
  // 길잡이: talk면 answer 없이 이것만, research면 answer 다음에 온다
  | { event: "guide"; data: Guide }
  // 서버가 로드맵을 바꿨을 때 (첫 로드맵 생성, '했어요' 버튼)
  | { event: "journey"; data: { added: JourneyItem[]; done?: JourneyItem } }
  | { event: "question"; data: { text: string; profile?: Profile } }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: Record<string, never> };

export interface Turn {
  id: string;
  question: string;
  /** talk: 길잡이가 검색 없이 바로 답함 */
  status: "loading" | "streaming" | "answer" | "talk" | "question" | "error";
  steps: string[];
  text: string;
  sources: Source[];
  profile: Profile;
  /** 이어서 물어볼 만한 질문 (최종 답변과 함께 온다) */
  followUps: string[];
  /** 사용자가 답변 도중 멈춤 */
  stopped?: boolean;
  /** 길잡이의 한마디·버튼·할 일 제안 */
  guide?: Guide;
  /** 같은 대화에서 이어진 길잡이 말 (예: 첫 로드맵 완성 안내) */
  moreGuides?: Guide[];
}

export const SERVICE_TYPE_LABELS: Record<ServiceType, string> = {
  conscript: "의무복무 병사",
  short_term_officer: "단기 간부",
  long_term: "중·장기 복무",
  merit: "보훈대상자",
};

/** 간부 구분: 계급이나 말로 장교·부사관·준사관을 가른다 (백엔드 agents/state.py의 cadre_of와 같은 규칙) */
export function cadreOf(text?: string): string | undefined {
  const t = text ?? "";
  if (/준위|준사관/.test(t)) return "준사관";
  if (/소위|중위|대위|소령|중령|대령|장교|학군|ROTC|학사장교|사관학교/.test(t)) return "장교";
  if (/하사|중사|상사|원사|부사관/.test(t)) return "부사관";
  return undefined;
}
