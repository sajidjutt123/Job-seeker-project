"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ErrorState, LoadingBlock } from "@/components/ui/states";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";

interface Overview {
  jobs: {
    total: number; active: number; expired: number; pending_review: number;
    today: number; this_week: number; hidden: number; duplicates: number;
  };
  users: { total: number; new_this_week: number; suspended: number };
  sources: {
    total: number; enabled: number; failing: number; degraded: number; failed_runs_24h: number;
  };
  alerts: { active: number };
  moderation: { open_reports: number; duplicate_links: number };
}

interface Health {
  status: string;
  environment: string;
  components: Record<string, { status: string; detail?: string | null; latency_ms?: number | null }>;
  warnings: string[];
}

export function AdminOverview() {
  const [data, setData] = useState<Overview | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [overview, healthResult] = await Promise.all([
        api.get<Overview>("/admin/overview", { revalidate: false }),
        // Health lives outside the versioned prefix; a failure here is not fatal.
        fetch("/health").then((r) => r.json()).catch(() => null),
      ]);
      setData(overview);
      setHealth(healthResult);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load the dashboard.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 60_000);
    return () => clearInterval(timer);
  }, [load]);

  if (loading && !data) return <LoadingBlock label="Loading dashboard…" />;
  if (error) return <ErrorState description={error} onRetry={() => void load()} />;
  if (!data) return null;

  const needsAttention =
    data.sources.failing > 0 || data.moderation.open_reports > 0 || data.jobs.pending_review > 0;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-ink-900 sm:text-2xl">Overview</h1>
          <p className="mt-1 text-sm text-ink-500">Platform health and moderation queue.</p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-lg border border-ink-200 bg-white px-3 py-1.5 text-xs font-medium text-ink-700 hover:bg-ink-50"
        >
          Refresh
        </button>
      </header>

      {health && (
        <section className={cn(
          "rounded-xl border p-4",
          health.status === "ok" ? "border-emerald-200 bg-emerald-50/60" :
          health.status === "degraded" ? "border-amber-200 bg-amber-50/60" :
          "border-rose-200 bg-rose-50/60",
        )}>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <p className="text-sm font-semibold text-ink-900">
              System status: <span className="uppercase">{health.status}</span>
            </p>
            {Object.entries(health.components).map(([name, component]) => (
              <span key={name} className="inline-flex items-center gap-1.5 text-xs text-ink-700">
                <span className={cn(
                  "h-2 w-2 rounded-full",
                  component.status === "ok" ? "bg-emerald-500" :
                  component.status === "stale" || component.status === "unknown" ? "bg-amber-500" : "bg-rose-500",
                )} />
                {name}
                {component.latency_ms != null && <span className="text-ink-400">{component.latency_ms}ms</span>}
                {component.detail && <span className="text-ink-400">({component.detail})</span>}
              </span>
            ))}
          </div>
          {health.warnings.length > 0 && (
            <ul className="mt-2.5 space-y-1">
              {health.warnings.map((warning) => (
                <li key={warning} className="text-xs font-medium text-rose-800">⚠ {warning}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      {needsAttention && (
        <section className="rounded-xl border border-amber-200 bg-amber-50 p-4">
          <h2 className="text-sm font-bold text-amber-900">Needs your attention</h2>
          <ul className="mt-2 space-y-1.5 text-sm text-amber-900">
            {data.sources.failing > 0 && (
              <li>
                <Link href="/admin/sources" className="font-medium underline underline-offset-2">
                  {data.sources.failing} source{data.sources.failing === 1 ? " is" : "s are"} failing
                </Link>
              </li>
            )}
            {data.moderation.open_reports > 0 && (
              <li>
                <Link href="/admin/reports" className="font-medium underline underline-offset-2">
                  {data.moderation.open_reports} open report{data.moderation.open_reports === 1 ? "" : "s"}
                </Link>
              </li>
            )}
            {data.jobs.pending_review > 0 && (
              <li>
                <Link href="/admin/jobs?status=pending_review" className="font-medium underline underline-offset-2">
                  {data.jobs.pending_review} job{data.jobs.pending_review === 1 ? "" : "s"} pending review
                </Link>
              </li>
            )}
          </ul>
        </section>
      )}

      <Group title="Jobs">
        <Stat label="Total" value={data.jobs.total} />
        <Stat label="Active" value={data.jobs.active} tone="good" />
        <Stat label="Added today" value={data.jobs.today} />
        <Stat label="This week" value={data.jobs.this_week} />
        <Stat label="Expired" value={data.jobs.expired} />
        <Stat label="Pending review" value={data.jobs.pending_review} tone={data.jobs.pending_review > 0 ? "warn" : undefined} />
        <Stat label="Hidden" value={data.jobs.hidden} />
        <Stat label="Duplicates merged" value={data.jobs.duplicates} />
      </Group>

      <Group title="Sources">
        <Stat label="Configured" value={data.sources.total} />
        <Stat label="Enabled" value={data.sources.enabled} tone="good" />
        <Stat label="Degraded" value={data.sources.degraded} tone={data.sources.degraded > 0 ? "warn" : undefined} />
        <Stat label="Failing" value={data.sources.failing} tone={data.sources.failing > 0 ? "bad" : undefined} />
        <Stat label="Failed runs (24h)" value={data.sources.failed_runs_24h} tone={data.sources.failed_runs_24h > 0 ? "warn" : undefined} />
      </Group>

      <Group title="Users & engagement">
        <Stat label="Users" value={data.users.total} />
        <Stat label="New this week" value={data.users.new_this_week} />
        <Stat label="Suspended" value={data.users.suspended} />
        <Stat label="Active alerts" value={data.alerts.active} />
        <Stat label="Open reports" value={data.moderation.open_reports} tone={data.moderation.open_reports > 0 ? "warn" : undefined} />
        <Stat label="Duplicate links" value={data.moderation.duplicate_links} />
      </Group>
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-3 text-sm font-bold text-ink-900">{title}</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{children}</div>
    </section>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: "good" | "warn" | "bad" }) {
  return (
    <div className={cn(
      "rounded-xl border bg-white p-4",
      tone === "bad" ? "border-rose-200" : tone === "warn" ? "border-amber-200" : "border-ink-200",
    )}>
      <p className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</p>
      <p className={cn(
        "mt-1.5 text-2xl font-bold tracking-tight",
        tone === "bad" ? "text-rose-700" : tone === "warn" ? "text-amber-700" :
        tone === "good" ? "text-emerald-700" : "text-ink-900",
      )}>
        {value.toLocaleString("en-PK")}
      </p>
    </div>
  );
}
