import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { CompanyLogo } from "@/components/jobs/CompanyLogo";
import { JobActions } from "@/components/jobs/JobActions";
import { Badge, JobSourceBadge, MatchScore } from "@/components/ui/Badge";
import {
  deadlineInfo, educationLabel, employmentLabel, experienceLabel,
  formatDate, formatSalary, jobLocationLabel, relativeTime, workModeLabel,
} from "@/lib/format";
import { api } from "@/lib/api";
import { fetchJobDetail, fetchJobs } from "@/lib/server-api";

export const revalidate = 300;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const result = await fetchJobDetail(slug);
  if (!result.ok) {
    return { title: "Job not found", robots: { index: false, follow: false } };
  }

  const job = result.data;
  const location = jobLocationLabel(job);
  const salary = formatSalary(job.salary);
  const description = [
    `${job.title} at ${job.company_name ?? "a company"} in ${location}.`,
    salary ? `Salary ${salary}.` : "",
    employmentLabel(job.employment_type),
    "Apply on the original source via RozgarPK.",
  ]
    .filter(Boolean)
    .join(" ")
    .slice(0, 300);

  return {
    title: `${job.title} at ${job.company_name ?? "Company"} — ${location}`,
    description,
    alternates: { canonical: `/jobs/${job.slug}` },
    openGraph: {
      type: "article",
      title: `${job.title} — ${job.company_name ?? "Company"}`,
      description,
      url: `/jobs/${job.slug}`,
      publishedTime: job.posted_at ?? undefined,
    },
    // Expired jobs stay reachable (for people arriving from old links) but leave the index.
    robots: job.status === "active" ? undefined : { index: false, follow: true },
  };
}

export default async function JobDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const result = await fetchJobDetail(slug);

  if (!result.ok) {
    if (result.status === 404) notFound();
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 text-center">
        <h1 className="text-xl font-bold text-ink-900">This job could not be loaded</h1>
        <p className="mt-2 text-sm text-ink-600">{result.error}</p>
        <Link href="/jobs" className="mt-6 inline-block text-sm font-semibold text-brand-700 hover:text-brand-800">
          ← Back to all jobs
        </Link>
      </div>
    );
  }

  const job = result.data;
  const salary = formatSalary(job.salary);
  const deadline = deadlineInfo(job.deadline);
  const mode = workModeLabel(job);
  const education = educationLabel(job.education_requirement);

  // Structured data straight from the API keeps schema.org output consistent with the DB.
  const structuredData = await api
    .get<Record<string, unknown>>(`/seo/jobs/${encodeURIComponent(slug)}/structured-data`, { revalidate: 3600 })
    .catch(() => null);

  const related = await fetchJobs({
    category: job.category,
    city: job.city ?? undefined,
    page_size: 5,
    sort: "newest",
  });
  const relatedJobs = related.ok ? related.data.items.filter((j) => j.id !== job.id).slice(0, 4) : [];

  return (
    <>
      {structuredData && (
        <script
          type="application/ld+json"
          // Server-generated from our own database — no user input is interpolated.
          dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
        />
      )}

      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <nav aria-label="Breadcrumb" className="mb-5 flex flex-wrap items-center gap-1.5 text-sm text-ink-500">
          <Link href="/" className="hover:text-brand-700">Home</Link>
          <span aria-hidden="true">/</span>
          <Link href="/jobs" className="hover:text-brand-700">Jobs</Link>
          {job.city && (
            <>
              <span aria-hidden="true">/</span>
              <Link href={`/jobs?city=${encodeURIComponent(job.city)}`} className="hover:text-brand-700">
                {job.city}
              </Link>
            </>
          )}
          <span aria-hidden="true">/</span>
          <span className="truncate font-medium text-ink-700">{job.title}</span>
        </nav>

        <div className="grid gap-6 lg:grid-cols-[1fr_20rem] lg:gap-8">
          {/* ------------------------------------------------------ Main -- */}
          <div className="min-w-0">
            <header className="rounded-xl border border-ink-200 bg-white p-5 sm:p-6">
              <div className="flex gap-4">
                <CompanyLogo name={job.company_name} logoUrl={job.company?.logo_url} size="lg" />
                <div className="min-w-0 flex-1">
                  <h1 className="text-xl font-bold leading-tight tracking-tight text-ink-900 sm:text-2xl">
                    {job.title}
                  </h1>
                  <p className="mt-1.5 text-base text-ink-700">
                    {job.company?.website ? (
                      <a
                        href={job.company.website}
                        target="_blank"
                        rel="noopener noreferrer nofollow"
                        className="font-medium hover:text-brand-700 hover:underline"
                      >
                        {job.company_name}
                      </a>
                    ) : (
                      <span className="font-medium">{job.company_name ?? "Company not stated"}</span>
                    )}
                    <span className="text-ink-400"> · </span>
                    {jobLocationLabel(job)}
                  </p>

                  <div className="mt-3 flex flex-wrap items-center gap-1.5">
                    {mode === "Remote" && <Badge tone="success">Remote</Badge>}
                    {mode === "Hybrid" && <Badge tone="info">Hybrid</Badge>}
                    {mode === "On-site" && <Badge tone="neutral">On-site</Badge>}
                    {job.is_government && <Badge tone="violet">Government</Badge>}
                    {job.is_internship && <Badge tone="brand">Internship</Badge>}
                    {job.is_fresh_graduate_friendly && !job.is_internship && (
                      <Badge tone="brand">Fresh graduate friendly</Badge>
                    )}
                    {job.status !== "active" && <Badge tone="danger">Closed</Badge>}
                    {typeof job.match_score === "number" && <MatchScore score={job.match_score} />}
                  </div>
                </div>
              </div>

              <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-3.5 border-t border-ink-100 pt-4 sm:grid-cols-4">
                <Fact label="Salary" value={salary ?? "Not disclosed"} emphasis={Boolean(salary)} />
                <Fact label="Job type" value={employmentLabel(job.employment_type)} />
                <Fact label="Experience" value={experienceLabel(job.experience_level)} />
                <Fact label="Posted" value={relativeTime(job.posted_at)} />
                {education && <Fact label="Education" value={education} />}
                {job.deadline && (
                  <Fact
                    label="Deadline"
                    value={formatDate(job.deadline)}
                    emphasis={deadline?.urgent}
                  />
                )}
                {job.category_label && <Fact label="Category" value={job.category_label} />}
                <Fact label="Applications" value="On original source" />
              </dl>
            </header>

            {/* Mobile action bar */}
            <div className="mt-4 lg:hidden">
              <JobActions job={job} />
            </div>

            {job.skills.length > 0 && (
              <Section title="Skills">
                <ul className="flex flex-wrap gap-1.5">
                  {job.skills.map((skill) => (
                    <li key={skill}>
                      <Link
                        href={`/jobs?skills=${encodeURIComponent(skill)}`}
                        className="inline-block rounded-md bg-ink-100 px-2.5 py-1 text-xs font-medium text-ink-700 transition-colors hover:bg-brand-50 hover:text-brand-800"
                      >
                        {skill}
                      </Link>
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {job.responsibilities.length > 0 && (
              <Section title="Responsibilities">
                <BulletList items={job.responsibilities} />
              </Section>
            )}

            {job.requirements.length > 0 && (
              <Section title="Requirements">
                <BulletList items={job.requirements} />
              </Section>
            )}

            {job.benefits.length > 0 && (
              <Section title="Benefits">
                <BulletList items={job.benefits} />
              </Section>
            )}

            <Section title="Full description">
              {job.description ? (
                <div className="job-prose text-sm text-ink-700">{job.description}</div>
              ) : (
                <p className="text-sm text-ink-500">
                  The source did not provide a full description. Open the original posting for details.
                </p>
              )}
            </Section>

            {/* Source attribution — deliberately prominent */}
            <Section title="Where this job came from">
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm text-ink-600">Listed on</span>
                  {job.source && (
                    <JobSourceBadge name={job.source.label ?? job.source.name} href={job.source.website_url} />
                  )}
                </div>
                {job.other_sources.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm text-ink-600">Also found on</span>
                    {job.other_sources.map((source) => (
                      <JobSourceBadge
                        key={source.id ?? source.name}
                        name={source.label ?? source.name}
                        href={source.website_url}
                        size="sm"
                      />
                    ))}
                  </div>
                )}
                {job.source_url && (
                  <p className="text-sm">
                    <a
                      href={job.source_url}
                      target="_blank"
                      rel="noopener noreferrer nofollow"
                      className="font-medium text-brand-700 hover:text-brand-800 hover:underline"
                    >
                      View the original posting
                    </a>
                  </p>
                )}
                <p className="text-xs leading-relaxed text-ink-500">
                  RozgarPK does not accept applications. Clicking apply takes you to the original
                  publisher, where the employer receives your application directly. Always verify
                  employer details before sharing personal documents, and never pay a fee to apply.
                </p>
              </div>
            </Section>
          </div>

          {/* --------------------------------------------------- Sidebar -- */}
          <aside className="hidden lg:block">
            <div className="sticky top-24 space-y-4">
              <div className="rounded-xl border border-ink-200 bg-white p-4">
                <JobActions job={job} />
              </div>

              {job.company && (
                <div className="rounded-xl border border-ink-200 bg-white p-4">
                  <h2 className="text-sm font-semibold text-ink-900">About the employer</h2>
                  <div className="mt-3 flex items-center gap-3">
                    <CompanyLogo name={job.company.name} logoUrl={job.company.logo_url} size="sm" />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-ink-800">{job.company.name}</p>
                      {job.company.industry && (
                        <p className="truncate text-xs text-ink-500">{job.company.industry}</p>
                      )}
                    </div>
                  </div>
                  <Link
                    href={`/jobs?company=${encodeURIComponent(job.company.name)}`}
                    className="mt-3 inline-block text-xs font-semibold text-brand-700 hover:text-brand-800"
                  >
                    See all jobs from this employer →
                  </Link>
                </div>
              )}

              {relatedJobs.length > 0 && (
                <div className="rounded-xl border border-ink-200 bg-white p-4">
                  <h2 className="text-sm font-semibold text-ink-900">Similar jobs</h2>
                  <ul className="mt-3 space-y-3">
                    {relatedJobs.map((related) => (
                      <li key={related.id}>
                        <Link href={`/jobs/${related.slug}`} className="group block">
                          <p className="line-clamp-2 text-sm font-medium leading-snug text-ink-800 group-hover:text-brand-700">
                            {related.title}
                          </p>
                          <p className="mt-0.5 truncate text-xs text-ink-500">
                            {related.company_name ?? "Company not stated"} · {jobLocationLabel(related)}
                          </p>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </aside>
        </div>
      </div>
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-4 rounded-xl border border-ink-200 bg-white p-5 sm:p-6">
      <h2 className="mb-3 text-base font-bold text-ink-900">{title}</h2>
      {children}
    </section>
  );
}

function BulletList({ items }: { items: string[] }) {
  return (
    <ul className="space-y-2">
      {items.map((item, index) => (
        <li key={index} className="flex gap-2.5 text-sm leading-relaxed text-ink-700">
          <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-brand-600" aria-hidden="true" />
          {item}
        </li>
      ))}
    </ul>
  );
}

function Fact({ label, value, emphasis }: { label: string; value: string; emphasis?: boolean }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</dt>
      <dd className={`mt-0.5 text-sm ${emphasis ? "font-semibold text-ink-900" : "text-ink-700"}`}>
        {value}
      </dd>
    </div>
  );
}
