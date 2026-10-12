import { postJson } from "./api";

export type Rating = "up" | "down";

export interface FeedbackRequest {
  rating: Rating;
  question: string;
  answer: string;
  comment?: string;
  thread_id?: string | null;
  user_id?: string;
}

/** 답변 피드백을 저장한다. 실패하면 사용자에게 보여 줄 문장으로 예외를 던진다. */
export async function sendFeedback(req: FeedbackRequest): Promise<void> {
  await postJson("feedback", req, "의견을 보내지 못했어요. 잠시 후 다시 시도해 주세요.");
}
