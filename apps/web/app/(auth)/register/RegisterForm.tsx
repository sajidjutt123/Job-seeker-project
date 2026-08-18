"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState, type FormEvent } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { GoogleButton } from "@/components/auth/GoogleButton";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";

export function RegisterForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { register } = useAuth();
  const next = params.get("next") ?? "/dashboard/profile";

  const [form, setForm] = useState({ email: "", password: "", full_name: "", city: "" });
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const strength = useMemo(() => passwordStrength(form.password), [form.password]);

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [key]: e.target.value }));

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setFieldErrors({});
    try {
      await register({
        email: form.email.trim(),
        password: form.password,
        full_name: form.full_name.trim() || undefined,
        city: form.city.trim() || undefined,
      });
      router.replace(next);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setFieldErrors(err.fieldErrors);
      } else {
        setError("Could not create your account. Please try again.");
      }
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-[80vh] max-w-md flex-col justify-center px-4 py-12">
      <div className="rounded-xl border border-ink-200 bg-white p-6 shadow-card sm:p-8">
        <h1 className="text-xl font-bold tracking-tight text-ink-900">Create your account</h1>
        <p className="mt-1.5 text-sm text-ink-500">
          Free forever. Save jobs, set alerts and get roles matched to your skills.
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
            value={form.email}
            error={fieldErrors.email}
            onChange={set("email")}
            placeholder="you@example.com"
          />

          <div>
            <Input
              type={showPassword ? "text" : "password"}
              label="Password"
              autoComplete="new-password"
              required
              minLength={8}
              value={form.password}
              error={fieldErrors.password}
              hint="At least 8 characters, with letters and numbers."
              onChange={set("password")}
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
            {form.password.length > 0 && (
              <div className="mt-2 flex items-center gap-2" aria-live="polite">
                <div className="flex h-1 flex-1 gap-1">
                  {[0, 1, 2, 3].map((i) => (
                    <div
                      key={i}
                      className={cn(
                        "h-full flex-1 rounded-full transition-colors",
                        i < strength.score ? strength.color : "bg-ink-200",
                      )}
                    />
                  ))}
                </div>
                <span className="text-xs text-ink-500">{strength.label}</span>
              </div>
            )}
          </div>

          <Input
            label="Full name"
            autoComplete="name"
            value={form.full_name}
            error={fieldErrors.full_name}
            onChange={set("full_name")}
            placeholder="Optional"
          />
          <Input
            label="City"
            autoComplete="address-level2"
            value={form.city}
            error={fieldErrors.city}
            onChange={set("city")}
            placeholder="Optional — helps us match nearby jobs"
          />

          <Button type="submit" size="lg" fullWidth loading={submitting}>
            Create account
          </Button>

          <p className="text-center text-xs leading-relaxed text-ink-500">
            By creating an account you agree to our{" "}
            <Link href="/terms" className="text-brand-700 hover:underline">Terms</Link> and{" "}
            <Link href="/privacy" className="text-brand-700 hover:underline">Privacy Policy</Link>.
          </p>
        </form>

        <GoogleButton className="mt-2" label="Sign up with Google" />

        <p className="mt-6 text-center text-sm text-ink-600">
          Already have an account?{" "}
          <Link href="/login" className="font-semibold text-brand-700 hover:text-brand-800">Sign in</Link>
        </p>
      </div>
    </div>
  );
}

function passwordStrength(password: string): { score: number; label: string; color: string } {
  if (!password) return { score: 0, label: "", color: "bg-ink-200" };
  let score = 0;
  if (password.length >= 8) score += 1;
  if (password.length >= 12) score += 1;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score += 1;
  if (/\d/.test(password) && /[^A-Za-z0-9]/.test(password)) score += 1;

  const map = [
    { label: "Too short", color: "bg-rose-500" },
    { label: "Weak", color: "bg-rose-500" },
    { label: "Fair", color: "bg-amber-500" },
    { label: "Good", color: "bg-emerald-500" },
    { label: "Strong", color: "bg-emerald-600" },
  ];
  return { score, ...map[score] };
}
