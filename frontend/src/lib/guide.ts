// 길잡이(전역이)가 먼저 말 거는 규칙. 서버 길잡이(agents/guide.py)와 같은 버튼을 쓴다.

import { daysLeft, ddayLabel, dueDate, levelOf, nextItem } from "./journey";
import type { JourneyItem, Profile, QuickReply } from "./types";

export const SERVICE_REPLIES: QuickReply[] = [
  { label: "의무복무 병사", message: "의무복무 병사로 전역했어요" },
  { label: "단기 간부 (5년 미만)", message: "단기 간부로 5년 미만 복무했어요" },
  { label: "중·장기 복무 (5년 이상)", message: "중·장기 복무 간부로 5년 이상 복무했어요" },
  { label: "보훈대상자", message: "국가유공자·보훈대상자예요" },
];

export const OPEN_JOURNEY: QuickReply = { label: "작전도 보기", open: "journey" };

/** 할 일 하나를 권할 때의 버튼: 했어요 / 어떻게 해요? / 나중에 */
export function stepReplies(item: JourneyItem): QuickReply[] {
  return [
    { label: "했어요", message: `'${item.title}' 했어요`, action: { type: "done", item_id: item.id } },
    { label: "어떻게 해요?", message: `${item.title}, 어떻게 신청해요?` },
    { label: "나중에 할게요", message: "이건 나중에 할게요. 다음 거 알려줘요", action: { type: "later", item_id: item.id } },
  ];
}

function dueNote(item: JourneyItem, profile: Profile): string {
  const due = dueDate(item, profile.discharge_date);
  if (!due || !item.deadline) return "";
  // 할 일 문장에 기한이 이미 있으면 D-day만
  const what = item.action.includes(item.deadline) ? "" : `${item.deadline}, `;
  return ` (${what}${ddayLabel(daysLeft(due))})`;
}

/** 첫 화면에서 길잡이가 먼저 하는 말과 버튼 */
export function greeting(profile: Profile, items: JourneyItem[]): { say: string; replies: QuickReply[] } {
  if (!profile.service_type) {
    return {
      say: "충성! 전역 길잡이 전역이에요. 전역하고 챙길 것들, 하나씩 같이 해 봐요. 먼저, 어떻게 복무했어요?",
      replies: SERVICE_REPLIES,
    };
  }
  if (!items.length) {
    return {
      say: "다시 왔군요! 사는 곳이랑 전역일만 알려 주면 임무를 순서대로 정리한 작전도를 바로 만들어 줄게요.",
      replies: [{ label: "내 작전도 만들어 줘", message: "내 로드맵 만들어 줘" }],
    };
  }
  const level = levelOf(items);
  if (level.finished) {
    return {
      say: "민간인 완성! 핵심 임무는 다 끝냈어요. 더 궁금한 건 언제든 물어봐요.",
      replies: [OPEN_JOURNEY],
    };
  }
  const next = nextItem(items);
  // 담은 임무를 다 끝냈지만 민간인 조건(핵심 임무 3개 이상)은 아직인 경우
  if (!next) {
    return {
      say: `어서 와요, ${level.rank}님! 담아 둔 임무는 다 끝냈어요. 임무를 더 찾아서 이어 가 볼까요?`,
      replies: [{ label: "임무 더 찾아 줘", message: "내 로드맵 만들어 줘" }, OPEN_JOURNEY],
    };
  }
  return {
    say: `어서 와요, ${level.rank}님! 다음 임무는 '${next.title}'이에요. ${next.action}${dueNote(next, profile)}`,
    replies: [...stepReplies(next), OPEN_JOURNEY],
  };
}
