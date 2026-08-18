"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

export function ResetPasswordForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (password !== confirm) {
      setError("The two passwords do not match.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.post("/auth/reset-password", { token, password });
      setDone(true);
      setTimeout(() => router.push("/login"), 2200);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reset your password.");
      setSubmitting(false);
    }
  };

  if (!token) {
    return (
      <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-4 text-center">
        <h1 className="text-xl font-bold text-ink-900">Invalid reset link</h1>
        <p className="mt-2 text-sm text-ink-600">
          This link is missing its token. Request a new password reset email.
        </p>
        <Link href="/forgot-password" className="mt-6 text-sm font-semibold text-brand-700 hover:text-brand-800">
          Request a new link
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-[80vh] max-w-md flex-col justify-center px-4 py-12">
      <div className="rounded-xl border border-ink-200 bg-white p-6 shadow-card sm:p-8">
        {done ? (
          <>
            <h1 className="text-xl font-bold text-ink-900">Password updated</h1>
            <p className="mt-2 text-sm text-ink-600">
              Taking you to the sign-in page…
            </p>
          </>
        ) : (
          <>
            <h1 className="text-xl font-bold tracking-tight text-ink-900">Set a new password</h1>
            <p className="mt-1.5 text-sm text-ink-500">
              Choose a password you have not used elsewhere.
            </p>

            {error && (
              <p role="alert" className="mt-5 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
                {error}
              </p>
            )}

            <form onSubmit={onSubmit} className="mt-6 space-y-4" noValidate>
              <Input
                type="password"
                label="New password"
                autoComplete="new-password"
                required
                minLength={8}
                hint="At least 8 characters, with letters and numbers."
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <Input
                type="password"
                label="Confirm new password"
                autoComplete="new-password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
              <Button type="submit" size="lg" fullWidth loading={submitting}>
                Update password
              </Button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
