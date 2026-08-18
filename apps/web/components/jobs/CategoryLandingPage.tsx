import Link from "next/link";

import { JobCard } from "@/components/jobs/JobCard";
import { SearchBar } from "@/components/search/SearchBar";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { pluralize } from "@/lib/format";
import { fetchJobs, type SearchParams } from "@/lib/server-api";

/**
 * Shared implementation for the curated landing pages (/remote-jobs, /government-jobs,
 * /internships). Keeps a single well-tested layout instead of three near-duplicates.
 */
export async function CategoryLandingPage({
  title, intro, filters, searchHref, emptyTitle, emptyDescription, notice,
}: {
  title: string;
  intro: string;
  filters: SearchParams;
  searchHref: string;
  emptyTitle: string;
  emptyDescription: string;
  notice?: string;
}) {
  const result = await fetchJobs({ ...filters, page_size: 20, sort: "newest" });

  return (
    <>
      <section className="border-b border-ink-200 bg-white">
        <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 sm:py-14 lg:px-8">
          <nav aria-label="Breadcrumb" className="mb-4 flex items-center gap-1.5 text-sm text-ink-500">
            <Link href="/" className="hover:text-brand-700">Home</Link>
            <span aria-hidden="true">/</span>
            <span className="font-medium text-ink-700">{title}</span>
          </nav>

          <h1 className="text-2xl font-bold tracking-tight text-ink-900 sm:text-3xl">{title}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-600 sm:text-base">{intro}</p>
          {result.ok && result.data.total > 0 && (
            <p className="mt-2 text-sm font-medium text-brand-700">
              {pluralize(result.data.total, "opportunity", "opportunities")} open right now
            </p>
          )}

          <div className="mt-6">
            <SearchBar size="md" />
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
        {notice && (
          <p className="mb-6 rounded-lg border border-ink-200 bg-white p-4 text-sm leading-relaxed text-ink-600">
            {notice}
          </p>
        )}

        {!result.ok ? (
          <ErrorState description={result.error} />
        ) : result.data.items.length === 0 ? (
          <EmptyState
            title={emptyTitle}
            description={emptyDescription}
            action={
              <Link
                href="/dashboard/alerts"
                className="inline-flex h-9 items-center rounded-lg bg-brand-700 px-3.5 text-sm font-semibold text-white hover:bg-brand-800"
              >
                Create an alert
              </Link>
            }
          />
        ) : (
          <>
            <div className="space-y-3">
              {result.data.items.map((job) => <JobCard key={job.id} job={job} />)}
            </div>
            {result.data.has_next && (
              <div className="mt-8 text-center">
                <Link
                  href={searchHref}
                  className="inline-flex h-11 items-center rounded-lg border border-ink-300 bg-white px-5 text-sm font-semibold text-ink-800 hover:bg-ink-50"
                >
                  See all {pluralize(result.data.total, "job")}
                </Link>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
