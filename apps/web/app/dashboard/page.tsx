import Link from "next/link";

import { JobCard } from "@/components/jobs/JobCard";
import { EmptyState } from "@/components/ui/states";
import { fetchMe, fetchRecommended } from "@/lib/server-api";

export default async function DashboardPage() {
  const [me, recommended] = await Promise.all([fetchMe(), fetchRecommended(6)]);
  if (!me) return null; // layout already redirected

  const completion = me.profile?.profile_completion ?? 0;
  const nextSteps = me.profile?.next_steps ?? [];
  const jobs = recommended.ok ? recommended.data : [];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-bold tracking-tight text-ink-900 sm:text-2xl">
          {me.profile?.full_name ? `Welcome back, ${me.profile.full_name.split(" ")[0]}` : "Your dashboard"}
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          Recommendations improve as you complete your profile and save jobs.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Saved jobs" value={me.stats.saved_jobs ?? 0} href="/dashboard/saved" />
        <StatCard label="Active alerts" value={me.stats.active_alerts ?? 0} href="/dashboard/alerts" />
        <StatCard label="Profile complete" value={`${completion}%`} href="/dashboard/profile" />
      </div>

      {completion < 100 && (
        <section className="rounded-xl border border-brand-200 bg-brand-50/60 p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <h2 className="text-sm font-bold text-brand-900">
                Complete your profile to improve job recommendations
              </h2>
              <p className="mt-1 text-sm text-brand-800">
                Your profile is {completion}% complete.
              </p>
              {nextSteps.length > 0 && (
                <ul className="mt-3 space-y-1">
                  {nextSteps.map((step) => (
                    <li key={step} className="flex items-center gap-2 text-sm text-brand-900">
                      <span className="h-1.5 w-1.5 rounded-full bg-brand-600" aria-hidden="true" />
                      {step}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <Link
              href="/dashboard/profile"
              className="inline-flex h-10 shrink-0 items-center rounded-lg bg-brand-700 px-4 text-sm font-semibold text-white transition-colors hover:bg-brand-800"
            >
              Update profile
            </Link>
          </div>

          <div className="mt-4 h-2 overflow-hidden rounded-full bg-brand-200" role="progressbar"
               aria-valuenow={completion} aria-valuemin={0} aria-valuemax={100}
               aria-label="Profile completion">
            <div className="h-full rounded-full bg-brand-600 transition-all" style={{ width: `${completion}%` }} />
          </div>
        </section>
      )}

      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold text-ink-900">Recommended for you</h2>
          <Link href="/jobs" className="text-sm font-semibold text-brand-700 hover:text-brand-800">
            Browse all jobs
          </Link>
        </div>

        {jobs.length === 0 ? (
          <EmptyState
            title="No recommendations yet"
            description="Add your skills and preferred locations, and we will start matching roles to your profile."
            action={
              <Link
                href="/dashboard/profile"
                className="inline-flex h-9 items-center rounded-lg bg-brand-700 px-3.5 text-sm font-semibold text-white hover:bg-brand-800"
              >
                Complete your profile
              </Link>
            }
          />
        ) : (
          <div className="space-y-3">
            {jobs.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function StatCard({ label, value, href }: { label: string; value: number | string; href: string }) {
  return (
    <Link
      href={href}
      className="rounded-xl border border-ink-200 bg-white p-5 transition-all hover:border-brand-300 hover:shadow-card-hover"
    >
      <p className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</p>
      <p className="mt-2 text-2xl font-bold tracking-tight text-ink-900">{value}</p>
    </Link>
  );
}
