import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { JobCard } from "@/components/jobs/JobCard";
import { SearchBar } from "@/components/search/SearchBar";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { pluralize } from "@/lib/format";
import { fetchJobs } from "@/lib/server-api";

/**
 * SEO landing page for a city. Served at /jobs-in-lahore via a rewrite in next.config.ts.
 * Only cities in our reference list resolve; anything else 404s so we never generate
 * thin, low-quality pages for arbitrary strings.
 */
const CITIES: Record<string, { name: string; province: string }> = {
  karachi: { name: "Karachi", province: "Sindh" },
  lahore: { name: "Lahore", province: "Punjab" },
  islamabad: { name: "Islamabad", province: "Islamabad Capital Territory" },
  rawalpindi: { name: "Rawalpindi", province: "Punjab" },
  faisalabad: { name: "Faisalabad", province: "Punjab" },
  multan: { name: "Multan", province: "Punjab" },
  peshawar: { name: "Peshawar", province: "Khyber Pakhtunkhwa" },
  quetta: { name: "Quetta", province: "Balochistan" },
  gujranwala: { name: "Gujranwala", province: "Punjab" },
  sialkot: { name: "Sialkot", province: "Punjab" },
  hyderabad: { name: "Hyderabad", province: "Sindh" },
  sukkur: { name: "Sukkur", province: "Sindh" },
  bahawalpur: { name: "Bahawalpur", province: "Punjab" },
  sargodha: { name: "Sargodha", province: "Punjab" },
  abbottabad: { name: "Abbottabad", province: "Khyber Pakhtunkhwa" },
  gilgit: { name: "Gilgit", province: "Gilgit-Baltistan" },
  muzaffarabad: { name: "Muzaffarabad", province: "Azad Jammu and Kashmir" },
};

export function generateStaticParams() {
  return Object.keys(CITIES).map((city) => ({ city }));
}

export const revalidate = 600;

export async function generateMetadata({ params }: { params: Promise<{ city: string }> }): Promise<Metadata> {
  const { city } = await params;
  const info = CITIES[city];
  if (!info) return { title: "City not found", robots: { index: false, follow: false } };

  return {
    title: `Jobs in ${info.name} — Latest vacancies`,
    description:
      `Browse the latest job vacancies in ${info.name}, ${info.province}. Government, private, ` +
      `remote and internship opportunities gathered from authorised sources, updated continuously.`,
    alternates: { canonical: `/jobs-in-${city}` },
    openGraph: { title: `Jobs in ${info.name}`, url: `/jobs-in-${city}` },
  };
}

export default async function CityJobsPage({ params }: { params: Promise<{ city: string }> }) {
  const { city } = await params;
  const info = CITIES[city];
  if (!info) notFound();

  const result = await fetchJobs({ city, page_size: 20, sort: "newest" });

  return (
    <>
      <section className="border-b border-ink-200 bg-white">
        <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 sm:py-14 lg:px-8">
          <nav aria-label="Breadcrumb" className="mb-4 flex items-center gap-1.5 text-sm text-ink-500">
            <Link href="/" className="hover:text-brand-700">Home</Link>
            <span aria-hidden="true">/</span>
            <Link href="/jobs" className="hover:text-brand-700">Jobs</Link>
            <span aria-hidden="true">/</span>
            <span className="font-medium text-ink-700">{info.name}</span>
          </nav>

          <h1 className="text-2xl font-bold tracking-tight text-ink-900 sm:text-3xl">
            Jobs in {info.name}
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-600 sm:text-base">
            {result.ok && result.data.total > 0
              ? `${pluralize(result.data.total, "opportunity", "opportunities")} currently open in ${info.name}, ${info.province}, collected from authorised sources.`
              : `Openings in ${info.name}, ${info.province} appear here as soon as our sources publish them.`}
          </p>

          <div className="mt-6">
            <SearchBar size="md" defaultCity={info.name} />
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
        {!result.ok ? (
          <ErrorState description={result.error} />
        ) : result.data.items.length === 0 ? (
          <EmptyState
            title={`No jobs listed in ${info.name} right now`}
            description="Try a nearby city or create an alert and we will email you when something opens up."
            action={
              <Link href="/dashboard/alerts" className="inline-flex h-9 items-center rounded-lg bg-brand-700 px-3.5 text-sm font-semibold text-white hover:bg-brand-800">
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
                  href={`/jobs?city=${city}`}
                  className="inline-flex h-11 items-center rounded-lg border border-ink-300 bg-white px-5 text-sm font-semibold text-ink-800 hover:bg-ink-50"
                >
                  See all {pluralize(result.data.total, "job")} in {info.name}
                </Link>
              </div>
            )}
          </>
        )}

        <section className="mt-12 border-t border-ink-200 pt-8">
          <h2 className="text-sm font-semibold text-ink-900">Browse other cities</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(CITIES)
              .filter(([slug]) => slug !== city)
              .map(([slug, other]) => (
                <Link
                  key={slug}
                  href={`/jobs-in-${slug}`}
                  className="rounded-lg border border-ink-200 bg-white px-3 py-1.5 text-sm text-ink-700 transition-colors hover:border-brand-300 hover:text-brand-800"
                >
                  {other.name}
                </Link>
              ))}
          </div>
        </section>
      </div>
    </>
  );
}
