import { Suspense } from "react";
import { Loader2 } from "lucide-react";

import { Panel } from "@/components/academic";
import SubscribePageClient from "./SubscribePageClient";

export default function SubscribePage() {
  return (
    <Suspense
      fallback={
        <Panel className="flex items-center gap-2 text-slate-600">
          <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
        </Panel>
      }
    >
      <SubscribePageClient />
    </Suspense>
  );
}
