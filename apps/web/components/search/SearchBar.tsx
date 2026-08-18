"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { buildQuery } from "@/lib/api";

const POPULAR_CITIES = [
  "Lahore", "Karachi", "Islamabad", "Rawalpindi", "Faisalabad",
  "Multan", "Peshawar", "Quetta", "Sialkot", "Hyderabad", "Gujranwala",
];

export function SearchBar({
  defaultQuery = "", defaultCity = "", size = "lg", className, autoFocus,
}: {
  defaultQuery?: string;
  defaultCity?: string;
  size?: "md" | "lg";
  className?: string;
  autoFocus?: boolean;
}) {
  const router = useRouter();
  const [query, setQuery] = useState(defaultQuery);
  const [city, setCity] = useState(defaultCity);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    // URL-driven search keeps results shareable and indexable.
    router.push(`/jobs${buildQuery({ q: query.trim() || undefined, city: city || undefined })}`);
  };

  const inputHeight = size === "lg" ? "h-14" : "h-12";

  return (
    <form
      onSubmit={onSubmit}
      className={cn(
        "flex w-full flex-col gap-2 rounded-xl border border-ink-200 bg-white p-2 shadow-card sm:flex-row sm:items-center sm:gap-0 sm:p-1.5",
        className,
      )}
      role="search"
      aria-label="Job search"
    >
      <div className="relative flex-1">
        <label htmlFor="search-keyword" className="sr-only">Job title or keyword</label>
        <svg
          className="pointer-events-none absolute left-3.5 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-ink-400"
          viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" aria-hidden="true"
        >
          <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" strokeLinecap="round" />
        </svg>
        <input
          id="search-keyword"
          name="q"
          type="search"
          autoFocus={autoFocus}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Job title, skill or company"
          className={cn(
            "w-full rounded-lg border-0 bg-transparent pl-11 pr-3 text-[15px] text-ink-900",
            "placeholder:text-ink-400 focus:outline-none focus:ring-0",
            inputHeight,
          )}
        />
      </div>

      <div className="hidden h-8 w-px bg-ink-200 sm:block" aria-hidden="true" />

      <div className="relative sm:w-56">
        <label htmlFor="search-city" className="sr-only">City</label>
        <svg
          className="pointer-events-none absolute left-3.5 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-ink-400"
          viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" aria-hidden="true"
        >
          <path d="M12 21s-7-5.5-7-11a7 7 0 1114 0c0 5.5-7 11-7 11z" /><circle cx="12" cy="10" r="2.5" />
        </svg>
        <input
          id="search-city"
          name="city"
          list="popular-cities"
          value={city}
          onChange={(e) => setCity(e.target.value)}
          placeholder="City"
          className={cn(
            "w-full rounded-lg border-0 bg-transparent pl-11 pr-3 text-[15px] text-ink-900",
            "placeholder:text-ink-400 focus:outline-none focus:ring-0",
            inputHeight,
          )}
        />
        <datalist id="popular-cities">
          {POPULAR_CITIES.map((c) => <option key={c} value={c} />)}
        </datalist>
      </div>

      <Button
        type="submit"
        size={size === "lg" ? "lg" : "md"}
        loading={submitting}
        className="shrink-0 sm:ml-1.5"
      >
        Search jobs
      </Button>
    </form>
  );
}
