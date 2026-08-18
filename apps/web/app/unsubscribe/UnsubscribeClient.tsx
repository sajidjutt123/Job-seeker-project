"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";

type State = "working" | "done" | "invalid" | "error";

/**
 * Landing page for the unsubscribe link in alert emails.
 *
 * Runs without a session on purpose — someone who wants the email to stop should not have to
 * remember a password first. The signed token in the URL is what authorises the change.
 */
export function UnsubscribeClient() {
  const params = useSearchParams();
  const alertId = params.get("alert");
  const token = params.get("token");

  const [state, setState] = useState<State>(alertId && token ? "working" : "invalid");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!alertId || !token) return;
    let cancelled = false;

    api
      .post<{ message: string }>("/alerts/unsubscribe", { alert: alertId, token })
      .then((response) => {
        if (cancelled) return;
        setMessage(response.message);
        setState("done");
      })
      .catch((error) => {
        if (cancelled) return;
        if (error instanceof ApiError && error.isNotFound) {
          setState("invalid");
        } else {
          setMessage(error instanceof ApiError ? error.message : "Please try again.");
          setState("error");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [alertId, token]);

  const content = {
    working: {
      title: "Updating your preferences…",
      body: "One moment.",
    },
    done: {
      title: "Unsubscribed",
      body: message || "You will no longer receive emails for this alert.",
    },
    invalid: {
      title: "This link is not valid",
      body:
        "It may have been altered, or the alert may already have been deleted. " +
        "You can manage every alert from your dashboard.",
    },
    error: {
      title: "Something went wrong",
      body: message || "We could not update your preferences. Please try again.",
    },
  }[state];

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-4 py-12">
      <div className="rounded-xl border border-ink-200 bg-white p-8 text-center shadow-card">
        {state === "done" && (
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 text-emerald-700">
            <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
              <path d="m5 13 4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        )}

        <h1 className="text-xl font-bold text-ink-900">{content.title}</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-600">{content.body}</p>

        {state !== "working" && (
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            <Link
              href="/dashboard/alerts"
              className="inline-flex h-11 items-center rounded-lg bg-brand-700 px-5 text-sm font-semibold text-white transition-colors hover:bg-brand-800"
            >
              Manage your alerts
            </Link>
            <Link
              href="/jobs"
              className="inline-flex h-11 items-center rounded-lg border border-ink-300 bg-white px-5 text-sm font-semibold text-ink-800 transition-colors hover:bg-ink-50"
            >
              Browse jobs
            </Link>
          </div>
        )}

        {state === "done" && (
          <p className="mt-5 text-xs text-ink-500">
            Your other alerts are unaffected. You can re-enable this one any time from your
            dashboard.
          </p>
        )}
      </div>
    </div>
  );
}
