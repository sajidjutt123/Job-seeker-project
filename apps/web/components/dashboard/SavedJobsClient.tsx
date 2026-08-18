"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { JobCard } from "@/components/jobs/JobCard";
import { Input, Select } from "@/components/ui/Input";
import { EmptyState, ErrorState, JobListSkeleton } from "@/components/ui/states";
import { api, ApiError, buildQuery } from "@/lib/api";
import { pluralize } from "@/lib/format";
import type { Paged, SavedJobItem } from "@/lib/types";

const SORT_OPTIONS = [
  { value: "saved_newest", label: "Recently saved" },
  { value: "saved_oldest", label: "Oldest saved" },
  { value: "posted_newest", label: "Recently posted" },
  { value: "deadline", label: "Closing soon" },
];

const STATUS_OPTIONS = [
  { value: "active", label: "Still open" },
  { value: "expired", label: "Expired" },
  { value: "closed", label: "Closed" },
];

export function SavedJobsClient() {
  const [data, setData] = useState<Paged<SavedJobItem> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [sort, setSort] = useState("saved_newest");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);

  // Debounce typing so we do not fire a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(query);
      setPage(1);
    }, 350);
    return () => clearTimeout(timer);
  }, [query]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.get<Paged<SavedJobItem>>(
        `/saved-jobs${buildQuery({ q: debouncedQuery || undefined, sort, status: status || undefined, page, page_size: 20 })}`,
        { revalidate: false },
      );
      setData(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load your saved jobs.");
    } finally {
      setLoading(false);
    }
  }, [debouncedQuery, sort, status, page]);

  useEffect(() => {
    void load();
  }, [load]);

  const onRemoved = (jobId: string, saved: boolean) => {
    if (saved) return;
    // Remove locally so the list reacts instantly; the count comes back correct on next load.
    setData((current) =>
      current
        ? { ...current, items: current.items.filter((i) => i.job.id !== jobId), total: Math.max(0, current.total - 1) }
        : current,
    );
  };

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-bold tracking-tight text-ink-900 sm:text-2xl">Saved jobs</h1>
        <p className="mt-1 text-sm text-ink-500">
          {data ? pluralize(data.total, "job") + " saved" : "Your shortlist, stored on your account."}
        </p>
      </header>

      <div className="flex flex-wrap gap-2.5">
        <Input
          type="search"
          placeholder="Search your saved jobs"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          wrapperClassName="min-w-48 flex-1"
          aria-label="Search saved jobs"
          leftIcon={
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" aria-hidden="true">
              <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" strokeLinecap="round" />
            </svg>
          }
        />
        <Select
          aria-label="Filter by status"
          placeholder="All statuses"
          options={STATUS_OPTIONS}
          value={status}
          onChange={(e) => { setStatus(e.target.value); setPage(1); }}
          wrapperClassName="w-40"
        />
        <Select
          aria-label="Sort saved jobs"
          options={SORT_OPTIONS}
          value={sort}
          onChange={(e) => { setSort(e.target.value); setPage(1); }}
          wrapperClassName="w-44"
        />
      </div>

      {loading ? (
        <JobListSkeleton count={4} />
      ) : error ? (
        <ErrorState description={error} onRetry={() => void load()} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title={debouncedQuery || status ? "No saved jobs match" : "You have not saved any jobs yet"}
          description={
            debouncedQuery || status
              ? "Try a different keyword or clear the filters."
              : "Tap the bookmark icon on any job to keep it here."
          }
          action={
            <Link
              href="/jobs"
              className="inline-flex h-9 items-center rounded-lg bg-brand-700 px-3.5 text-sm font-semibold text-white hover:bg-brand-800"
            >
              Browse jobs
            </Link>
          }
        />
      ) : (
        <>
          <div className="space-y-3">
            {data.items.map((item) => (
              <div key={item.id}>
                <JobCard job={{ ...item.job, is_saved: true }} onSavedChange={onRemoved} />
                {item.note && (
                  <p className="mt-1.5 rounded-lg bg-ink-100 px-3 py-2 text-xs text-ink-600">
                    <span className="font-medium">Your note:</span> {item.note}
                  </p>
                )}
              </div>
            ))}
          </div>

          {data.total_pages > 1 && (
            <div className="flex items-center justify-center gap-3 pt-4">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="rounded-lg border border-ink-200 bg-white px-3.5 py-2 text-sm font-medium text-ink-700 hover:bg-ink-50 disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-sm text-ink-500">Page {data.page} of {data.total_pages}</span>
              <button
                type="button"
                onClick={() => setPage((p) => p + 1)}
                disabled={!data.has_next}
                className="rounded-lg border border-ink-200 bg-white px-3.5 py-2 text-sm font-medium text-ink-700 hover:bg-ink-50 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
