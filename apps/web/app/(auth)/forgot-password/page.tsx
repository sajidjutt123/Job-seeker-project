"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.post("/auth/forgot-password", { email: email.trim() });
      // The API deliberately does not reveal whether the account exists.
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send the reset link. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-[80vh] max-w-md flex-col justify-center px-4 py-12">
      <div className="rounded-xl border border-ink-200 bg-white p-6 shadow-card sm:p-8">
        {sent ? (
          <>
            <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-emerald-50 text-emerald-700">
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                <rect x="3" y="5" width="18" height="14" rx="2" />
                <path d="m3 7 9 6 9-6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <h1 className="text-xl font-bold text-ink-900">Check your email</h1>
            <p className="mt-2 text-sm leading-relaxed text-ink-600">
              If an account exists for <span className="font-medium text-ink-800">{email}</span>, we
              have sent a password reset link. It expires in 60 minutes.
            </p>
            <Link href="/login" className="mt-6 inline-block text-sm font-semibold text-brand-700 hover:text-brand-800">
              ← Back to sign in
            </Link>
          </>
        ) : (
          <>
            <h1 className="text-xl font-bold tracking-tight text-ink-900">Reset your password</h1>
            <p className="mt-1.5 text-sm text-ink-500">
              Enter your email and we will send you a reset link.
            </p>

            {error && (
              <p role="alert" className="mt-5 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
                {error}
              </p>
            )}

            <form onSubmit={onSubmit} className="mt-6 space-y-4" noValidate>
              <Input
                type="email"
                label="Email address"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
              <Button type="submit" size="lg" fullWidth loading={submitting}>
                Send reset link
              </Button>
            </form>

            <p className="mt-6 text-center text-sm text-ink-600">
              Remembered it?{" "}
              <Link href="/login" className="font-semibold text-brand-700 hover:text-brand-800">Sign in</Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
