import type { ReactNode } from "react";

import { StatusBadge } from "@/components/academic";

export default function V2Layout({ children }: { children: ReactNode }) {
  return (
    <div className="relative">
      <div className="pointer-events-none absolute right-4 top-4 z-20 hidden md:block">
        <StatusBadge tone="teal">V2 Multi-Agent</StatusBadge>
      </div>
      {children}
    </div>
  );
}
