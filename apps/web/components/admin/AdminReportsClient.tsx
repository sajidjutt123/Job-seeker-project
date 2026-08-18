"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Select, Textarea } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/states";
import { api, ApiError } from "@/lib/api";
import { relativeTime } from "@/lib/format";

interface Report {
  id: string;
  reason: string;
  details?: string | null;
  status: string;
  reporter_email?: string | null;
  created_at: string;
  resolution_note?: string | null;
  job: { id: string; title: string; slug: string; company?: string | null; status: string; apply_url: string } | null;
}

const REASON_LABELS: Record<string, string> = {
  expired: "No longer open",
  spam: "Spam",
  scam: "Suspected scam",
  duplicate: "Duplicate",
  wrong_information: "Wrong information",
  broken_link: "Broken link",
  offensive: "Offensive",
  other: "Other",
};

export function AdminReportsClient() {
  const toast = useToast();
  const [reports, setReports] = useState<Report[] | null>(null);
  const [status, setStatus] = useState("open");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [resolving, setResolving] = useState<Report | null>(null);
  const [action, setAction] = useState<"resolve" | "reject" | "remove_job">("resolve");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.get<{ items: Report[] }>(`/admin/reports?status=${status}`, { revalidate: false });
      setReports(result.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load reports.");
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => { void load(); }, [load]);

  const submit = async () => {
    if (!resolving) return;
    setSaving(true);
    try {
      await api.post(`/admin/reports/${resolving.id}/resolve`, { action, note: note || null });
      toast.success("Report actioned.");
      setResolving(null);
      setNote("");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not action the report.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-ink-900 sm:text-2xl">Reports</h1>
          <p className="mt-1 text-sm text-ink-500">Listings flagged by users for review.</p>
        </div>
        <Select
          aria-label="Filter by status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          options={[
            { value: "open", label: "Open" },
            { value: "resolved", label: "Resolved" },
            { value: "rejected", label: "Rejected" },
            { value: "all", label: "All" },
          ]}
          wrapperClassName="w-40"
        />
      </header>

      {loading && !reports ? (
        <LoadingBlock label="Loading reports…" />
      ) : error ? (
        <ErrorState description={error} onRetry={() => void load()} />
      ) : !reports || reports.length === 0 ? (
        <EmptyState
          title={status === "open" ? "No open reports" : "Nothing here"}
          description={status === "open" ? "The moderation queue is clear." : "Try a different status filter."}
        />
      ) : (
        <ul className="space-y-3">
          {reports.map((report) => (
            <li key={report.id} className="rounded-xl border border-ink-200 bg-white p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
                      {REASON_LABELS[report.reason] ?? report.reason}
                    </span>
                    <span className="text-xs text-ink-400">{relativeTime(report.created_at)}</span>
                  </div>

                  {report.job ? (
                    <Link
                      href={`/jobs/${report.job.slug}`} target="_blank"
                      className="mt-2 block text-sm font-semibold text-ink-900 hover:text-brand-700"
                    >
                      {report.job.title}
                    </Link>
                  ) : (
                    <p className="mt-2 text-sm text-ink-500">Job no longer exists</p>
                  )}
                  {report.job?.company && (
                    <p className="text-xs text-ink-500">{report.job.company} · status {report.job.status}</p>
                  )}
                  {report.details && (
                    <p className="mt-2 rounded bg-ink-50 p-2 text-xs leading-relaxed text-ink-700">
                      {report.details}
                    </p>
                  )}
                  {report.reporter_email && (
                    <p className="mt-1.5 text-xs text-ink-400">Reported by {report.reporter_email}</p>
                  )}
                  {report.resolution_note && (
                    <p className="mt-1.5 text-xs text-ink-500">Resolution: {report.resolution_note}</p>
                  )}
                </div>

                {report.status === "open" && (
                  <Button size="sm" variant="outline" onClick={() => { setResolving(report); setAction("resolve"); }}>
                    Action
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <Modal
        open={Boolean(resolving)}
        onClose={() => setResolving(null)}
        title="Action this report"
        description={resolving?.job?.title}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setResolving(null)}>Cancel</Button>
            <Button size="sm" onClick={submit} loading={saving}>Confirm</Button>
          </div>
        }
      >
        <div className="space-y-4">
          <Select
            label="What should happen?"
            value={action}
            onChange={(e) => setAction(e.target.value as typeof action)}
            options={[
              { value: "resolve", label: "Valid — mark resolved (leave job as is)" },
              { value: "remove_job", label: "Valid — remove the job from the site" },
              { value: "reject", label: "Not valid — reject this report" },
            ]}
          />
          <Textarea
            label="Note (recorded in the audit log)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={1000}
          />
        </div>
      </Modal>
    </div>
  );
}
