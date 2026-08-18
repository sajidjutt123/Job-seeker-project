"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { GoogleButton } from "@/components/auth/GoogleButton";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ApiError } from "@/lib/api";

const ERROR_MESSAGES: Record<string, string> = {
  google_failed: "Google sign-in did not complete. Please try again or use your password.",
  email_unverified: "That Google account does not have a verified email address.",
};

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { login, user } = useAuth();

  const next = params.get("next") ?? "/dashboard";
  const urlError = params.get("error");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(urlError ? ERROR_MESSAGES[urlError] ?? null : null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (user) router.replace(next);
  }, [user, next, router]);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setFieldErrors({});
    try {
      await login(email.trim(), password);
      router.replace(next);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setFieldErrors(err.fieldErrors);
      } else {
        setError("Could not sign you in. Please try again.");
      }
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-[80vh] max-w-md flex-col justify-center px-4 py-12">
      <div className="rounded-xl border border-ink-200 bg-white p-6 shadow-card sm:p-8">
        <h1 className="text-xl font-bold tracking-tight text-ink-900">Welcome back</h1>
        <p className="mt-1.5 text-sm text-ink-500">
          Sign in to save jobs, set alerts and see roles matched to your profile.
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
            error={fieldErrors.email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
          <Input
            type={showPassword ? "text" : "password"}
            label="Password"
            autoComplete="current-password"
            required
            value={password}
            error={fieldErrors.password}
            onChange={(e) => setPassword(e.target.value)}
            rightSlot={
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="rounded p-1.5 text-xs font-medium text-ink-500 hover:text-ink-800"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            }
          />

          <div className="flex justify-end">
            <Link href="/forgot-password" className="text-sm font-medium text-brand-700 hover:text-brand-800">
              Forgot password?
            </Link>
          </div>

          <Button type="submit" size="lg" fullWidth loading={submitting}>
            Sign in
          </Button>
        </form>

        <GoogleButton className="mt-4" label="Continue with Google" />

        <p className="mt-6 text-center text-sm text-ink-600">
          New to RozgarPK?{" "}
          <Link href={`/register${next !== "/dashboard" ? `?next=${encodeURIComponent(next)}` : ""}`}
                className="font-semibold text-brand-700 hover:text-brand-800">
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}
