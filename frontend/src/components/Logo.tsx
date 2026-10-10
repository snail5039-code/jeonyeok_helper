/** 군번줄(인식표) 모양 로고 */
export function LogoMark() {
  return (
    <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-accent">
      <svg viewBox="0 0 24 24" className="size-[18px] fill-none stroke-accent-ink" strokeWidth={1.8} strokeLinecap="round">
        <rect x="6" y="5" width="12" height="16" rx="5" />
        <circle cx="12" cy="8.6" r="1.1" />
        <path d="M9.5 13h5M9.5 16h3M12 5V2.5" />
      </svg>
    </span>
  );
}
