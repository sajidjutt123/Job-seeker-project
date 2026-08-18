import type { Metadata } from "next";
import { Suspense } from "react";

import { SearchBar } from "@/components/search/SearchBar";
import { SearchResults } from "@/components/search/SearchResults";
import { JobListSkeleton } from "@/components/ui/states";
import { fetchFilterOptions, fetchJobs, type SearchParams } from "@/lib/server-api";

type RawParams = Record<string, string | string[] | undefined>;

export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<RawParams>;
}): Promise<Metadata> {
  const params = await searchParams;
  const q = single(params.q);
  const city = single(params.city);

  const parts = ["Jobs"];
  if (q) parts.push(`for "${q}"`);
  if (city) parts.push(`in ${titleCase(city)}`);
  const title = parts.join(" ");

  return {
    title,
    description: `Browse ${q ? `${q} ` : ""}jobs${city ? ` in ${titleCase(city)}` : " across Pakistan"} from multiple authorised sources. Apply directly on the original posting.`,
    // Filtered permutations must not be indexed — only clean landing pages are.
    robots: Object.keys(params).length > 0 ? { index: false, follow: true } : undefined,
    alternates: { canonical: "/jobs" },
  };
}

export default async function JobsPage({ searchParams }: { searchParams: Promise<RawParams> }) {
  const raw = await searchParams;
  const params = normalize(raw);

  const [result, options] = await Promise.all([
    fetchJobs({ ...params, facets: false }),
    fetchFilterOptions(),
  ]);

  return (
    <>
      <div className="border-b border-ink-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6 lg:px-8">
          <SearchBar
            size="md"
            defaultQuery={single(raw.q) ?? ""}
            defaultCity={single(raw.city) ?? ""}
          />
        </div>
      </div>

      <Suspense fallback={<SearchLoading />}>
        <SearchResults
          result={result.ok ? result.data : null}
          error={result.ok ? undefined : result.error}
          options={options.ok ? options.data : null}
          heading={buildHeading(raw)}
        />
      </Suspense>
    </>
  );
}

function SearchLoading() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <JobListSkeleton count={6} />
    </div>
  );
}

/* ------------------------------------------------------------------ utils */

function single(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) return value[0];
  return value;
}

function many(value: string | string[] | undefined): string[] | undefined {
  if (value === undefined) return undefined;
  return Array.isArray(value) ? value : [value];
}

function bool(value: string | string[] | undefined): boolean | undefined {
  const v = single(value);
  if (v === "true") return true;
  if (v === "false") return false;
  return undefined;
}

function num(value: string | string[] | undefined): number | undefined {
  const v = single(value);
  if (!v) return undefined;
  const parsed = Number.parseInt(v, 10);
  return Number.isFinite(parsed) ? parsed : undefined;
}

/** Whitelist + coerce query params; never pass unvalidated user input to the API. */
function normalize(raw: RawParams): SearchParams {
  return {
    q: single(raw.q),
    city: single(raw.city),
    province: single(raw.province),
    category: many(raw.category),
    employment_type: many(raw.employment_type),
    experience: many(raw.experience),
    education: single(raw.education),
    company: single(raw.company),
    skills: many(raw.skills),
    remote: bool(raw.remote),
    government: bool(raw.government),
    internship: bool(raw.internship),
    fresh_graduate: bool(raw.fresh_graduate),
    salary_min: num(raw.salary_min),
    salary_max: num(raw.salary_max),
    posted_within_days: num(raw.posted_within_days),
    sort: single(raw.sort),
    page: num(raw.page) ?? 1,
    page_size: 20,
  };
}

function buildHeading(raw: RawParams): string {
  const q = single(raw.q);
  const city = single(raw.city);
  if (q && city) return `${q} jobs in ${titleCase(city)}`;
  if (q) return `${q} jobs`;
  if (city) return `Jobs in ${titleCase(city)}`;
  if (bool(raw.remote)) return "Remote jobs";
  if (bool(raw.government)) return "Government jobs";
  if (bool(raw.internship)) return "Internships";
  return "All jobs";
}

function titleCase(value: string): string {
  return value
    .split(/[\s-]+/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
