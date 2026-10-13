"use client";

import { Compass, ListChecks, MessageCircle, Map, Undo2, UserRound, type LucideIcon } from "lucide-react";

import { Book, BookTitle } from "./Book";

interface Props {
  onAsk: (question: string) => void;
  onJourney: () => void;
  onProfile: () => void;
}

const STEPS: { icon: LucideIcon; title: string; body: string }[] = [
  {
    icon: MessageCircle,
    title: "전역이가 먼저 물어요",
    body: "복무 형태, 사는 지역, 전역 시기를 버튼으로 고르면 돼요. 대화로 말해도 알아듣고, 나중에 내 정보에서 고칠 수 있어요.",
  },
  {
    icon: Map,
    title: "나만의 작전도가 생겨요",
    body: "조건에 맞는 임무(받을 수 있는 혜택, 챙겨야 할 신청)가 단계별로 모여요. 별표는 놓치면 아까운 핵심 임무예요.",
  },
  {
    icon: ListChecks,
    title: "한 걸음씩 따라가요",
    body: "지금 할 일을 하나씩 안내해요. 했어요, 나중에 할게요를 누르면 다음 임무를 권하고, 끝낸 만큼 계급이 올라요.",
  },
  {
    icon: Undo2,
    title: "마음이 바뀌어도 괜찮아요",
    body: "완료, 빼기, 담기는 모두 기록돼요. 아래에 뜨는 되돌리기나 작전도의 변경 기록으로 원래대로 돌릴 수 있어요.",
  },
];

const SAMPLES: { title: string; hint: string; asks: string[] }[] = [
  {
    title: "혜택이 뭐가 있는지",
    hint: "복무 형태를 몰라도 병사 기준으로 먼저 알려 줘요.",
    asks: ["혜택 알려줘", "전역하면 뭐 받을 수 있어요?", "서울 사는 25살인데 월세 지원 받을 수 있어요?"],
  },
  {
    title: "신청 방법과 서류",
    hint: "근거 법령과 어디서 신청하는지까지 같이 나와요.",
    asks: ["군복무 크레딧은 따로 신청해야 하나요?", "국가유공자 등록하려면 서류 뭐 필요해요?", "제대군인 히어로즈 카드는 누가 신청할 수 있어요?"],
  },
  {
    title: "내 사정에 맞춰서",
    hint: "상황을 말하면 내 정보에 반영하고 그에 맞춰 답해요.",
    asks: ["저는 상병으로 전역했고 경기도 수원 살아요", "군대에서 다쳤는데 전역 후 치료비 지원돼요?", "취업 지원 뭐 있어요?"],
  },
  {
    title: "그냥 대화",
    hint: "검색 없이 짧게 답하고 다음 임무를 권해요.",
    asks: ["안녕하세요", "지금 어디까지 했어요?", "다음 뭐 해요?"],
  },
];

const RANKS = [
  ["이병", "처음 시작"],
  ["일병", "임무 1개 완료"],
  ["상병", "임무 4개 완료"],
  ["병장", "임무 8개 완료"],
  ["민간인", "핵심 임무를 모두 끝내고 병장 수준까지"],
];

/** 사용 설명: 어떻게 쓰는지, 눌러 보면 바로 물어보는 예시 질문, 계급 규칙, 알아 둘 점 */
export function HelpView({ onAsk, onJourney, onProfile }: Props) {
  return (
    <main className="flex-1 overflow-y-auto px-2.5 pt-4 pb-6 sm:px-5 sm:pt-6 lg:pb-12">
      <Book as="div" rings={14} className="mx-auto grid max-w-[880px] grid-cols-[minmax(0,1fr)] gap-7">
        <header className="grid gap-2">
          <BookTitle accent="사용법">전역도우미</BookTitle>
          <p className="max-w-[60ch] text-[15px] leading-relaxed text-fg-2">
            군 복무를 마친 사람이 받을 수 있는 혜택과 그 근거, 신청할 곳을 찾아 한 걸음씩 안내해요. 답마다 출처가 붙고, 모르는 건 모른다고 해요.
          </p>
        </header>

        <section aria-label="이렇게 써요" className="grid gap-3">
          <h2 className="font-fun text-[19px]">이렇게 써요</h2>
          <ol className="grid gap-2.5 sm:grid-cols-2">
            {STEPS.map(({ icon: Icon, title, body }, i) => (
              <li key={title} className="flex gap-3 rounded-xl border-2 border-edge bg-soft p-3.5">
                <span className="grid size-9 shrink-0 place-items-center rounded-lg border-2 border-ink bg-bg">
                  <Icon className="size-[18px]" strokeWidth={2.2} />
                </span>
                <div className="min-w-0">
                  <div className="text-[14.5px] font-extrabold">
                    {i + 1}. {title}
                  </div>
                  <p className="mt-0.5 text-[13.5px] leading-relaxed text-fg-2">{body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section aria-label="이렇게 물어보세요" className="grid gap-3">
          <div>
            <h2 className="font-fun text-[19px]">이렇게 물어보세요</h2>
            <p className="mt-0.5 text-[13.5px] text-fg-3">문장을 누르면 작전실에서 바로 물어봐요.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {SAMPLES.map(({ title, hint, asks }) => (
              <div key={title} className="rounded-xl border-2 border-edge bg-soft p-3.5">
                <div className="text-[14.5px] font-extrabold">{title}</div>
                <p className="mt-0.5 mb-2 text-[12.5px] text-fg-3">{hint}</p>
                <ul className="grid gap-1.5">
                  {asks.map((q) => (
                    <li key={q}>
                      <button
                        type="button"
                        onClick={() => onAsk(q)}
                        className="w-full rounded-lg border-2 border-edge bg-bg px-3 py-2 text-left text-[13.5px] font-semibold hover:border-ink"
                      >
                        {q}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        <section aria-label="계급 규칙" className="grid gap-3">
          <h2 className="font-fun text-[19px]">계급은 이렇게 올라요</h2>
          <ul className="flex flex-wrap gap-2">
            {RANKS.map(([rank, rule]) => (
              <li key={rank} className="rounded-lg border-2 border-edge bg-soft px-3 py-2 text-[13px]">
                <span className="font-extrabold">{rank}</span> <span className="text-fg-3">{rule}</span>
              </li>
            ))}
          </ul>
          <p className="text-[12.5px] text-fg-3">임무 하나를 끝냈다고 바로 민간인이 되지는 않아요.</p>
        </section>

        <section aria-label="알아 둘 점" className="grid gap-2 rounded-xl border-2 border-dashed border-edge p-4">
          <h2 className="flex items-center gap-1.5 font-fun text-[19px]">
            <Compass className="size-[18px]" strokeWidth={2.2} />
            알아 둘 점
          </h2>
          <ul className="grid gap-1.5 text-[13.5px] leading-relaxed text-fg-2">
            <li>첫 작전도를 만들 때는 20~30초 걸려요.</li>
            <li>복무 형태를 모르면 의무복무 병사 기준으로 답하고, 그렇게 말해 줘요. 내 정보에서 고르면 더 정확해요.</li>
            <li>로그인이 없어요. 이 브라우저에 저장되니, 다른 브라우저에서는 처음부터 시작해요.</li>
            <li>법령과 공식 안내를 근거로 하지만 바뀔 수 있어요. 신청 전에는 안내된 기관에서 한 번 더 확인해 주세요.</li>
          </ul>
          <div className="mt-1 flex flex-wrap gap-2">
            <button type="button" onClick={onProfile} className="inline-flex h-9 items-center gap-1.5 rounded-lg border-2 border-ink bg-soft px-3 text-[13.5px] font-bold">
              <UserRound className="size-4" />내 정보 적기
            </button>
            <button type="button" onClick={onJourney} className="inline-flex h-9 items-center gap-1.5 rounded-lg border-2 border-ink bg-soft px-3 text-[13.5px] font-bold">
              <Map className="size-4" />
              작전도 보기
            </button>
          </div>
        </section>
      </Book>
    </main>
  );
}
