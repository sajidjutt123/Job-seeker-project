import Link from "next/link";

const COLUMNS = [
  {
    title: "Find work",
    links: [
      { href: "/jobs", label: "All jobs" },
      { href: "/remote-jobs", label: "Remote jobs" },
      { href: "/government-jobs", label: "Government jobs" },
      { href: "/internships", label: "Internships" },
      { href: "/jobs?fresh_graduate=true", label: "Fresh graduate jobs" },
    ],
  },
  {
    title: "Popular cities",
    links: [
      { href: "/jobs-in-karachi", label: "Jobs in Karachi" },
      { href: "/jobs-in-lahore", label: "Jobs in Lahore" },
      { href: "/jobs-in-islamabad", label: "Jobs in Islamabad" },
      { href: "/jobs-in-rawalpindi", label: "Jobs in Rawalpindi" },
      { href: "/jobs-in-faisalabad", label: "Jobs in Faisalabad" },
    ],
  },
  {
    title: "Account",
    links: [
      { href: "/dashboard", label: "Dashboard" },
      { href: "/dashboard/saved", label: "Saved jobs" },
      { href: "/dashboard/alerts", label: "Job alerts" },
      { href: "/dashboard/profile", label: "Your profile" },
    ],
  },
  {
    title: "About",
    links: [
      { href: "/sources", label: "Where jobs come from" },
      { href: "/about", label: "About RozgarPK" },
      { href: "/privacy", label: "Privacy" },
      { href: "/terms", label: "Terms" },
    ],
  },
];

export function Footer() {
  return (
    <footer className="mt-auto border-t border-ink-200 bg-white">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid grid-cols-2 gap-8 md:grid-cols-5">
          <div className="col-span-2 md:col-span-1">
            <Link href="/" className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-700" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="7" width="18" height="13" rx="2" />
                  <path d="M8.5 7V5.5A1.5 1.5 0 0110 4h4a1.5 1.5 0 011.5 1.5V7" />
                  <path d="M3 12h18" />
                </svg>
              </span>
              <span className="text-base font-bold tracking-tight text-ink-900">
                Rozgar<span className="text-brand-700">PK</span>
              </span>
            </Link>
            <p className="mt-3 max-w-xs text-sm leading-relaxed text-ink-500">
              Opportunities from across Pakistan, gathered from authorised sources into one
              searchable place. You always apply on the original site.
            </p>
          </div>

          {COLUMNS.map((column) => (
            <nav key={column.title} aria-label={column.title}>
              <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-900">{column.title}</h2>
              <ul className="mt-3 space-y-2">
                {column.links.map((link) => (
                  <li key={link.href}>
                    <Link href={link.href} className="text-sm text-ink-500 transition-colors hover:text-brand-700">
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className="mt-10 flex flex-col gap-3 border-t border-ink-200 pt-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-ink-500">
            © {new Date().getFullYear()} RozgarPK. Listings belong to their original publishers.
          </p>
          <p className="text-xs text-ink-400">
            We aggregate only from sources that permit it, and always link back to the original posting.
          </p>
        </div>
      </div>
    </footer>
  );
}
