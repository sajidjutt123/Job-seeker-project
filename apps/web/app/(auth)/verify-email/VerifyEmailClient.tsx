"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { api, ApiError } from "@/lib/api";

type State = "verifying" | "success" | "error" | "missing";

export function VerifyEmailClient() {
  const token = useSearchParams().get("token");
  const { refresh } = useAuth();
  const [state, setState] = useState<State>(token ? "verifying" : "missing");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    api
      .post("/auth/verify-email", { token })
      .then(async () => {
        if (cancelled) return;
        setState("success");
        await refresh();
      })
      .catch((err) => {
        if (cancelled) return;
        setState("error");
        setMessage(err instanceof ApiError ? err.message : "This link could not be verified.");
      });

    return () => {
      cancelled = true;
    };
  }, [token, refresh]);

  const content = {
    verifying: { title: "Verifying your email…", body: "This will only take a moment." },
    success: { title: "Email verified", body: "Your account is fully active. You can now receive job alerts." },
    error: { title: "Verification failed", body: message },
    missing: { title: "Invalid link", body: "This verification link is missing its token." },
  }[state];

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-4 py-12 text-center">
      <div className="rounded-xl border border-ink-200 bg-white p-8 shadow-card">
        <h1 className="text-xl font-bold text-ink-900">{content.title}</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-600">{content.body}</p>
        {state !== "verifying" && (
          <Link
            href={state === "success" ? "/dashboard" : "/login"}
            className="mt-6 inline-flex h-11 items-center rounded-lg bg-brand-700 px-5 text-sm font-semibold text-white transition-colors hover:bg-brand-800"
          >
            {state === "success" ? "Go to dashboard" : "Back to sign in"}
          </Link>
        )}
      </div>
    </div>
  );
}
