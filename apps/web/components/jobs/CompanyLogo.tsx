"use client";

import { useState } from "react";

import { cn } from "@/lib/cn";
import { initials } from "@/lib/format";

const PALETTE = [
  "bg-brand-100 text-brand-800",
  "bg-sky-100 text-sky-800",
  "bg-violet-100 text-violet-800",
  "bg-amber-100 text-amber-800",
  "bg-emerald-100 text-emerald-800",
  "bg-rose-100 text-rose-800",
];

/** Stable colour per company so the same employer always looks the same. */
function paletteFor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return PALETTE[hash % PALETTE.length];
}

export function CompanyLogo({
  name, logoUrl, size = "md", className,
}: {
  name?: string | null;
  logoUrl?: string | null;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const label = name || "Unknown company";

  const sizes = {
    sm: "h-9 w-9 text-xs rounded-md",
    md: "h-11 w-11 text-sm rounded-lg",
    lg: "h-16 w-16 text-lg rounded-xl",
  };

  if (logoUrl && !failed) {
    return (
      // Plain <img>: logos come from arbitrary third-party hosts that may not be reachable,
      // and a broken logo must degrade to initials rather than break layout.
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={logoUrl}
        alt={`${label} logo`}
        loading="lazy"
        decoding="async"
        onError={() => setFailed(true)}
        className={cn(
          "shrink-0 border border-ink-200 bg-white object-contain p-1",
          sizes[size],
          className,
        )}
      />
    );
  }

  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-center font-semibold",
        sizes[size],
        paletteFor(label),
        className,
      )}
      aria-hidden="true"
      title={label}
    >
      {initials(name)}
    </div>
  );
}
