/** Display formatting helpers. Pure, testable, no React. */

import type { EmploymentType, ExperienceLevel, JobListItem, SalaryRange } from "./types";

const EMPLOYMENT_LABELS: Record<EmploymentType, string> = {
  full_time: "Full time",
  part_time: "Part time",
  contract: "Contract",
  temporary: "Temporary",
  internship: "Internship",
  freelance: "Freelance",
  volunteer: "Volunteer",
  unknown: "Not stated",
};

const EXPERIENCE_LABELS: Record<ExperienceLevel, string> = {
  intern: "Intern",
  fresh_graduate: "Fresh graduate",
  entry: "Entry level",
  mid: "Mid level",
  senior: "Senior",
  lead: "Lead",
  executive: "Executive",
  unknown: "Any experience",
};

const EDUCATION_LABELS: Record<string, string> = {
  matric: "Matric",
  intermediate: "Intermediate",
  diploma: "Diploma",
  bachelors: "Bachelors",
  masters: "Masters",
  phd: "PhD",
};

export const employmentLabel = (v?: string | null) =>
  (v && EMPLOYMENT_LABELS[v as EmploymentType]) || "Not stated";

export const experienceLabel = (v?: string | null) =>
  (v && EXPERIENCE_LABELS[v as ExperienceLevel]) || "Any experience";

export const educationLabel = (v?: string | null) => (v && EDUCATION_LABELS[v]) || null;

export function workModeLabel(job: Pick<JobListItem, "work_mode" | "is_remote">): string | null {
  if (job.is_remote || job.work_mode === "remote") return "Remote";
  if (job.work_mode === "hybrid") return "Hybrid";
  if (job.work_mode === "onsite") return "On-site";
  return null;
}

const PERIOD_SUFFIX: Record<string, string> = {
  month: "/month",
  year: "/year",
  hour: "/hour",
  week: "/week",
  day: "/day",
};

/** Compact salary display: "PKR 80k – 120k/month". Returns null when undisclosed. */
export function formatSalary(salary?: SalaryRange | null): string | null {
  if (!salary) return null;
  const min = toNumber(salary.min);
  const max = toNumber(salary.max);
  if (min === null && max === null) return null;

  const currency = salary.currency || "PKR";
  const suffix = PERIOD_SUFFIX[salary.period || "month"] ?? "";

  if (min !== null && max !== null && min !== max) {
    return `${currency} ${compact(min)} – ${compact(max)}${suffix}`;
  }
  const single = (max ?? min) as number;
  return `${currency} ${compact(single)}${suffix}`;
}

function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = typeof value === "number" ? value : Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Pakistani-reader-friendly compaction: 1.2M, 250k, 85k. */
function compact(value: number): string {
  if (value >= 10_000_000) return `${trim(value / 10_000_000)} crore`;
  if (value >= 1_000_000) return `${trim(value / 1_000_000)}M`;
  if (value >= 1_000) return `${trim(value / 1_000)}k`;
  return String(Math.round(value));
}

const trim = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, ""));

/** "2 hours ago", "3 days ago", "12 Mar 2026". */
export function relativeTime(iso?: string | null): string {
  if (!iso) return "Recently";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Recently";

  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months} month${months === 1 ? "" : "s"} ago`;
  return formatDate(iso);
}

export function formatDate(iso?: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-PK", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

/** Deadline urgency copy used on cards and detail pages. */
export function deadlineInfo(iso?: string | null): { label: string; urgent: boolean } | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;

  const days = Math.ceil((date.getTime() - Date.now()) / 86_400_000);
  if (days < 0) return { label: "Closed", urgent: true };
  if (days === 0) return { label: "Closes today", urgent: true };
  if (days === 1) return { label: "Closes tomorrow", urgent: true };
  if (days <= 7) return { label: `Closes in ${days} days`, urgent: true };
  return { label: `Closes ${formatDate(iso)}`, urgent: false };
}

export function jobLocationLabel(job: Pick<JobListItem, "location" | "city" | "province" | "is_remote">): string {
  if (job.location) return job.location;
  if (job.city) return job.province ? `${job.city}, ${job.province}` : job.city;
  if (job.is_remote) return "Remote";
  return "Pakistan";
}

export function initials(name?: string | null): string {
  if (!name) return "?";
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

export function pluralize(count: number, singular: string, plural?: string): string {
  return `${count.toLocaleString("en-PK")} ${count === 1 ? singular : plural ?? `${singular}s`}`;
}
