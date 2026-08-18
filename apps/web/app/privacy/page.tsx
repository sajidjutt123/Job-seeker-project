import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy",
  description: "What data RozgarPK collects and why.",
  alternates: { canonical: "/privacy" },
};

export default function PrivacyPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6 lg:px-8">
      <h1 className="text-2xl font-bold tracking-tight text-ink-900 sm:text-3xl">Privacy</h1>
      <p className="mt-2 text-sm text-ink-500">
        Summary of how this platform handles your data. Operators deploying RozgarPK should review
        this against their own legal obligations before launch.
      </p>

      <div className="mt-8 space-y-6 text-sm leading-relaxed text-ink-700">
        <section>
          <h2 className="text-base font-bold text-ink-900">What we store</h2>
          <ul className="mt-2 list-disc space-y-1.5 pl-5">
            <li>Your email address and a hashed password (we never store the password itself).</li>
            <li>Profile details you choose to enter: name, city, education, skills and job preferences.</li>
            <li>Jobs you save and alerts you create.</li>
            <li>Aggregate product analytics: which searches return no results, which categories are popular.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-base font-bold text-ink-900">What we deliberately do not store</h2>
          <ul className="mt-2 list-disc space-y-1.5 pl-5">
            <li>Raw IP addresses — where we need to rate limit, we store a salted hash instead.</li>
            <li>Browsing history outside this site.</li>
            <li>Any data about you on the employer&apos;s side: applications happen on their platform, not ours.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-base font-bold text-ink-900">Email</h2>
          <p className="mt-2">
            We email you only for account actions you triggered (verification, password reset) and
            for job alerts you created. Every alert can be paused or deleted from your dashboard.
          </p>
        </section>

        <section>
          <h2 className="text-base font-bold text-ink-900">Your control</h2>
          <p className="mt-2">
            You can edit or clear your profile at any time, delete saved jobs and alerts, and
            request account deletion. Deleting your account removes your profile, saved jobs and
            alerts.
          </p>
        </section>
      </div>
    </div>
  );
}
