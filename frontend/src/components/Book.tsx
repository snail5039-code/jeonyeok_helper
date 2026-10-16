import type { ReactNode } from "react";

/** 스프링 달린 줄 노트. 화면마다 수첩 한 권(또는 두 권)을 펼쳐 놓는다. */
export function Book({
  children,
  rings = 8,
  className = "",
  label,
  as: Tag = "section",
}: {
  children: ReactNode;
  rings?: number;
  className?: string;
  label?: string;
  as?: "section" | "aside" | "main" | "div";
}) {
  return (
    <Tag aria-label={label} className={`notebook px-4 pt-5 pb-5 sm:px-7 sm:pt-6 ${className}`}>
      <span className="notebook-rings" aria-hidden>
        {Array.from({ length: rings }, (_, i) => (
          <i key={i} />
        ))}
      </span>
      {children}
    </Tag>
  );
}

/** 수첩 제목: 굵은 군대 글씨를 테두리 상자에 */
export function BookTitle({ children, accent }: { children: ReactNode; accent?: string }) {
  return (
    <h1 className="inline-block text-[22px] leading-tight font-black tracking-[-0.06em] text-fg sm:text-[27px]">
      {children}
      {accent && <span className="text-olive"> {accent}</span>}
    </h1>
  );
}

/** 빨간 도장 (예: 임무 수행 중) */
export function Stamp({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={`font-stencil inline-block rounded-md border-[3.5px] border-double border-warn bg-bg/70 px-2.5 py-0.5 text-[16px] text-warn ${className}`}
    >
      {children}
    </span>
  );
}
