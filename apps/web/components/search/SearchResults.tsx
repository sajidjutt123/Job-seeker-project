"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { JobCard } from "@/components/jobs/JobCard";
import { Button } from "@/components/ui/Button";
import { Drawer } from "@/components/ui/Modal";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { pluralize } from "@/lib/format";
import type { FilterOptions, JobSearchResponse } from "@/lib/types";

import { FilterPanel } from "./FilterPanel";
import { Pagination } from "./Pagination";

export function SearchResults({
  result, error, options, heading,
}: {
  result: JobSearchResponse | null;
  error?: string;
  options: FilterOptions | null;
  heading?: string;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const sort = params.get("sort") ?? (params.get("q") ? "relevance" : "newest");
  const activeFilterCount = countActiveFilters(params);

  const changeSort = (value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value === "newest") next.delete("sort");
    else next.set("sort", value);
    next.delete("page");
    router.push(`/jobs?${next.toString()}`, { scroll: false });
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      <div className="flex gap-8">
        {/* Desktop filter rail */}
        <aside className="hidden w-64 shrink-0 lg:block xl:w-72">
          <div className="sticky top-24 max-h-[calc(100vh-7rem)] overflow-y-auto rounded-xl border border-ink-200 bg-white p-4 pb-6">
            <FilterPanel options={options} />
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          {/* Result header */}
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-lg font-bold text-ink-900 sm:text-xl">
                {heading ?? "Search results"}
              </h1>
              {result && (
                <p className="mt-0.5 text-sm text-ink-500">
                  {result.total === 0
                    ? "No jobs matched"
                    : `${pluralize(result.total, "job")} found`}
                  {result.took_ms > 0 && <span className="text-ink-400"> · {result.took_ms}ms</span>}
                </p>
              )}
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="lg:hidden"
                onClick={() => setDrawerOpen(true)}
                leftIcon={
                  <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                    <path fillRule="evenodd" d="M2.6 4.2A1 1 0 013.5 3.7h13a1 1 0 01.78 1.63l-4.9 6.1v4.3a1 1 0 01-1.45.9l-2.4-1.2a1 1 0 01-.55-.9v-3.1l-4.9-6.1a1 1 0 01.12-1.13z" clipRule="evenodd" />
                  </svg>
                }
              >
                Filters
                {activeFilterCount > 0 && (
                  <span className="ml-1 rounded-full bg-brand-700 px-1.5 text-[11px] font-semibold text-white">
                    {activeFilterCount}
                  </span>
                )}
              </Button>

              <label className="sr-only" htmlFor="sort-select">Sort results</label>
              <select
                id="sort-select"
                value={sort}
                onChange={(e) => changeSort(e.target.value)}
                className="h-9 rounded-lg border border-ink-300 bg-white pl-3 pr-8 text-sm text-ink-800 focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-600/15"
              >
                <option value="newest">Newest</option>
                <option value="relevance">Most relevant</option>
                <option value="deadline">Closing soon</option>
                <option value="salary">Highest salary</option>
              </select>
            </div>
          </div>

          {/* Results */}
          {error ? (
            <ErrorState
              title="Search is unavailable"
              description={error}
              onRetry={() => router.refresh()}
            />
          ) : !result || result.items.length === 0 ? (
            <EmptyState
              title="No jobs found"
              description="Try a different keyword or remove some filters. You can also create an alert and we will email you when a matching job appears."
              action={
                <div className="flex flex-wrap justify-center gap-2">
                  <Button variant="outline" size="sm" onClick={() => router.push("/jobs")}>
                    Clear all filters
                  </Button>
                  <Link
                    href="/dashboard/alerts"
                    className="inline-flex h-9 items-center rounded-lg bg-brand-700 px-3.5 text-sm font-semibold text-white transition-colors hover:bg-brand-800"
                  >
                    Create job alert
                  </Link>
                </div>
              }
            />
          ) : (
            <>
              <div className="space-y-3">
                {result.items.map((job) => (
                  <JobCard key={job.id} job={job} />
                ))}
              </div>
              <Pagination page={result.page} totalPages={result.total_pages} className="mt-8" />
            </>
          )}
        </div>
      </div>

      {/* Mobile filter drawer */}
      <Drawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="Filters"
        footer={
          <Button fullWidth onClick={() => setDrawerOpen(false)}>
            Show {result ? pluralize(result.total, "job") : "results"}
          </Button>
        }
      >
        <FilterPanel options={options} onApplied={() => undefined} />
      </Drawer>
    </div>
  );
}

function countActiveFilters(params: URLSearchParams): number {
  const multi = ["category", "employment_type", "experience", "skills"];
  const single = [
    "city", "province", "education", "company", "remote", "government",
    "internship", "fresh_graduate", "salary_min", "salary_max", "posted_within_days",
  ];
  return (
    multi.reduce((sum, key) => sum + params.getAll(key).length, 0) +
    single.reduce((sum, key) => sum + (params.get(key) ? 1 : 0), 0)
  );
}
