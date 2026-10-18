// 운영 대시보드 (관리자용): 서버 api/runlog.py summary와 같은 모양

export interface AdminSummary {
  days: number;
  chats: { total: number; by_kind: Record<string, number> };
  daily: { day: string; count: number }[];
  latency: {
    first_p50_ms: number | null;
    first_p90_ms: number | null;
    total_p50_ms: number | null;
    total_p90_ms: number | null;
    cases: number;
  };
  slow_steps: { node: string; count: number; p50_ms: number | null; p90_ms: number | null }[];
  failures: {
    count: number;
    by_where: Record<string, number>;
    recent: { at: string; question: string; where: string; error: string }[];
  };
  errors: { at: string; question: string; error: string }[];
  feedback: {
    up: number;
    down: number;
    top_down_questions: { question: string; count: number }[];
    recent_down: { at: string; question: string; answer: string; comment: string }[];
  };
}

/** 그래프 단계 이름 → 사람이 읽는 이름 */
export const NODE_NAMES: Record<string, string> = {
  start: "시작",
  guard: "입력 확인",
  profile: "내 정보 읽기",
  coach: "길잡이 판단",
  supervisor: "할 일 나누기",
  regulation: "법령 찾기",
  benefit: "혜택 찾기",
  institution: "기관 찾기",
  ask_user: "되묻기",
  respond: "답변 쓰기",
  verify: "근거 확인",
  guide: "다음 할 일 고르기",
};

export const KIND_NAMES: Record<string, string> = {
  research: "자료 찾아 답함",
  talk: "바로 대화",
  cached: "저장한 답",
  question: "되물음",
  error: "오류",
};

export const TOKEN_KEY = "jeonyeok.adminToken";

export async function fetchSummary(token: string, days: number): Promise<AdminSummary> {
  const res = await fetch(`/api/admin/summary?days=${days}`, { headers: { "X-Admin-Token": token } });
  if (res.status === 401) throw new Error("관리자 열쇠가 맞지 않아요.");
  if (res.status === 404) throw new Error("서버에 관리자 열쇠(ADMIN_TOKEN)가 설정되지 않아 대시보드가 꺼져 있어요.");
  if (!res.ok) throw new Error("불러오지 못했어요. 잠시 후 다시 시도해 주세요.");
  return res.json();
}

/** 1234 → "1.2초" */
export function seconds(ms: number | null | undefined): string {
  return ms == null ? "-" : `${(ms / 1000).toFixed(1)}초`;
}
