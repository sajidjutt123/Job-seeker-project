import Link from "next/link";

import { EmptyState, ErrorState } from "@/components/ui/states";
import type { JobListItem } from "@/lib/types";

import { JobCard } from "./JobCard";

/**
 * A homepage feed section. Renders whatever the server fetch produced — including a real
 * error state — so a single failing section never blanks the page.
 */
export function JobSection({
  title, description, viewAllHref, viewAllLabel = "View all", jobs, error, emptyMessage, columns = 2,
}: {
  title: string;
  description?: string;
  viewAllHref?: string;
  viewAllLabel?: string;
  jobs: JobListItem[];
  error?: string;
  emptyMessage?: string;
  columns?: 1 | 2;
}) {
  return (
    <section className="py-10 sm:py-12">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-ink-900 sm:text-2xl">{title}</h2>
          {description && <p className="mt-1 text-sm text-ink-500">{description}</p>}
        </div>
        {viewAllHref && (
          <Link
            href={viewAllHref}
            className="inline-flex items-center gap-1 text-sm font-semibold text-brand-700 transition-colors hover:text-brand-800"
          >
            {viewAllLabel}
            <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
            </svg>
          </Link>
        )}
      </div>

      {error ? (
        <ErrorState
          title="This section could not load"
          description={error}
        />
      ) : jobs.length === 0 ? (
        <EmptyState
          title="Nothing here yet"
          description={emptyMessage ?? "New opportunities appear here as soon as our sources publish them."}
        />
      ) : (
        <div className={columns === 2 ? "grid gap-3 lg:grid-cols-2" : "space-y-3"}>
          {jobs.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      )}
    </section>
  );
}
