import type { Metadata } from "next";
import Link from "next/link";

import { ErrorState } from "@/components/ui/states";
import { pluralize } from "@/lib/format";
import { fetchPublicSources } from "@/lib/server-api";

export const revalidate = 900;

export const metadata: Metadata = {
  title: "Where our jobs come from",
  description:
    "RozgarPK aggregates only from sources that permit it — official APIs, employer career " +
    "boards and published feeds. Every listing links back to its original publisher.",
  alternates: { canonical: "/sources" },
};

const TYPE_LABELS: Record<string, string> = {
  api: "Official API",
  rss: "RSS / Atom feed",
  partner_feed: "Partner feed",
  career_page: "Employer career board",
  government_portal: "Government portal",
  employer_direct: "Posted directly by employer",
  seed: "Development sample",
};

const PRINCIPLES = [
  {
    title: "Only sources that permit aggregation",
    body: "We ingest from documented public APIs, employer career boards and RSS feeds that publishers have made available for syndication. If a site's terms do not allow automated access, we do not collect from it.",
  },
  {
    title: "No bypassing protections",
    body: "We never circumvent logins, CAPTCHAs, paywalls, rate limits or anti-bot measures. Our crawler identifies itself and backs off when a source asks it to.",
  },
  {
    title: "Attribution is never hidden",
    body: "Every job card and detail page names the source it came from and links to the original posting. We do not present other publishers' listings as our own.",
  },
  {
    title: "Applications go directly to the employer",
    body: "RozgarPK does not accept applications or charge candidates. The apply button always takes you to the original publisher.",
  },
];

export default async function SourcesPage() {
  const result = await fetchPublicSources();

  return (
    <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6 sm:py-14 lg:px-8">
      <nav aria-label="Breadcrumb" className="mb-4 flex items-center gap-1.5 text-sm text-ink-500">
        <Link href="/" className="hover:text-brand-700">Home</Link>
        <span aria-hidden="true">/</span>
        <span className="font-medium text-ink-700">Sources</span>
      </nav>

      <h1 className="text-2xl font-bold tracking-tight text-ink-900 sm:text-3xl">
        Where our jobs come from
      </h1>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-ink-600 sm:text-base">
        RozgarPK is an aggregator. We do not write job adverts — we collect them from sources that
        allow it, clean them up so they are comparable, remove duplicates, and send you to the
        original posting to apply.
      </p>

      <section className="mt-10">
        <h2 className="text-lg font-bold text-ink-900">Active sources</h2>
        {!result.ok ? (
          <ErrorState className="mt-4" description={result.error} />
        ) : result.data.length === 0 ? (
          <p className="mt-4 rounded-xl border border-dashed border-ink-300 bg-white p-6 text-sm text-ink-500">
            No sources are currently enabled on this deployment. An administrator can enable
            connectors from the admin panel.
          </p>
        ) : (
          <ul className="mt-4 divide-y divide-ink-200 overflow-hidden rounded-xl border border-ink-200 bg-white">
            {result.data.map((source) => (
              <li key={source.slug} className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-ink-900">{source.name}</p>
                  <p className="mt-0.5 text-xs text-ink-500">
                    {TYPE_LABELS[source.type] ?? source.type}
                    {source.website_url && (
                      <>
                        {" · "}
                        <a
                          href={source.website_url}
                          target="_blank"
                          rel="noopener noreferrer nofollow"
                          className="text-brand-700 hover:underline"
                        >
                          Visit source
                        </a>
                      </>
                    )}
                  </p>
                </div>
                <span className="shrink-0 rounded-md bg-ink-100 px-2 py-1 text-xs font-medium text-ink-700">
                  {pluralize(source.active_jobs, "active job")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-10">
        <h2 className="text-lg font-bold text-ink-900">How we handle sources</h2>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2">
          {PRINCIPLES.map((principle) => (
            <div key={principle.title} className="rounded-xl border border-ink-200 bg-white p-5">
              <dt className="text-sm font-semibold text-ink-900">{principle.title}</dt>
              <dd className="mt-1.5 text-sm leading-relaxed text-ink-600">{principle.body}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="mt-10 rounded-xl border border-brand-200 bg-brand-50/60 p-6">
        <h2 className="text-base font-bold text-brand-900">Are you a publisher or employer?</h2>
        <p className="mt-2 text-sm leading-relaxed text-brand-800">
          If you publish vacancies and would like them included — or if you would like your
          listings removed — get in touch and we will action it. We honour removal requests from
          the rights holder without argument.
        </p>
      </section>
    </div>
  );
}
