"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { ErrorState, LoadingBlock } from "@/components/ui/states";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { relativeTime } from "@/lib/format";

interface AdminSource {
  id: string;
  name: string;
  slug: string;
  type: string;
  connector_key: string;
  enabled: boolean;
  status: string;
  priority: number;
  fetch_interval_minutes: number;
  reliability_score: number;
  config: Record<string, unknown>;
  requires_credentials: boolean;
  credential_env_keys: string[];
  last_run_at?: string | null;
  last_success_at?: string | null;
  last_failure_at?: string | null;
  last_error?: string | null;
  consecutive_failures: number;
  total_runs: number;
  total_jobs_collected: number;
  error_count: number;
  active_jobs: number;
  is_seed: boolean;
  notes?: string | null;
  website_url?: string | null;
}

interface SourceRun {
  id: string;
  status: string;
  trigger: string;
  attempt: number;
  started_at: string;
  duration_ms?: number | null;
  fetched: number;
  valid: number;
  rejected: number;
  duplicates: number;
  created: number;
  updated: number;
  error_message?: string | null;
  error_type?: string | null;
  stats: Record<string, unknown>;
}

const STATUS_TONES: Record<string, string> = {
  healthy: "bg-emerald-100 text-emerald-800",
  degraded: "bg-amber-100 text-amber-800",
  failing: "bg-rose-100 text-rose-800",
  disabled: "bg-ink-100 text-ink-600",
  needs_credentials: "bg-violet-100 text-violet-800",
  unknown: "bg-ink-100 text-ink-600",
};

export function SourcesClient() {
  const toast = useToast();
  const [sources, setSources] = useState<AdminSource[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [runsFor, setRunsFor] = useState<AdminSource | null>(null);
  const [runs, setRuns] = useState<SourceRun[] | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSources(await api.get<AdminSource[]>("/admin/sources", { revalidate: false }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load sources.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = async (source: AdminSource) => {
    setBusy(source.id);
    try {
      await api.patch(`/admin/sources/${source.id}`, { enabled: !source.enabled });
      toast.success(`${source.name} ${source.enabled ? "disabled" : "enabled"}.`);
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not update the source.");
    } finally {
      setBusy(null);
    }
  };

  const runNow = async (source: AdminSource) => {
    setBusy(source.id);
    try {
      const result = await api.post<{ queued: boolean; message: string }>(
        `/admin/sources/${source.id}/run`,
      );
      if (result.queued) toast.success(result.message);
      else toast.error(result.message);
      // Give the worker a moment, then refresh the health columns.
      setTimeout(() => void load(), 4000);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not queue the run.");
    } finally {
      setBusy(null);
    }
  };

  const openRuns = async (source: AdminSource) => {
    setRunsFor(source);
    setRuns(null);
    try {
      setRuns(await api.get<SourceRun[]>(`/admin/sources/${source.id}/runs?limit=20`, { revalidate: false }));
    } catch {
      setRuns([]);
    }
  };

  if (loading && !sources) return <LoadingBlock label="Loading sources…" />;
  if (error) return <ErrorState description={error} onRetry={() => void load()} />;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-ink-900 sm:text-2xl">Sources</h1>
          <p className="mt-1 text-sm text-ink-500">
            Each source is an isolated connector. Enable, configure and monitor them independently.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void load()}>Refresh</Button>
      </header>

      <div className="overflow-x-auto rounded-xl border border-ink-200 bg-white">
        <table className="w-full min-w-[64rem] text-sm">
          <thead className="border-b border-ink-200 bg-ink-50 text-left">
            <tr>
              <Th>Source</Th>
              <Th>Status</Th>
              <Th>Interval</Th>
              <Th className="text-right">Active jobs</Th>
              <Th className="text-right">Collected</Th>
              <Th className="text-right">Errors</Th>
              <Th>Last run</Th>
              <Th className="text-right">Actions</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-100">
            {(sources ?? []).map((source) => (
              <tr key={source.id} className={cn(source.is_seed && "bg-amber-50/40")}>
                <td className="px-4 py-3">
                  <p className="font-medium text-ink-900">
                    {source.name}
                    {source.is_seed && (
                      <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-semibold text-amber-800">
                        DEV DATA
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 font-mono text-xs text-ink-500">{source.connector_key}</p>
                  {source.last_error && (
                    <p className="mt-1 max-w-md truncate text-xs text-rose-700" title={source.last_error}>
                      {source.last_error}
                    </p>
                  )}
                  {source.requires_credentials && source.credential_env_keys.length > 0 && (
                    <p className="mt-1 text-xs text-violet-700">
                      Needs env: {source.credential_env_keys.join(", ")}
                    </p>
                  )}
                </td>
                <td className="px-4 py-3">
                  <span className={cn("inline-block rounded px-2 py-0.5 text-xs font-medium",
                    STATUS_TONES[source.status] ?? STATUS_TONES.unknown)}>
                    {source.status.replace(/_/g, " ")}
                  </span>
                </td>
                <td className="px-4 py-3 text-ink-600">{source.fetch_interval_minutes}m</td>
                <td className="px-4 py-3 text-right font-medium text-ink-900">{source.active_jobs}</td>
                <td className="px-4 py-3 text-right text-ink-600">{source.total_jobs_collected}</td>
                <td className={cn("px-4 py-3 text-right", source.error_count > 0 ? "text-rose-700" : "text-ink-400")}>
                  {source.error_count}
                </td>
                <td className="px-4 py-3 text-xs text-ink-500">
                  {source.last_run_at ? relativeTime(source.last_run_at) : "Never"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-1.5">
                    <Button variant="ghost" size="sm" onClick={() => void openRuns(source)}>History</Button>
                    <Button
                      variant="ghost" size="sm"
                      disabled={busy === source.id || !source.enabled}
                      onClick={() => void runNow(source)}
                    >
                      Run now
                    </Button>
                    <Button
                      variant={source.enabled ? "outline" : "primary"} size="sm"
                      disabled={busy === source.id}
                      onClick={() => void toggle(source)}
                    >
                      {source.enabled ? "Disable" : "Enable"}
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Modal
        open={Boolean(runsFor)}
        onClose={() => setRunsFor(null)}
        title={`Run history — ${runsFor?.name ?? ""}`}
        description="Most recent ingestion runs for this source."
        size="lg"
      >
        {runs === null ? (
          <LoadingBlock label="Loading history…" />
        ) : runs.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-500">This source has not run yet.</p>
        ) : (
          <ul className="space-y-2.5">
            {runs.map((run) => (
              <li key={run.id} className="rounded-lg border border-ink-200 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className={cn(
                    "rounded px-2 py-0.5 text-xs font-semibold",
                    run.status === "success" ? "bg-emerald-100 text-emerald-800" :
                    run.status === "partial" ? "bg-amber-100 text-amber-800" :
                    run.status === "failed" ? "bg-rose-100 text-rose-800" : "bg-ink-100 text-ink-700",
                  )}>
                    {run.status}
                  </span>
                  <span className="text-xs text-ink-500">
                    {relativeTime(run.started_at)} · {run.trigger}
                    {run.attempt > 1 && ` · attempt ${run.attempt}`}
                    {run.duration_ms != null && ` · ${run.duration_ms}ms`}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-600">
                  <span>fetched {run.fetched}</span>
                  <span>valid {run.valid}</span>
                  <span className="text-emerald-700">created {run.created}</span>
                  <span>updated {run.updated}</span>
                  <span>duplicates {run.duplicates}</span>
                  {run.rejected > 0 && <span className="text-amber-700">rejected {run.rejected}</span>}
                </div>
                {run.error_message && (
                  <p className="mt-2 rounded bg-rose-50 p-2 font-mono text-xs text-rose-800">
                    {run.error_type}: {run.error_message}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Modal>
    </div>
  );
}

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <th className={cn("px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink-500", className)}>
      {children}
    </th>
  );
}
