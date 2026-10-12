// B급 감성 그림: 마스코트 '전역이', 말풍선, 스티커 배지.
// 굵은 검은 테두리 + 단색 채우기 + 살짝 삐뚤게. 다크 모드에서도 '노란 종이' 위에 그려서 잘 보이게 한다.

import type { Badge } from "@/lib/journey";

const INK = "#1b1b1b";
const SKIN = "#ffd7a1";
const OLIVE = "#7d8c3c";
const OLIVE_DARK = "#5e6b2a";

const STRIPES: Record<string, number> = { 이병: 1, 일병: 2, 상병: 3, 병장: 4 };

/** 계급에 따라 표정과 차림이 바뀌는 마스코트. */
export function Mascot({ rank, size = 120, className = "" }: { rank: string; size?: number; className?: string }) {
  const civilian = rank === "민간인";
  const stripes = STRIPES[rank] ?? 0;
  return (
    <svg
      viewBox="0 0 120 150"
      width={size}
      height={(size * 150) / 120}
      className={className}
      role="img"
      aria-label={`${rank} 전역이`}
    >
      {/* 그림자 */}
      <ellipse cx="60" cy="143" rx="34" ry="5" fill={INK} opacity="0.15" />
      {/* 몸 (군복 / 민간인은 주황 후드) */}
      <path
        d="M27 141 C25 112 33 92 60 90 C88 92 96 113 93 141 Z"
        fill={civilian ? "#ff8a3d" : OLIVE}
        stroke={INK}
        strokeWidth="3.5"
        strokeLinejoin="round"
      />
      {!civilian && (
        <>
          {/* 군복 무늬 몇 점 */}
          <path d="M38 118 q6 -5 11 0 q-4 6 -11 0Z M70 108 q7 -4 11 2 q-6 4 -11 -2Z M74 128 q5 -3 9 1 q-4 5 -9 -1Z" fill={OLIVE_DARK} />
          {/* 가슴 계급장 */}
          <rect x="66" y="98" width="15" height="13" rx="2" fill="#2b2b2b" stroke={INK} strokeWidth="2" />
          {Array.from({ length: stripes }, (_, i) => (
            <rect key={i} x="68.5" y={100 + i * 2.6} width="10" height="1.6" fill="#f2d54a" />
          ))}
        </>
      )}
      {/* 배낭 끈 */}
      <path d="M44 93 L41 140 M76 93 L79 140" stroke={INK} strokeWidth="3" strokeLinecap="round" />
      {/* 손 흔들기 (민간인) / 경례 (군인) */}
      {civilian ? (
        <path d="M92 112 q14 -14 12 -32" fill="none" stroke={INK} strokeWidth="9" strokeLinecap="round" />
      ) : (
        <path d="M90 108 q12 -22 -4 -38" fill="none" stroke={INK} strokeWidth="9" strokeLinecap="round" />
      )}
      <path
        d={civilian ? "M92 112 q14 -14 12 -32" : "M90 108 q12 -22 -4 -38"}
        fill="none"
        stroke={civilian ? "#ff8a3d" : OLIVE}
        strokeWidth="4.5"
        strokeLinecap="round"
      />
      <circle cx={civilian ? 104 : 86} cy={civilian ? 79 : 69} r="6.5" fill={SKIN} stroke={INK} strokeWidth="3" />

      {/* 머리 */}
      <path
        d="M31 54 C30 33 43 22 60 22 C79 22 90 34 89 55 C88 75 76 86 60 86 C43 86 32 75 31 54 Z"
        fill={SKIN}
        stroke={INK}
        strokeWidth="3.5"
      />
      {/* 모자 */}
      {civilian ? (
        <>
          <path d="M33 42 C35 24 50 17 63 18 C78 19 88 28 87 41 Z" fill="#e24b4b" stroke={INK} strokeWidth="3.5" strokeLinejoin="round" />
          <path d="M33 41 L16 38 C14 44 22 47 34 46" fill="#e24b4b" stroke={INK} strokeWidth="3" strokeLinejoin="round" />
        </>
      ) : (
        <>
          <path d="M30 40 C31 22 46 14 61 15 C77 16 90 24 90 40 Z" fill={OLIVE} stroke={INK} strokeWidth="3.5" strokeLinejoin="round" />
          <path d="M27 40 L93 40 L95 46 L25 46 Z" fill={OLIVE_DARK} stroke={INK} strokeWidth="3" strokeLinejoin="round" />
        </>
      )}

      {/* 얼굴: 계급마다 다르게 */}
      <Face rank={rank} />
      {/* 볼터치 */}
      <ellipse cx="41" cy="66" rx="5" ry="3" fill="#ff8f8f" opacity="0.6" />
      <ellipse cx="79" cy="66" rx="5" ry="3" fill="#ff8f8f" opacity="0.6" />
    </svg>
  );
}

function Face({ rank }: { rank: string }) {
  const s = { stroke: INK, strokeWidth: 3, strokeLinecap: "round" as const, fill: "none" };
  switch (rank) {
    case "이병": // 긴장: 동그란 눈, 땀, 삐뚤한 입
      return (
        <g>
          <circle cx="48" cy="57" r="5.5" fill="#fff" stroke={INK} strokeWidth="2.5" />
          <circle cx="72" cy="57" r="5.5" fill="#fff" stroke={INK} strokeWidth="2.5" />
          <circle cx="49" cy="58" r="2.2" fill={INK} />
          <circle cx="71" cy="58" r="2.2" fill={INK} />
          <path d="M52 74 q4 -3 8 0 q4 3 8 0" {...s} />
          <path d="M86 44 q5 8 0 11 q-5 -3 0 -11Z" fill="#6ec6ff" stroke={INK} strokeWidth="2" />
        </g>
      );
    case "일병": // 무표정
      return (
        <g>
          <circle cx="48" cy="58" r="2.8" fill={INK} />
          <circle cx="72" cy="58" r="2.8" fill={INK} />
          <path d="M53 73 L67 73" {...s} />
        </g>
      );
    case "상병": // 거들먹: 반쯤 감은 눈, 한쪽 입꼬리
      return (
        <g>
          <path d="M42 58 L54 58 M66 58 L78 58" {...s} />
          <path d="M44 55 q4 -3 9 -1 M67 54 q5 -2 9 1" {...s} strokeWidth={2.5} />
          <path d="M52 72 q8 5 16 -3" {...s} />
        </g>
      );
    case "병장": // 선글라스 + 씩
      return (
        <g>
          <path d="M37 52 L83 52" stroke={INK} strokeWidth="3" />
          <path d="M38 52 q1 13 12 12 q9 -1 9 -12Z M61 52 q0 12 10 12 q11 0 11 -12Z" fill={INK} />
          <path d="M42 55 l5 0" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
          <path d="M51 72 q9 7 18 0" {...s} />
        </g>
      );
    default: // 민간인: ^^ 눈 + 활짝
      return (
        <g>
          <path d="M42 59 q6 -8 12 0 M66 59 q6 -8 12 0" {...s} />
          <path d="M49 69 q11 12 22 0 Z" fill="#c0392b" stroke={INK} strokeWidth="3" strokeLinejoin="round" />
        </g>
      );
  }
}

/** 삐뚤빼뚤한 말풍선 (꼬리는 왼쪽 아래) */
export function Bubble({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`relative ${className}`}>
      <div className="font-fun relative z-10 -rotate-1 rounded-[18px_22px_20px_16px] border-[2.5px] border-[#1b1b1b] bg-white px-3.5 py-2 text-[15px] leading-snug text-[#1b1b1b] shadow-[3px_3px_0_#1b1b1b]">
        {children}
      </div>
      <svg viewBox="0 0 24 18" className="absolute -bottom-[13px] left-5 z-20 h-[18px] w-6" aria-hidden>
        <path d="M2 0 L8 16 L16 0" fill="#fff" stroke="#1b1b1b" strokeWidth="2.5" strokeLinejoin="round" />
        <path d="M3 -1 L15 -1" stroke="#fff" strokeWidth="4" />
      </svg>
    </div>
  );
}

/** 스티커 배지. 아직 못 받았으면 회색 물음표. */
export function Sticker({ badge, fresh = false }: { badge: Badge; fresh?: boolean }) {
  // 배지마다 기울기를 조금씩 다르게 (붙인 스티커 느낌)
  const tilt = ((badge.id.length * 7) % 11) - 5;
  return (
    <div
      className={`grid w-[88px] justify-items-center gap-1 text-center ${fresh ? "animate-pop" : ""}`}
      title={badge.earned ? `${badge.name} — ${badge.line}` : `잠김: ${badge.line}`}
    >
      <div
        style={{ rotate: `${tilt}deg` }}
        className={`grid size-[58px] place-items-center rounded-full border-[2.5px] border-[#1b1b1b] text-[28px] shadow-[3px_3px_0_#1b1b1b] ${
          badge.earned ? "bg-[#ffe066]" : "bg-[#d9d9d9] grayscale"
        }`}
      >
        <span className={badge.earned ? "" : "opacity-40"}>{badge.earned ? badge.emoji : "?"}</span>
      </div>
      <span className={`font-fun text-[13px] leading-tight ${badge.earned ? "text-fg" : "text-fg-3"}`}>
        {badge.earned ? badge.name : "???"}
      </span>
    </div>
  );
}
