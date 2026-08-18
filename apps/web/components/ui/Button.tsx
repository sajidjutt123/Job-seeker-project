"use client";

import Link from "next/link";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "outline" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-brand-700 text-white hover:bg-brand-800 active:bg-brand-900 shadow-sm disabled:bg-brand-700/50",
  secondary:
    "bg-ink-900 text-white hover:bg-ink-800 active:bg-ink-950 shadow-sm disabled:bg-ink-900/50",
  outline:
    "border border-ink-300 bg-white text-ink-800 hover:bg-ink-50 hover:border-ink-400 active:bg-ink-100",
  ghost: "text-ink-700 hover:bg-ink-100 active:bg-ink-200",
  danger: "bg-accent-rose text-white hover:brightness-95 active:brightness-90 shadow-sm",
};

const SIZES: Record<Size, string> = {
  sm: "h-9 px-3.5 text-sm gap-1.5",
  md: "h-11 px-5 text-sm gap-2",
  lg: "h-12 px-6 text-base gap-2",
};

const BASE =
  "inline-flex items-center justify-center rounded-lg font-semibold transition-colors " +
  "disabled:cursor-not-allowed disabled:opacity-60 whitespace-nowrap select-none";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  fullWidth?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, fullWidth, leftIcon, rightIcon, className,
    children, disabled, type = "button", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(BASE, VARIANTS[variant], SIZES[size], fullWidth && "w-full", className)}
      {...props}
    >
      {loading ? <Spinner /> : leftIcon}
      {children}
      {!loading && rightIcon}
    </button>
  );
});

export interface ButtonLinkProps {
  href: string;
  variant?: Variant;
  size?: Size;
  fullWidth?: boolean;
  className?: string;
  children: ReactNode;
  external?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  onClick?: () => void;
  prefetch?: boolean;
  "aria-label"?: string;
}

export function ButtonLink({
  href, variant = "primary", size = "md", fullWidth, className,
  children, external, leftIcon, rightIcon, onClick, prefetch, ...rest
}: ButtonLinkProps) {
  const classes = cn(BASE, VARIANTS[variant], SIZES[size], fullWidth && "w-full", className);

  if (external) {
    return (
      <a
        href={href}
        target="_blank"
        // noopener/noreferrer is mandatory: apply links point at third-party sites.
        rel="noopener noreferrer nofollow"
        className={classes}
        onClick={onClick}
        {...rest}
      >
        {leftIcon}
        {children}
        {rightIcon}
      </a>
    );
  }

  return (
    <Link href={href} className={classes} onClick={onClick} prefetch={prefetch} {...rest}>
      {leftIcon}
      {children}
      {rightIcon}
    </Link>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cn("h-4 w-4 animate-spin", className)}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  );
}
