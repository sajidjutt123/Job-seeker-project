import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms",
  description: "Terms of use for RozgarPK.",
  alternates: { canonical: "/terms" },
};

export default function TermsPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6 lg:px-8">
      <h1 className="text-2xl font-bold tracking-tight text-ink-900 sm:text-3xl">Terms of use</h1>
      <p className="mt-2 text-sm text-ink-500">
        Plain-language summary. Operators should have these reviewed by a lawyer before launch.
      </p>

      <div className="mt-8 space-y-6 text-sm leading-relaxed text-ink-700">
        <section>
          <h2 className="text-base font-bold text-ink-900">What this service is</h2>
          <p className="mt-2">
            RozgarPK indexes job advertisements published by third parties. We are not the
            employer, not a recruitment agency, and not a party to any hiring decision. Listings
            belong to whoever published them.
          </p>
        </section>

        <section>
          <h2 className="text-base font-bold text-ink-900">Accuracy</h2>
          <p className="mt-2">
            We normalise and verify listings as best we can, but details such as salary, deadline
            and eligibility come from the source. Always confirm on the original posting before
            acting. If a listing is wrong or expired, use the report button and we will review it.
          </p>
        </section>

        <section>
          <h2 className="text-base font-bold text-ink-900">Acceptable use</h2>
          <ul className="mt-2 list-disc space-y-1.5 pl-5">
            <li>Do not scrape, resell or bulk-copy the index.</li>
            <li>Do not attempt to bypass rate limits or authentication.</li>
            <li>Do not use the platform to post or promote fraudulent opportunities.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-base font-bold text-ink-900">Rights holders</h2>
          <p className="mt-2">
            If you publish a listing indexed here and want it removed, contact us and we will
            remove it and stop collecting from that source.
          </p>
        </section>
      </div>
    </div>
  );
}
