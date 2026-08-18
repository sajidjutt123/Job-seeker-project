"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/states";
import { api, ApiError, buildQuery } from "@/lib/api";
import { cn } from "@/lib/cn";
import { relativeTime } from "@/lib/format";
import type { JobListItem, Paged } from "@/lib/types";

interface AdminJobDetail extends JobListItem {
  quality_score: number;
  quality_breakdown: Record<string, number>;
  classification_confidence: number;
  classification_method: string;
  source_job_id?: string | null;
  content_fingerprint?: string | null;
  is_canonical: boolean;
  hidden_by_admin: boolean;
  admin_note?: string | null;
  report_count: number;
  apply_url_ok?: boolean | null;
  last_seen_at?: string | null;
  description: string;
}

interface DuplicateLink {
  link_id: string;
  confidence: number;
  signals: Record<string, number>;
  job: { id: string; title: string; slug: string; company?: string | null; status: string; apply_url?: string };
}

const STATUS_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "expired", label: "Expired" },
  { value: "closed", label: "Closed" },
  { value: "pending_review", label: "Pending review" },
  { value: "removed", label: "Removed" },
];

export function AdminJobsClient() {
  const toast = useToast();
  const initialStatus = useSearchParams().get("status") ?? "";

  const [data, setData] = useState<Paged<JobListItem> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [status, setStatus] = useState(initialStatus);
  const [sort, setSort] = useState("newest");
  const [reportedOnly, setReportedOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [inspect, setInspect] = useState<AdminJobDetail | null>(null);
  const [duplicates, setDuplicates] = useState<{ duplicates: DuplicateLink[]; merged_into: DuplicateLink[] } | null>(null);
  const [actionNote, setActionNote] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => { setDebounced(query); setPage(1); }, 350);
    return () => clearTimeout(timer);
  }, [query]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.get<Paged<JobListItem>>(
        `/admin/jobs${buildQuery({
          q: debounced || undefined, status: status || undefined, sort,
          reported_only: reportedOnly || undefined, page, page_size: 25,
        })}`,
        { revalidate: false },
      ));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load jobs.");
    } finally {
      setLoading(false);
    }
  }, [debounced, status, sort, reportedOnly, page]);

  useEffect(() => { void load(); }, [load]);

  const openInspect = async (job: JobListItem) => {
    setActionNote("");
    setDuplicates(null);
    try {
      const [detail, dupes] = await Promise.all([
        api.get<AdminJobDetail>(`/admin/jobs/${job.id}`, { revalidate: false }),
        api.get<{ duplicates: DuplicateLink[]; merged_into: DuplicateLink[] }>(
          `/admin/jobs/${job.id}/duplicates`, { revalidate: false },
        ),
      ]);
      setInspect(detail);
      setDuplicates(dupes);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not load the job.");
    }
  };

  const act = async (jobId: string, action: "hide" | "restore" | "remove" | "approve") => {
    try {
      await api.post(`/admin/jobs/${jobId}/${action}`, action === "restore" || action === "approve" ? {} : { note: actionNote || null });
      toast.success(`Job ${action}d.`);
      setInspect(null);
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : `Could not ${action} the job.`);
    }
  };

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-bold tracking-tight text-ink-900 sm:text-2xl">Jobs</h1>
        <p className="mt-1 text-sm text-ink-500">
          Every listing including hidden, expired and duplicate records.
        </p>
      </header>

      <div className="flex flex-wrap gap-2.5">
        <Input
          type="search" placeholder="Search title, company or ID" value={query}
          onChange={(e) => setQuery(e.target.value)} wrapperClassName="min-w-56 flex-1"
          aria-label="Search jobs"
        />
        <Select
          aria-label="Status" placeholder="All statuses" options={STATUS_OPTIONS} value={status}
          onChange={(e) => { setStatus(e.target.value); setPage(1); }} wrapperClassName="w-44"
        />
        <Select
          aria-label="Sort" value={sort} onChange={(e) => { setSort(e.target.value); setPage(1); }}
          options={[
            { value: "newest", label: "Newest" },
            { value: "quality", label: "Quality score" },
            { value: "reports", label: "Most reported" },
            { value: "views", label: "Most viewed" },
          ]}
          wrapperClassName="w-44"
        />
        <Button
          variant={reportedOnly ? "primary" : "outline"} size="md"
          onClick={() => { setReportedOnly((v) => !v); setPage(1); }}
        >
          Reported only
        </Button>
      </div>

      {loading && !data ? (
        <LoadingBlock label="Loading jobs…" />
      ) : error ? (
        <ErrorState description={error} onRetry={() => void load()} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="No jobs match" description="Adjust the filters above." />
      ) : (
        <>
          <p className="text-sm text-ink-500">{data.total.toLocaleString("en-PK")} jobs</p>
          <div className="overflow-x-auto rounded-xl border border-ink-200 bg-white">
            <table className="w-full min-w-[52rem] text-sm">
              <thead className="border-b border-ink-200 bg-ink-50 text-left">
                <tr>
                  <th className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink-500">Job</th>
                  <th className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink-500">Source</th>
                  <th className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink-500">Status</th>
                  <th className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink-500">Posted</th>
                  <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-ink-500">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {data.items.map((job) => (
                  <tr key={job.id}>
                    <td className="px-4 py-3">
                      <p className="font-medium text-ink-900">{job.title}</p>
                      <p className="mt-0.5 text-xs text-ink-500">
                        {job.company_name ?? "No company"} · {job.city ?? (job.is_remote ? "Remote" : "—")}
                        {" · "}{job.category_label}
                      </p>
                    </td>
                    <td className="px-4 py-3 text-xs text-ink-600">{job.source?.label ?? "Direct"}</td>
                    <td className="px-4 py-3">
                      <span className={cn(
                        "rounded px-2 py-0.5 text-xs font-medium",
                        job.status === "active" ? "bg-emerald-100 text-emerald-800" :
                        job.status === "pending_review" ? "bg-amber-100 text-amber-800" :
                        "bg-ink-100 text-ink-600",
                      )}>
                        {job.status.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-ink-500">{relativeTime(job.posted_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-1.5">
                        <Link
                          href={`/jobs/${job.slug}`} target="_blank"
                          className="rounded-md px-2 py-1 text-xs font-medium text-ink-600 hover:bg-ink-100"
                        >
                          View
                        </Link>
                        <Button variant="ghost" size="sm" onClick={() => void openInspect(job)}>Inspect</Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.total_pages > 1 && (
            <div className="flex items-center justify-center gap-3">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Previous
              </Button>
              <span className="text-sm text-ink-500">Page {data.page} of {data.total_pages}</span>
              <Button variant="outline" size="sm" disabled={!data.has_next} onClick={() => setPage((p) => p + 1)}>
                Next
              </Button>
            </div>
          )}
        </>
      )}

      <Modal
        open={Boolean(inspect)}
        onClose={() => setInspect(null)}
        title={inspect?.title ?? ""}
        description={`${inspect?.company_name ?? "No company"} · ${inspect?.source?.label ?? "Direct"}`}
        size="lg"
        footer={
          inspect && (
            <div className="flex flex-wrap justify-end gap-2">
              {inspect.status === "pending_review" && (
                <Button size="sm" onClick={() => void act(inspect.id, "approve")}>Approve</Button>
              )}
              {inspect.hidden_by_admin ? (
                <Button variant="outline" size="sm" onClick={() => void act(inspect.id, "restore")}>Restore</Button>
              ) : (
                <Button variant="outline" size="sm" onClick={() => void act(inspect.id, "hide")}>Hide</Button>
              )}
              <Button variant="danger" size="sm" onClick={() => void act(inspect.id, "remove")}>Remove</Button>
            </div>
          )
        }
      >
        {inspect && (
          <div className="space-y-4 text-sm">
            <dl className="grid grid-cols-2 gap-3 rounded-lg bg-ink-50 p-3 text-xs sm:grid-cols-3">
              <Field label="Quality score" value={`${inspect.quality_score.toFixed(1)} / 100`} />
              <Field label="Classification" value={`${inspect.category} (${(inspect.classification_confidence * 100).toFixed(0)}%, ${inspect.classification_method})`} />
              <Field label="Canonical" value={inspect.is_canonical ? "Yes" : "No — merged"} />
              <Field label="Reports" value={String(inspect.report_count)} />
              <Field label="Apply URL check" value={inspect.apply_url_ok === null || inspect.apply_url_ok === undefined ? "Not checked" : inspect.apply_url_ok ? "OK" : "Broken"} />
              <Field label="Last seen in source" value={inspect.last_seen_at ? relativeTime(inspect.last_seen_at) : "—"} />
              <Field label="Source job ID" value={inspect.source_job_id ?? "—"} />
              <Field label="Fingerprint" value={inspect.content_fingerprint?.slice(0, 12) ?? "—"} />
              <Field label="Status" value={inspect.status} />
            </dl>

            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-500">Quality breakdown</p>
              <ul className="space-y-1 text-xs text-ink-600">
                {Object.entries(inspect.quality_breakdown).map(([factor, value]) => (
                  <li key={factor} className="flex justify-between gap-3">
                    <span>{factor.replace(/_/g, " ")}</span>
                    <span className={cn("font-mono", value < 0 && "text-rose-700")}>{value}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-500">Apply URL</p>
              <a
                href={inspect.apply_url} target="_blank" rel="noopener noreferrer nofollow"
                className="break-all text-xs text-brand-700 hover:underline"
              >
                {inspect.apply_url}
              </a>
            </div>

            {duplicates && (duplicates.duplicates.length > 0 || duplicates.merged_into.length > 0) && (
              <div>
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-500">
                  Duplicate matches
                </p>
                <ul className="space-y-1.5">
                  {[...duplicates.duplicates, ...duplicates.merged_into].map((link) => (
                    <li key={link.link_id} className="rounded border border-ink-200 p-2 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-ink-800">{link.job.title}</span>
                        <span className="font-mono text-ink-500">{(link.confidence * 100).toFixed(0)}%</span>
                      </div>
                      <p className="mt-0.5 text-ink-500">
                        {Object.entries(link.signals).map(([k, v]) => `${k} ${v}`).join(" · ")}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <Textarea
              label="Moderation note (saved with hide/remove)"
              value={actionNote}
              onChange={(e) => setActionNote(e.target.value)}
              maxLength={1000}
              placeholder="Why are you actioning this listing?"
            />
          </div>
        )}
      </Modal>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-ink-500">{label}</dt>
      <dd className="mt-0.5 break-words font-medium text-ink-800">{value}</dd>
    </div>
  );
}
