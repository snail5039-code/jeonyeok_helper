import Image from "next/image";

/** 기존 SVG 군인 대신 목업에서 확정한 인물 사진을 작은 프로필로 쓴다. */
export function PhotoAvatar({ rank, size = 56, className = "" }: { rank: string; size?: number; className?: string }) {
  const civilian = rank === "민간인";
  return (
    <span
      role="img"
      aria-label={civilian ? "전역 후 길잡이 사진" : "군복 차림의 길잡이 사진"}
      className={`relative block aspect-square w-full overflow-hidden rounded-full border-2 border-[#b8cbb8] bg-[#dce9dd] shadow-[2px_2px_0_#a7bfa0] ${className}`}
      style={{ maxWidth: size }}
    >
      <Image
        src={civilian ? "/images/soldier-female-after.png" : "/images/soldier-female-before.png"}
        alt=""
        fill
        sizes={`${size * 3}px`}
        className="object-cover object-[76%_27%]"
      />
    </span>
  );
}
