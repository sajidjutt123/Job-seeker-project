"use client";

import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/states";
import { api, ApiError } from "@/lib/api";
import { relativeTime } from "@/lib/format";

interface AuditLog {
  id: string;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  payload: Record<string, unknown>;
  admin_email?: string | null;
  created_at: string;
}

export function AdminAuditClient() {
  const [logs, setLogs] = useState<AuditLog[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setLogs(await api.get<AuditLog[]>("/admin/audit-logs?limit=100", { revalidate: false }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load the audit log.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-bold tracking-tight text-ink-900 sm:text-2xl">Audit log</h1>
        <p className="mt-1 text-sm text-ink-500">
          Every privileged action, recorded immutably.
        </p>
      </header>

      {loading && !logs ? (
        <LoadingBlock label="Loading audit log…" />
      ) : error ? (
        <ErrorState description={error} onRetry={() => void load()} />
      ) : !logs || logs.length === 0 ? (
        <EmptyState title="No admin actions yet" description="Actions you take here will be recorded." />
      ) : (
        <ul className="divide-y divide-ink-100 overflow-hidden rounded-xl border border-ink-200 bg-white">
          {logs.map((log) => (
            <li key={log.id} className="flex flex-wrap items-start justify-between gap-3 p-3.5">
              <div className="min-w-0">
                <p className="text-sm font-medium text-ink-900">
                  <span className="font-mono text-xs text-violet-700">{log.action}</span>
                  {" · "}
                  <span className="text-ink-600">{log.entity_type}</span>
                  {log.entity_id && <span className="ml-1 font-mono text-xs text-ink-400">{log.entity_id.slice(0, 8)}</span>}
                </p>
                {Object.keys(log.payload).length > 0 && (
                  <p className="mt-1 truncate font-mono text-xs text-ink-500">
                    {JSON.stringify(log.payload).slice(0, 160)}
                  </p>
                )}
              </div>
              <div className="shrink-0 text-right">
                <p className="text-xs text-ink-600">{log.admin_email ?? "Unknown admin"}</p>
                <p className="text-xs text-ink-400">{relativeTime(log.created_at)}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
