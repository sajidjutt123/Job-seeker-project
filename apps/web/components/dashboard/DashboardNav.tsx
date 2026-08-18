"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { api } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/lib/cn";

const LINKS = [
  { href: "/dashboard", label: "Overview", exact: true },
  { href: "/dashboard/saved", label: "Saved jobs", badge: "saved" as const },
  { href: "/dashboard/alerts", label: "Job alerts", badge: "alerts" as const },
  { href: "/dashboard/profile", label: "Profile" },
  { href: "/dashboard/notifications", label: "Notifications" },
];

export function DashboardNav({
  email, emailVerified, isAdmin, savedCount, alertCount,
}: {
  email: string;
  emailVerified: boolean;
  isAdmin: boolean;
  savedCount: number;
  alertCount: number;
}) {
  const pathname = usePathname();
  const toast = useToast();
  const [resending, setResending] = useState(false);

  const resend = async () => {
    setResending(true);
    try {
      await api.post("/auth/resend-verification", {});
      toast.success("Verification link sent. Check your inbox.");
    } catch {
      toast.error("Could not send the link right now. Please try again.");
    } finally {
      setResending(false);
    }
  };

  return (
    <nav aria-label="Dashboard">
      <div className="mb-4 rounded-xl border border-ink-200 bg-white p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-ink-500">Signed in as</p>
        <p className="mt-1 truncate text-sm font-semibold text-ink-900">{email}</p>
      </div>

      {!emailVerified && (
        <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-3.5">
          <p className="text-xs font-semibold text-amber-900">Verify your email</p>
          <p className="mt-1 text-xs leading-relaxed text-amber-800">
            Job alerts are only delivered to verified addresses.
          </p>
          <button
            type="button"
            onClick={resend}
            disabled={resending}
            className="mt-2 text-xs font-semibold text-amber-900 underline underline-offset-2 disabled:opacity-60"
          >
            {resending ? "Sending…" : "Resend verification link"}
          </button>
        </div>
      )}

      <ul className="flex gap-1 overflow-x-auto rounded-xl border border-ink-200 bg-white p-1.5 lg:flex-col lg:overflow-visible">
        {LINKS.map((link) => {
          const active = link.exact ? pathname === link.href : pathname.startsWith(link.href);
          const count = link.badge === "saved" ? savedCount : link.badge === "alerts" ? alertCount : null;
          return (
            <li key={link.href} className="shrink-0 lg:w-full">
              <Link
                href={link.href}
                className={cn(
                  "flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  active ? "bg-brand-50 text-brand-800" : "text-ink-600 hover:bg-ink-50 hover:text-ink-900",
                )}
                aria-current={active ? "page" : undefined}
              >
                {link.label}
                {count !== null && count > 0 && (
                  <span className="rounded-md bg-ink-100 px-1.5 py-0.5 text-[11px] font-semibold text-ink-600">
                    {count}
                  </span>
                )}
              </Link>
            </li>
          );
        })}
        {isAdmin && (
          <li className="shrink-0 lg:mt-2 lg:w-full lg:border-t lg:border-ink-100 lg:pt-2">
            <Link
              href="/admin"
              className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-violet-700 transition-colors hover:bg-violet-50"
            >
              Admin dashboard
            </Link>
          </li>
        )}
      </ul>
    </nav>
  );
}
