import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col items-center justify-center px-4 text-center">
      <p className="text-5xl font-bold tracking-tight text-brand-700">404</p>
      <h1 className="mt-4 text-xl font-bold text-ink-900">We could not find that page</h1>
      <p className="mt-2 text-sm leading-relaxed text-ink-600">
        The link may be broken, or the job may have been removed by its source.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        <Link
          href="/jobs"
          className="inline-flex h-11 items-center rounded-lg bg-brand-700 px-5 text-sm font-semibold text-white transition-colors hover:bg-brand-800"
        >
          Browse all jobs
        </Link>
        <Link
          href="/"
          className="inline-flex h-11 items-center rounded-lg border border-ink-300 bg-white px-5 text-sm font-semibold text-ink-800 transition-colors hover:bg-ink-50"
        >
          Go home
        </Link>
      </div>
    </div>
  );
}
