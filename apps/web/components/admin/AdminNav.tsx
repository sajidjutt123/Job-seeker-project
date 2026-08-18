"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";

const LINKS = [
  { href: "/admin", label: "Overview", exact: true },
  { href: "/admin/jobs", label: "Jobs" },
  { href: "/admin/sources", label: "Sources" },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/reports", label: "Reports" },
  { href: "/admin/analytics", label: "Analytics" },
  { href: "/admin/audit", label: "Audit log" },
];

export function AdminNav({ email }: { email: string }) {
  const pathname = usePathname();

  return (
    <nav aria-label="Admin">
      <div className="mb-4 rounded-xl border border-violet-200 bg-violet-50 p-3.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-violet-700">Admin mode</p>
        <p className="mt-1 truncate text-xs text-violet-900">{email}</p>
      </div>

      <ul className="flex gap-1 overflow-x-auto rounded-xl border border-ink-200 bg-white p-1.5 lg:flex-col lg:overflow-visible">
        {LINKS.map((link) => {
          const active = link.exact ? pathname === link.href : pathname.startsWith(link.href);
          return (
            <li key={link.href} className="shrink-0 lg:w-full">
              <Link
                href={link.href}
                className={cn(
                  "block rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  active ? "bg-ink-900 text-white" : "text-ink-600 hover:bg-ink-100 hover:text-ink-900",
                )}
                aria-current={active ? "page" : undefined}
              >
                {link.label}
              </Link>
            </li>
          );
        })}
        <li className="shrink-0 lg:mt-2 lg:w-full lg:border-t lg:border-ink-100 lg:pt-2">
          <Link
            href="/dashboard"
            className="block rounded-lg px-3 py-2 text-sm font-medium text-ink-500 transition-colors hover:bg-ink-50"
          >
            ← Back to site
          </Link>
        </li>
      </ul>
    </nav>
  );
}
