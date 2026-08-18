import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type Tone = "neutral" | "brand" | "success" | "warning" | "danger" | "info" | "violet";

const TONES: Record<Tone, string> = {
  neutral: "bg-ink-100 text-ink-700 ring-ink-200",
  brand: "bg-brand-50 text-brand-800 ring-brand-200",
  success: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  warning: "bg-amber-50 text-amber-800 ring-amber-200",
  danger: "bg-rose-50 text-rose-800 ring-rose-200",
  info: "bg-sky-50 text-sky-800 ring-sky-200",
  violet: "bg-violet-50 text-violet-800 ring-violet-200",
};

export function Badge({
  children, tone = "neutral", icon, className, size = "md",
}: {
  children: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
  className?: string;
  size?: "sm" | "md";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md font-medium ring-1 ring-inset whitespace-nowrap",
        size === "sm" ? "px-1.5 py-0.5 text-[11px]" : "px-2 py-1 text-xs",
        TONES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

/**
 * Source attribution badge. Deliberately prominent: users must always be able to see
 * where a listing came from.
 */
export function JobSourceBadge({
  name, href, className, size = "md",
}: {
  name: string;
  href?: string | null;
  className?: string;
  size?: "sm" | "md";
}) {
  const content = (
    <>
      <svg className="h-3 w-3 shrink-0" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path d="M11 3a1 1 0 100 2h2.586l-6.293 6.293a1 1 0 101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z" />
        <path d="M5 5a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2v-3a1 1 0 10-2 0v3H5V7h3a1 1 0 000-2H5z" />
      </svg>
      <span className="truncate">{name}</span>
    </>
  );

  const classes = cn(
    "inline-flex max-w-[14rem] items-center gap-1 rounded-md bg-ink-100 font-medium text-ink-600 ring-1 ring-inset ring-ink-200",
    size === "sm" ? "px-1.5 py-0.5 text-[11px]" : "px-2 py-1 text-xs",
    href && "transition-colors hover:bg-ink-200 hover:text-ink-800",
    className,
  );

  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer nofollow"
        className={classes}
        title={`Source: ${name}`}
        onClick={(e) => e.stopPropagation()}
      >
        {content}
      </a>
    );
  }

  return (
    <span className={classes} title={`Source: ${name}`}>
      {content}
    </span>
  );
}

/** Compact match indicator for signed-in users. */
export function MatchScore({ score, className }: { score: number; className?: string }) {
  const tone: Tone = score >= 75 ? "success" : score >= 50 ? "brand" : "neutral";
  return (
    <Badge tone={tone} size="sm" className={className}>
      {Math.round(score)}% match
    </Badge>
  );
}
