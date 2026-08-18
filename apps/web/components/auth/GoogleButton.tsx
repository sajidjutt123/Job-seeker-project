"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { cn } from "@/lib/cn";

/**
 * Renders only when Google OAuth is actually configured on the backend, so users never see a
 * button that cannot work.
 */
export function GoogleButton({ className, label = "Continue with Google" }: { className?: string; label?: string }) {
  const [enabled, setEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    api
      .get<{ enabled: boolean }>("/auth/google/config", { revalidate: 3600 })
      .then((res) => setEnabled(res.enabled))
      .catch(() => setEnabled(false));
  }, []);

  if (enabled !== true) return null;

  return (
    <div className={className}>
      <div className="relative my-1">
        <div className="absolute inset-0 flex items-center" aria-hidden="true">
          <div className="w-full border-t border-ink-200" />
        </div>
        <div className="relative flex justify-center">
          <span className="bg-white px-3 text-xs text-ink-500">or</span>
        </div>
      </div>

      <a
        href="/api/v1/auth/google/start"
        className={cn(
          "mt-3 inline-flex h-11 w-full items-center justify-center gap-2.5 rounded-lg border border-ink-300",
          "bg-white text-sm font-semibold text-ink-800 transition-colors hover:bg-ink-50",
        )}
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.65l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0012 23z" />
          <path fill="#FBBC05" d="M5.84 14.11a6.6 6.6 0 010-4.22V7.05H2.18a11 11 0 000 9.9l3.66-2.84z" />
          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1a11 11 0 00-9.82 6.05l3.66 2.84c.87-2.6 3.3-4.51 6.16-4.51z" />
        </svg>
        {label}
      </a>
    </div>
  );
}
