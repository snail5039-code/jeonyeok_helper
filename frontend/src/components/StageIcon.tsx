import { Backpack, Briefcase, GraduationCap, Hourglass, House, Shield, type LucideProps } from "lucide-react";

import type { StageKey } from "@/lib/types";

// 단계 아이콘 (이모지 대신 같은 굵기의 선 아이콘)
const ICONS: Record<StageKey, React.ComponentType<LucideProps>> = {
  before: Backpack,
  right_after: Shield,
  job: Briefcase,
  study: GraduationCap,
  life: House,
  later: Hourglass,
};

export function StageIcon({ stage, className = "size-5" }: { stage: StageKey; className?: string }) {
  const Icon = ICONS[stage];
  return <Icon className={className} strokeWidth={2.2} aria-hidden />;
}
