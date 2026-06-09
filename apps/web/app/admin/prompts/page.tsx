"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, EyeOff, Filter, Loader2, RotateCcw, ShieldCheck, Sparkles } from "lucide-react";

import { AcademicShell, EmptyState, PageHeader, Panel, SectionHeading, StatusBadge } from "@/components/academic";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

type ApiError = {
  response?: {
    data?: {
      message?: string;
    };
  };
};

type PromptVersion = {
  id: string;
  agent_name: string;
  purpose: string;
  version: string;
  content_hash: string;
  metadata: Record<string, unknown>;
  active: boolean;
  created_at: string;
};

type Filters = {
  agentName: string;
  purpose: string;
  active: string;
};

const emptyFilters: Filters = { agentName: "", purpose: "", active: "true" };

export default function PromptAdminPage() {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated, fetchUser } = useAuthStore();
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [activeFilters, setActiveFilters] = useState<Filters>(emptyFilters);
  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const canAdmin = user?.role === "operator" || user?.role === "admin";

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) {
      router.push("/login");
    }
  }, [hasHydrated, isAuthenticated, router]);

  useEffect(() => {
    if (hasHydrated && isAuthenticated && !user) {
      fetchUser();
    }
  }, [fetchUser, hasHydrated, isAuthenticated, user]);

  useEffect(() => {
    if (!hasHydrated || !isAuthenticated || !canAdmin) return;

    let cancelled = false;
    async function loadVersions() {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({ limit: "120" });
        if (activeFilters.agentName) params.set("agent_name", activeFilters.agentName);
        if (activeFilters.purpose) params.set("purpose", activeFilters.purpose);
        if (activeFilters.active) params.set("active", activeFilters.active);
        const response = await api.get<{ versions: PromptVersion[] }>(`/admin/prompts/versions?${params.toString()}`);
        if (!cancelled) {
          setVersions(response.data.versions ?? []);
        }
      } catch (err: unknown) {
        const apiError = err as ApiError;
        if (!cancelled) {
          setError(apiError.response?.data?.message || "Prompt versions could not be loaded.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadVersions();
    return () => {
      cancelled = true;
    };
  }, [activeFilters, canAdmin, hasHydrated, isAuthenticated]);

  const agents = useMemo(() => Array.from(new Set(versions.map((item) => item.agent_name))).sort(), [versions]);
  const purposes = useMemo(() => Array.from(new Set(versions.map((item) => item.purpose))).sort(), [versions]);

  if (!hasHydrated || !isAuthenticated || (isAuthenticated && !user)) return null;

  if (!canAdmin) {
    return (
      <AcademicShell activePath="/admin/prompts" userName={user?.display_name} userRole={user?.role}>
        <Panel className="border-red-200 bg-red-50 text-red-700">
          <SectionHeading icon={ShieldCheck} label="Access denied" labelZh="权限不足" />
          <h1 className="font-serif text-3xl text-[#0B132B]">Prompt Admin</h1>
          <p className="mt-2 text-sm leading-6">This workspace is available to operator and admin accounts.</p>
          <Button type="button" variant="soft" className="mt-5" onClick={() => router.push("/practice")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Practice / 练习
          </Button>
        </Panel>
      </AcademicShell>
    );
  }

  return (
    <AcademicShell activePath="/admin/prompts" userName={user?.display_name} userRole={user?.role}>
      <PageHeader
        eyebrow="AI Operations"
        title="Prompt Admin"
        titleZh="提示词版本"
        description="Version metadata, active prompt catalog, content hashes, and rollback notes."
        actions={
          <Button type="button" variant="soft" onClick={() => router.push("/practice")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Practice / 练习
          </Button>
        }
      />

      {error && <Panel className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Panel>}

      <Panel tone="paper">
        <SectionHeading icon={Filter} label="Filters" labelZh="筛选" />
        <div className="grid gap-3 md:grid-cols-[1fr_1fr_0.7fr_auto_auto]">
          <SelectField label="Agent" value={filters.agentName} onChange={(value) => setFilters((current) => ({ ...current, agentName: value }))}>
            <option value="">All agents</option>
            {agents.map((agent) => (
              <option key={agent} value={agent}>
                {agent}
              </option>
            ))}
          </SelectField>
          <SelectField label="Purpose" value={filters.purpose} onChange={(value) => setFilters((current) => ({ ...current, purpose: value }))}>
            <option value="">All purposes</option>
            {purposes.map((purpose) => (
              <option key={purpose} value={purpose}>
                {purpose}
              </option>
            ))}
          </SelectField>
          <SelectField label="Active" value={filters.active} onChange={(value) => setFilters((current) => ({ ...current, active: value }))}>
            <option value="">All</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </SelectField>
          <Button type="button" variant="gold" onClick={() => setActiveFilters(filters)} className="h-11 self-end">
            Apply
          </Button>
          <Button type="button" variant="soft" onClick={() => { setFilters(emptyFilters); setActiveFilters(emptyFilters); }} className="h-11 self-end">
            Reset
          </Button>
        </div>
      </Panel>

      <Panel>
        <div className="mb-5 flex items-center justify-between gap-3">
          <SectionHeading icon={Sparkles} label="Prompt Versions" labelZh="版本列表" />
          <span className="text-sm text-slate-500">{versions.length} versions</span>
        </div>
        {loading ? (
          <div className="flex min-h-40 items-center justify-center text-sm text-slate-600">
            <Loader2 className="mr-2 h-5 w-5 animate-spin text-[#D4AF37]" />
            Loading prompt versions...
          </div>
        ) : versions.length === 0 ? (
          <EmptyState icon={Sparkles} title="No prompt versions" body="No prompt versions match the current filters. 当前筛选条件下暂无提示词版本。" />
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {versions.map((version) => (
              <article key={version.id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex flex-wrap gap-2">
                  <Badge>{version.agent_name}</Badge>
                  <Badge>{version.purpose}</Badge>
                  <Badge>{version.active ? "active" : "inactive"}</Badge>
                  {version.metadata?.prompt_body_redacted === true && <Badge>redacted</Badge>}
                </div>
                <h2 className="mt-3 break-words text-base font-semibold text-[#0B132B]">{version.version}</h2>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">{String(version.metadata?.summary ?? "No summary metadata.")}</p>
                <div className="mt-4 grid gap-2 text-xs text-slate-500">
                  <div className="flex items-center gap-2">
                    <EyeOff className="h-3.5 w-3.5 text-[#D4AF37]" />
                    Prompt body is not exposed in this UI.
                  </div>
                  <div className="break-all">{version.content_hash}</div>
                  <div className="flex items-center gap-2">
                    <RotateCcw className="h-3.5 w-3.5 text-[#3A7CA5]" />
                    Rollback: {String(version.metadata?.rollback_from ?? "none")}
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </Panel>
    </AcademicShell>
  );
}

function SelectField({ label, value, onChange, children }: { label: string; value: string; onChange: (value: string) => void; children: ReactNode }) {
  return (
    <label className="grid gap-2 text-sm text-slate-700">
      <span className="font-medium">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} className="h-11 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition-colors focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/20">
        {children}
      </select>
    </label>
  );
}

function Badge({ children }: { children: ReactNode }) {
  return <StatusBadge tone="slate">{children}</StatusBadge>;
}
