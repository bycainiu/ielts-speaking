import { Suspense } from "react";
import { Loader2 } from "lucide-react";

import LoginPageClient from "./LoginPageClient";

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-background text-slate-600">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      }
    >
      <LoginPageClient />
    </Suspense>
  );
}
