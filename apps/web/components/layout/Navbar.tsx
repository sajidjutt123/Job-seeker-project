"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Button, ButtonLink } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { initials } from "@/lib/format";

const NAV_LINKS = [
  { href: "/jobs", label: "Find jobs" },
  { href: "/remote-jobs", label: "Remote" },
  { href: "/government-jobs", label: "Government" },
  { href: "/internships", label: "Internships" },
  { href: "/sources", label: "Sources" },
];

export function Navbar() {
  const pathname = usePathname();
  const { user, loading, logout, isAdmin } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMobileOpen(false);
    setMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <header className="sticky top-0 z-40 border-b border-ink-200 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/85">
      <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8" aria-label="Main">
        <div className="flex items-center gap-6 lg:gap-8">
          <Link href="/" className="flex shrink-0 items-center gap-2" aria-label="RozgarPK home">
            <Logo />
            <span className="text-lg font-bold tracking-tight text-ink-900">
              Rozgar<span className="text-brand-700">PK</span>
            </span>
          </Link>

          <ul className="hidden items-center gap-1 lg:flex">
            {NAV_LINKS.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className={cn(
                    "rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive(link.href)
                      ? "bg-brand-50 text-brand-800"
                      : "text-ink-600 hover:bg-ink-100 hover:text-ink-900",
                  )}
                  aria-current={isActive(link.href) ? "page" : undefined}
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        <div className="flex items-center gap-2">
          {loading ? (
            <div className="h-9 w-24 animate-pulse rounded-lg bg-ink-100" />
          ) : user ? (
            <div className="relative" ref={menuRef}>
              <button
                type="button"
                onClick={() => setMenuOpen((v) => !v)}
                className="flex items-center gap-2 rounded-lg border border-ink-200 py-1.5 pl-1.5 pr-2.5 transition-colors hover:bg-ink-50"
                aria-expanded={menuOpen}
                aria-haspopup="menu"
              >
                <span className="flex h-7 w-7 items-center justify-center rounded-md bg-brand-100 text-xs font-semibold text-brand-800">
                  {initials(user.email)}
                </span>
                <svg className="h-3.5 w-3.5 text-ink-400" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
                </svg>
              </button>

              {menuOpen && (
                <div
                  role="menu"
                  className="absolute right-0 mt-2 w-60 origin-top-right animate-[slide-up_0.16s_ease-out] rounded-xl border border-ink-200 bg-white py-1.5 shadow-panel"
                >
                  <div className="border-b border-ink-100 px-3.5 pb-2.5 pt-1.5">
                    <p className="truncate text-sm font-medium text-ink-900">{user.email}</p>
                    {!user.email_verified && (
                      <p className="mt-0.5 text-xs text-amber-700">Email not verified</p>
                    )}
                  </div>
                  <MenuLink href="/dashboard">Dashboard</MenuLink>
                  <MenuLink href="/dashboard/saved">Saved jobs</MenuLink>
                  <MenuLink href="/dashboard/alerts">Job alerts</MenuLink>
                  <MenuLink href="/dashboard/profile">Profile</MenuLink>
                  {isAdmin && (
                    <>
                      <div className="my-1.5 border-t border-ink-100" />
                      <MenuLink href="/admin">Admin dashboard</MenuLink>
                    </>
                  )}
                  <div className="my-1.5 border-t border-ink-100" />
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => void logout()}
                    className="block w-full px-3.5 py-2 text-left text-sm text-ink-700 transition-colors hover:bg-ink-50"
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>
          ) : (
            <>
              <ButtonLink href="/login" variant="ghost" size="sm" className="hidden sm:inline-flex">
                Sign in
              </ButtonLink>
              <ButtonLink href="/register" size="sm">Create account</ButtonLink>
            </>
          )}

          <Button
            variant="ghost"
            size="sm"
            className="px-2 lg:hidden"
            onClick={() => setMobileOpen((v) => !v)}
            aria-expanded={mobileOpen}
            aria-label="Toggle navigation menu"
          >
            {mobileOpen ? (
              <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
              </svg>
            ) : (
              <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M3 5.75A.75.75 0 013.75 5h12.5a.75.75 0 010 1.5H3.75A.75.75 0 013 5.75zm0 4.5a.75.75 0 01.75-.75h12.5a.75.75 0 010 1.5H3.75a.75.75 0 01-.75-.75zm0 4.5a.75.75 0 01.75-.75h12.5a.75.75 0 010 1.5H3.75a.75.75 0 01-.75-.75z" clipRule="evenodd" />
              </svg>
            )}
          </Button>
        </div>
      </nav>

      {mobileOpen && (
        <div className="border-t border-ink-200 bg-white lg:hidden">
          <ul className="space-y-0.5 px-4 py-3">
            {NAV_LINKS.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className={cn(
                    "block rounded-md px-3 py-2.5 text-sm font-medium",
                    isActive(link.href) ? "bg-brand-50 text-brand-800" : "text-ink-700 hover:bg-ink-100",
                  )}
                >
                  {link.label}
                </Link>
              </li>
            ))}
            {!user && (
              <li className="pt-2">
                <ButtonLink href="/login" variant="outline" size="sm" fullWidth>Sign in</ButtonLink>
              </li>
            )}
          </ul>
        </div>
      )}
    </header>
  );
}

function MenuLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      role="menuitem"
      className="block px-3.5 py-2 text-sm text-ink-700 transition-colors hover:bg-ink-50"
    >
      {children}
    </Link>
  );
}

function Logo() {
  return (
    <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-700" aria-hidden="true">
      <svg className="h-4.5 w-4.5 text-white" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="7" width="18" height="13" rx="2" />
        <path d="M8.5 7V5.5A1.5 1.5 0 0110 4h4a1.5 1.5 0 011.5 1.5V7" />
        <path d="M3 12h18" />
      </svg>
    </span>
  );
}
