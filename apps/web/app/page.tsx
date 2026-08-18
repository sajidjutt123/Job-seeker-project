import type { Metadata } from "next";
import Link from "next/link";

import { JobSection } from "@/components/jobs/JobSection";
import { SearchBar } from "@/components/search/SearchBar";
import { fetchJobFacets, fetchLatestJobs } from "@/lib/server-api";
import { pluralize } from "@/lib/format";

export const metadata: Metadata = {
  title: "Find the right job in Pakistan",
  description:
    "Search government, private, remote and internship opportunities from across Pakistan in one " +
    "place. Every listing links back to the original source so you always apply directly.",
  alternates: { canonical: "/" },
};

// Homepage content changes as sources ingest; revalidate frequently but serve cached HTML fast.
export const revalidate = 120;

const QUICK_FILTERS = [
  { label: "Government", href: "/government-jobs" },
  { label: "Remote", href: "/remote-jobs" },
  { label: "Internships", href: "/internships" },
  { label: "Fresh Graduate", href: "/jobs?fresh_graduate=true" },
  { label: "Lahore", href: "/jobs-in-lahore" },
  { label: "Karachi", href: "/jobs-in-karachi" },
  { label: "Islamabad", href: "/jobs-in-islamabad" },
];

export default async function HomePage() {
  // Fetch every section in parallel; each degrades independently.
  const [facets, latest, remote, government, internships] = await Promise.all([
    fetchJobFacets(),
    fetchLatestJobs({ limit: 8 }),
    fetchLatestJobs({ limit: 4, remote: true }),
    fetchLatestJobs({ limit: 4, government: true }),
    fetchLatestJobs({ limit: 4, internship: true }),
  ]);

  const stats = facets.ok ? facets.data.totals : null;
  const categories = facets.ok ? facets.data.categories : [];
  const cities = facets.ok ? facets.data.cities : [];

  return (
    <>
      {/* ----------------------------------------------------------- Hero -- */}
      <section className="border-b border-ink-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6 sm:py-20 lg:px-8">
          <div className="mx-auto max-w-3xl text-center">
            <p className="mb-4 inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-800 ring-1 ring-inset ring-brand-200">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-500 opacity-75" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-brand-600" />
              </span>
              {stats ? `${pluralize(stats.posted_today, "new job")} added today` : "Updated continuously"}
            </p>

            <h1 className="text-3xl font-bold tracking-tight text-ink-900 sm:text-4xl lg:text-5xl">
              Find the right job in Pakistan
            </h1>
            <p className="mx-auto mt-4 max-w-2xl text-base leading-relaxed text-ink-600 sm:text-lg">
              RozgarPK brings opportunities from multiple authorised sources — government portals,
              employer career pages and partner feeds — into one searchable place. You always apply
              on the original site.
            </p>

            <div className="mt-8">
              <SearchBar />
            </div>

            <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
              <span className="text-xs font-medium text-ink-500">Popular:</span>
              {QUICK_FILTERS.map((filter) => (
                <Link
                  key={filter.href}
                  href={filter.href}
                  className="rounded-full border border-ink-200 bg-white px-3 py-1.5 text-xs font-medium text-ink-700 transition-colors hover:border-brand-300 hover:bg-brand-50 hover:text-brand-800"
                >
                  {filter.label}
                </Link>
              ))}
            </div>
          </div>

          {stats && (
            <dl className="mx-auto mt-12 grid max-w-3xl grid-cols-2 gap-px overflow-hidden rounded-xl border border-ink-200 bg-ink-200 sm:grid-cols-4">
              <Stat label="Active jobs" value={stats.active} />
              <Stat label="Remote roles" value={stats.remote} />
              <Stat label="Government" value={stats.government} />
              <Stat label="Internships" value={stats.internships} />
            </dl>
          )}
        </div>
      </section>

      <div className="mx-auto max-w-7xl divide-y divide-ink-200 px-4 sm:px-6 lg:px-8">
        {/* ------------------------------------------------------- Latest -- */}
        <JobSection
          title="Latest jobs"
          description="The most recently published opportunities across all sources."
          viewAllHref="/jobs"
          jobs={latest.ok ? latest.data : []}
          error={latest.ok ? undefined : latest.error}
        />

        {/* --------------------------------------------------- Categories -- */}
        {categories.length > 0 && (
          <section className="py-10 sm:py-12">
            <h2 className="text-xl font-bold tracking-tight text-ink-900 sm:text-2xl">
              Popular categories
            </h2>
            <p className="mt-1 text-sm text-ink-500">Browse openings by field.</p>
            <div className="mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
              {categories.slice(0, 12).map((category) => (
                <Link
                  key={category.slug}
                  href={`/jobs?category=${category.slug}`}
                  className="group flex items-center justify-between gap-2 rounded-lg border border-ink-200 bg-white px-4 py-3.5 transition-all hover:border-brand-300 hover:shadow-card-hover"
                >
                  <span className="truncate text-sm font-medium text-ink-800 group-hover:text-brand-800">
                    {category.label}
                  </span>
                  <span className="shrink-0 rounded-md bg-ink-100 px-1.5 py-0.5 text-xs font-medium text-ink-600">
                    {category.count}
                  </span>
                </Link>
              ))}
            </div>
          </section>
        )}

        {/* --------------------------------------------------- Remote/Gov -- */}
        <JobSection
          title="Remote jobs"
          description="Work from anywhere in Pakistan."
          viewAllHref="/remote-jobs"
          jobs={remote.ok ? remote.data : []}
          error={remote.ok ? undefined : remote.error}
          emptyMessage="No remote roles are open right now. Create an alert and we will email you when one appears."
        />

        <JobSection
          title="Government jobs"
          description="Public sector and government-linked vacancies."
          viewAllHref="/government-jobs"
          jobs={government.ok ? government.data : []}
          error={government.ok ? undefined : government.error}
          emptyMessage="No government vacancies are listed right now. Enable a government RSS source in the admin panel to start ingesting them."
        />

        <JobSection
          title="Internship opportunities"
          description="Start your career with a paid or structured internship."
          viewAllHref="/internships"
          jobs={internships.ok ? internships.data : []}
          error={internships.ok ? undefined : internships.error}
          emptyMessage="No internships are open right now. Set an alert so you hear first."
        />

        {/* ------------------------------------------------------- Cities -- */}
        {cities.length > 0 && (
          <section className="py-10 sm:py-12">
            <h2 className="text-xl font-bold tracking-tight text-ink-900 sm:text-2xl">Jobs by city</h2>
            <p className="mt-1 text-sm text-ink-500">Find work close to home.</p>
            <div className="mt-5 flex flex-wrap gap-2">
              {cities.slice(0, 20).map((city) => (
                <Link
                  key={city.slug}
                  href={`/jobs-in-${city.slug}`}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-ink-200 bg-white px-3.5 py-2 text-sm font-medium text-ink-700 transition-colors hover:border-brand-300 hover:bg-brand-50 hover:text-brand-800"
                >
                  {city.name}
                  <span className="text-xs text-ink-400">{city.count}</span>
                </Link>
              ))}
            </div>
          </section>
        )}

        {/* -------------------------------------------------- Attribution -- */}
        <section className="py-10 sm:py-12">
          <div className="rounded-xl border border-ink-200 bg-white p-6 sm:p-8">
            <div className="flex flex-col gap-6 sm:flex-row sm:items-start">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                  <path d="M12 3l8 4v5c0 4.5-3.2 8.3-8 9-4.8-.7-8-4.5-8-9V7l8-4z" strokeLinejoin="round" />
                  <path d="m9 12 2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <div>
                <h2 className="text-lg font-bold text-ink-900">Where these jobs come from</h2>
                <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink-600">
                  Every listing on RozgarPK is collected from a source that permits aggregation —
                  official APIs, employer career boards and published RSS feeds. We never bypass
                  logins, CAPTCHAs or access restrictions. Each job card shows exactly which source
                  it came from, and the apply button takes you to the original posting so your
                  application goes directly to the employer.
                </p>
                <Link
                  href="/sources"
                  className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-brand-700 transition-colors hover:text-brand-800"
                >
                  See all our sources
                  <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                    <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
                  </svg>
                </Link>
              </div>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-white px-4 py-5 text-center">
      <dd className="text-2xl font-bold tracking-tight text-ink-900">
        {value.toLocaleString("en-PK")}
      </dd>
      <dt className="mt-0.5 text-xs font-medium text-ink-500">{label}</dt>
    </div>
  );
}
