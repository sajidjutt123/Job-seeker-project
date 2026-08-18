"use client";

import { useEffect } from "react";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // Surfaces in the browser console and any client-side error reporter.
    console.error("Unhandled page error:", error);
  }, [error]);

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col items-center justify-center px-4 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-rose-100 text-rose-600">
        <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 8v4.5M12 16h.01" strokeLinecap="round" />
        </svg>
      </div>
      <h1 className="text-xl font-bold text-ink-900">Something went wrong</h1>
      <p className="mt-2 text-sm leading-relaxed text-ink-600">
        We hit an unexpected problem loading this page. Trying again usually helps.
      </p>
      {error.digest && (
        <p className="mt-2 font-mono text-xs text-ink-400">Reference: {error.digest}</p>
      )}
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        <button
          type="button"
          onClick={reset}
          className="inline-flex h-11 items-center rounded-lg bg-brand-700 px-5 text-sm font-semibold text-white transition-colors hover:bg-brand-800"
        >
          Try again
        </button>
        <a
          href="/"
          className="inline-flex h-11 items-center rounded-lg border border-ink-300 bg-white px-5 text-sm font-semibold text-ink-800 transition-colors hover:bg-ink-50"
        >
          Go home
        </a>
      </div>
    </div>
  );
}
