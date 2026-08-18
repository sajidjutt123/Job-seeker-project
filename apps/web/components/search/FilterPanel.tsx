"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Checkbox, Input, Select } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import type { FilterOptions } from "@/lib/types";

/**
 * URL-driven filters. Every change rewrites the query string, so results stay shareable,
 * bookmarkable and back-button friendly, and the server can render them directly.
 */
export function FilterPanel({
  options, onApplied, className,
}: {
  options: FilterOptions | null;
  onApplied?: () => void;
  className?: string;
}) {
  const router = useRouter();
  const params = useSearchParams();

  const current = useMemo(
    () => ({
      city: params.get("city") ?? "",
      province: params.get("province") ?? "",
      categories: params.getAll("category"),
      employmentTypes: params.getAll("employment_type"),
      experience: params.getAll("experience"),
      education: params.get("education") ?? "",
      company: params.get("company") ?? "",
      remote: params.get("remote") === "true",
      government: params.get("government") === "true",
      internship: params.get("internship") === "true",
      freshGraduate: params.get("fresh_graduate") === "true",
      salaryMin: params.get("salary_min") ?? "",
      postedWithin: params.get("posted_within_days") ?? "",
    }),
    [params],
  );

  const [salaryDraft, setSalaryDraft] = useState(current.salaryMin);
  const [companyDraft, setCompanyDraft] = useState(current.company);

  const update = useCallback(
    (mutate: (next: URLSearchParams) => void) => {
      const next = new URLSearchParams(params.toString());
      mutate(next);
      next.delete("page"); // any filter change resets pagination
      router.push(`/jobs?${next.toString()}`, { scroll: false });
      onApplied?.();
    },
    [onApplied, params, router],
  );

  const setSingle = (key: string, value: string) =>
    update((next) => (value ? next.set(key, value) : next.delete(key)));

  const toggleMulti = (key: string, value: string) =>
    update((next) => {
      const existing = next.getAll(key);
      next.delete(key);
      const updated = existing.includes(value)
        ? existing.filter((v) => v !== value)
        : [...existing, value];
      updated.forEach((v) => next.append(key, v));
    });

  const toggleBool = (key: string, value: boolean) =>
    update((next) => (value ? next.set(key, "true") : next.delete(key)));

  const activeCount =
    (current.city ? 1 : 0) + (current.province ? 1 : 0) + current.categories.length +
    current.employmentTypes.length + current.experience.length + (current.education ? 1 : 0) +
    (current.company ? 1 : 0) + (current.remote ? 1 : 0) + (current.government ? 1 : 0) +
    (current.internship ? 1 : 0) + (current.freshGraduate ? 1 : 0) +
    (current.salaryMin ? 1 : 0) + (current.postedWithin ? 1 : 0);

  const clearAll = () => {
    const next = new URLSearchParams();
    const q = params.get("q");
    if (q) next.set("q", q);
    setSalaryDraft("");
    setCompanyDraft("");
    router.push(`/jobs?${next.toString()}`, { scroll: false });
    onApplied?.();
  };

  if (!options) {
    return (
      <div className={cn("space-y-4", className)}>
        <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          Filter options could not be loaded. Search still works — try again shortly.
        </p>
      </div>
    );
  }

  return (
    <div className={cn("space-y-5", className)}>
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink-900">
          Filters {activeCount > 0 && <span className="text-brand-700">({activeCount})</span>}
        </h2>
        {activeCount > 0 && (
          <button
            type="button"
            onClick={clearAll}
            className="text-xs font-medium text-brand-700 transition-colors hover:text-brand-800"
          >
            Clear all
          </button>
        )}
      </div>

      <Group title="Quick filters">
        <div className="space-y-2.5">
          <Checkbox label="Remote only" checked={current.remote} onChange={(e) => toggleBool("remote", e.target.checked)} />
          <Checkbox label="Government jobs" checked={current.government} onChange={(e) => toggleBool("government", e.target.checked)} />
          <Checkbox label="Internships" checked={current.internship} onChange={(e) => toggleBool("internship", e.target.checked)} />
          <Checkbox label="Fresh graduate friendly" checked={current.freshGraduate} onChange={(e) => toggleBool("fresh_graduate", e.target.checked)} />
        </div>
      </Group>

      <Group title="Location">
        <div className="space-y-2.5">
          <Select
            aria-label="City"
            placeholder="Any city"
            value={current.city}
            options={options.cities.map((c) => ({ value: c.value, label: c.label }))}
            onChange={(e) => setSingle("city", e.target.value)}
          />
          <Select
            aria-label="Province"
            placeholder="Any province"
            value={current.province}
            options={options.provinces.map((p) => ({ value: p.value, label: p.label }))}
            onChange={(e) => setSingle("province", e.target.value)}
          />
        </div>
      </Group>

      <CollapsibleGroup title="Category" count={current.categories.length}>
        <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
          {options.categories.map((category) => (
            <Checkbox
              key={category.value}
              label={category.label}
              checked={current.categories.includes(category.value)}
              onChange={() => toggleMulti("category", category.value)}
            />
          ))}
        </div>
      </CollapsibleGroup>

      <Group title="Job type">
        <div className="space-y-2">
          {options.employment_types.map((type) => (
            <Checkbox
              key={type.value}
              label={type.label}
              checked={current.employmentTypes.includes(type.value)}
              onChange={() => toggleMulti("employment_type", type.value)}
            />
          ))}
        </div>
      </Group>

      <Group title="Experience">
        <div className="space-y-2">
          {options.experience_levels.map((level) => (
            <Checkbox
              key={level.value}
              label={level.label}
              checked={current.experience.includes(level.value)}
              onChange={() => toggleMulti("experience", level.value)}
            />
          ))}
        </div>
      </Group>

      <Group title="Minimum salary (PKR / month)">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setSingle("salary_min", salaryDraft);
          }}
          className="flex gap-2"
        >
          <Input
            type="number"
            min={0}
            step={5000}
            inputMode="numeric"
            placeholder="e.g. 100000"
            value={salaryDraft}
            onChange={(e) => setSalaryDraft(e.target.value)}
            wrapperClassName="flex-1"
            aria-label="Minimum monthly salary"
          />
          <Button type="submit" variant="outline" size="md">Set</Button>
        </form>
      </Group>

      <Group title="Date posted">
        <Select
          aria-label="Date posted"
          placeholder="Any time"
          value={current.postedWithin}
          options={options.date_posted.map((d) => ({ value: d.value, label: d.label }))}
          onChange={(e) => setSingle("posted_within_days", e.target.value)}
        />
      </Group>

      <Group title="Education">
        <Select
          aria-label="Education level"
          placeholder="Any education"
          value={current.education}
          options={options.education_levels.map((e) => ({ value: e.value, label: e.label }))}
          onChange={(e) => setSingle("education", e.target.value)}
        />
      </Group>

      <Group title="Company">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setSingle("company", companyDraft.trim());
          }}
          className="flex gap-2"
        >
          <Input
            placeholder="Company name"
            value={companyDraft}
            onChange={(e) => setCompanyDraft(e.target.value)}
            wrapperClassName="flex-1"
            aria-label="Company name"
          />
          <Button type="submit" variant="outline" size="md">Find</Button>
        </form>
      </Group>
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <fieldset className="border-t border-ink-200 pt-4">
      <legend className="sr-only">{title}</legend>
      <h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-ink-500">{title}</h3>
      {children}
    </fieldset>
  );
}

function CollapsibleGroup({
  title, count, children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(count > 0);
  return (
    <fieldset className="border-t border-ink-200 pt-4">
      <legend className="sr-only">{title}</legend>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="mb-2.5 flex w-full items-center justify-between text-xs font-semibold uppercase tracking-wide text-ink-500 hover:text-ink-700"
        aria-expanded={open}
      >
        <span>
          {title}
          {count > 0 && <span className="ml-1.5 text-brand-700">({count})</span>}
        </span>
        <svg
          className={cn("h-4 w-4 transition-transform", open && "rotate-180")}
          viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"
        >
          <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
        </svg>
      </button>
      {open && children}
    </fieldset>
  );
}
