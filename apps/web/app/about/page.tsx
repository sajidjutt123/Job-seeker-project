import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "About RozgarPK",
  description: "Why RozgarPK exists and how the platform works.",
  alternates: { canonical: "/about" },
};

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6 lg:px-8">
      <h1 className="text-2xl font-bold tracking-tight text-ink-900 sm:text-3xl">About RozgarPK</h1>

      <div className="mt-6 space-y-5 text-sm leading-relaxed text-ink-700 sm:text-base">
        <p>
          Looking for work in Pakistan usually means checking a dozen different places: government
          portals, individual company career pages, feeds, and job boards that each show a slice of
          what is out there. Opportunities get missed simply because nobody can watch everything.
        </p>
        <p>
          RozgarPK collects vacancies from sources that permit aggregation, standardises them so
          they can actually be compared, removes duplicates that appear on several sites, and puts
          them in one searchable place. You can filter by city, category, experience, salary and
          work mode, save what interests you, and set alerts so new matches come to you.
        </p>
        <p>
          We are an aggregator, not an employer or a recruitment agency. We do not accept
          applications, we do not charge candidates, and we never ask for money to apply for a job.
          Every listing links back to whoever published it.
        </p>

        <h2 className="pt-4 text-lg font-bold text-ink-900">How a job reaches you</h2>
        <ol className="list-decimal space-y-2 pl-5">
          <li>A source publishes a new vacancy.</li>
          <li>Our ingestion workers fetch it on a schedule, respecting the source&apos;s rate limits.</li>
          <li>The listing is parsed and normalised — titles, locations, salaries and dates all become consistent.</li>
          <li>It is categorised and checked against existing jobs so duplicates collapse into one entry.</li>
          <li>It is stored, indexed for search, and matched against everyone&apos;s active alerts.</li>
          <li>When the deadline passes or the source withdraws it, it is automatically marked as closed.</li>
        </ol>

        <h2 className="pt-4 text-lg font-bold text-ink-900">Staying safe</h2>
        <p>
          A legitimate employer will never ask you to pay a registration, processing or security
          fee. We filter obvious scam patterns automatically and review reported listings, but
          please use your judgement and{" "}
          <Link href="/jobs" className="font-medium text-brand-700 hover:underline">report anything suspicious</Link>{" "}
          using the button on each job page.
        </p>
      </div>
    </div>
  );
}
