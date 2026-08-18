"use client";

import Link from "next/link";
import { useCallback, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Badge, JobSourceBadge, MatchScore } from "@/components/ui/Badge";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  deadlineInfo, employmentLabel, experienceLabel, formatSalary,
  jobLocationLabel, relativeTime, workModeLabel,
} from "@/lib/format";
import type { JobListItem } from "@/lib/types";

import { CompanyLogo } from "./CompanyLogo";

export function JobCard({
  job, onSavedChange, compact = false,
}: {
  job: JobListItem;
  onSavedChange?: (jobId: string, saved: boolean) => void;
  compact?: boolean;
}) {
  const { user } = useAuth();
  const toast = useToast();
  const [saved, setSaved] = useState(Boolean(job.is_saved));
  const [savePending, setSavePending] = useState(false);

  const salary = formatSalary(job.salary);
  const deadline = deadlineInfo(job.deadline);
  const mode = workModeLabel(job);
  const isExpired = job.status !== "active";

  const toggleSave = useCallback(
    async (event: React.MouseEvent) => {
      event.preventDefault();
      event.stopPropagation();

      if (!user) {
        toast.toast("Sign in to save jobs.", "info");
        return;
      }
      setSavePending(true);
      // Optimistic: revert if the request fails.
      const next = !saved;
      setSaved(next);
      try {
        if (next) {
          await api.post(`/saved-jobs/${job.id}`, {});
          toast.success("Saved to your list.");
        } else {
          await api.delete(`/saved-jobs/${job.id}`);
          toast.toast("Removed from saved jobs.");
        }
        onSavedChange?.(job.id, next);
      } catch (error) {
        setSaved(!next);
        const message =
          error instanceof ApiError ? error.message : "Could not update your saved jobs.";
        toast.error(message);
      } finally {
        setSavePending(false);
      }
    },
    [job.id, onSavedChange, saved, toast, user],
  );

  const share = useCallback(
    async (event: React.MouseEvent) => {
      event.preventDefault();
      event.stopPropagation();
      const url = `${window.location.origin}/jobs/${job.slug}`;
      try {
        if (navigator.share) {
          await navigator.share({ title: job.title, url });
          return;
        }
        await navigator.clipboard.writeText(url);
        toast.success("Link copied to clipboard.");
      } catch {
        // User cancelled the share sheet — not an error worth surfacing.
      }
    },
    [job.slug, job.title, toast],
  );

  return (
    <article
      className={cn(
        "group relative rounded-xl border bg-white transition-all",
        "hover:border-ink-300 hover:shadow-card-hover",
        job.is_featured ? "border-brand-300 ring-1 ring-brand-200" : "border-ink-200",
        isExpired && "opacity-70",
        compact ? "p-3.5" : "p-4 sm:p-5",
      )}
    >
      <div className="flex gap-3 sm:gap-3.5">
        <CompanyLogo name={job.company_name} logoUrl={job.company?.logo_url} size={compact ? "sm" : "md"} />

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-[15px] font-semibold leading-snug text-ink-900">
                <Link
                  href={`/jobs/${job.slug}`}
                  className="before:absolute before:inset-0 hover:text-brand-700 focus-visible:text-brand-700"
                >
                  {job.title}
                </Link>
              </h3>
              <p className="mt-0.5 truncate text-sm text-ink-600">
                {job.company_name ?? "Company not stated"}
                {job.company?.verified && (
                  <svg className="ml-1 inline h-3.5 w-3.5 text-brand-600" viewBox="0 0 20 20" fill="currentColor" aria-label="Verified employer">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.86-9.7a1 1 0 10-1.72-1.02l-2.6 4.38-1.3-1.42a1 1 0 10-1.48 1.35l2.2 2.4a1 1 0 001.6-.16l3.3-5.54z" clipRule="evenodd" />
                  </svg>
                )}
              </p>
            </div>

            <div className="relative z-10 flex shrink-0 items-center gap-0.5">
              {typeof job.match_score === "number" && !compact && (
                <MatchScore score={job.match_score} className="mr-1 hidden sm:inline-flex" />
              )}
              <IconButton
                label={saved ? "Remove from saved jobs" : "Save job"}
                onClick={toggleSave}
                disabled={savePending}
                active={saved}
              >
                <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill={saved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                  <path d="M6 4h12a1 1 0 011 1v15l-7-4-7 4V5a1 1 0 011-1z" strokeLinejoin="round" />
                </svg>
              </IconButton>
              <IconButton label="Share job" onClick={share}>
                <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                  <circle cx="18" cy="5" r="2.5" /><circle cx="6" cy="12" r="2.5" /><circle cx="18" cy="19" r="2.5" />
                  <path d="m8.2 10.8 7.6-4.1M8.2 13.2l7.6 4.1" strokeLinecap="round" />
                </svg>
              </IconButton>
            </div>
          </div>

          {/* Facts row: location, salary, type, experience */}
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-600">
            <Fact icon={<LocationIcon />}>{jobLocationLabel(job)}</Fact>
            {salary && <Fact icon={<WalletIcon />}><span className="font-medium text-ink-800">{salary}</span></Fact>}
            <Fact icon={<BriefcaseIcon />}>{employmentLabel(job.employment_type)}</Fact>
            {job.experience_level !== "unknown" && (
              <Fact icon={<LevelIcon />}>{experienceLabel(job.experience_level)}</Fact>
            )}
          </div>

          {/* Tags */}
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            {mode === "Remote" && <Badge tone="success" size="sm">Remote</Badge>}
            {mode === "Hybrid" && <Badge tone="info" size="sm">Hybrid</Badge>}
            {job.is_government && <Badge tone="violet" size="sm">Government</Badge>}
            {job.is_internship && <Badge tone="brand" size="sm">Internship</Badge>}
            {job.is_fresh_graduate_friendly && !job.is_internship && (
              <Badge tone="brand" size="sm">Fresh grad</Badge>
            )}
            {job.is_featured && <Badge tone="warning" size="sm">Featured</Badge>}
            {isExpired && <Badge tone="danger" size="sm">No longer accepting</Badge>}
            {deadline && !isExpired && (
              <Badge tone={deadline.urgent ? "warning" : "neutral"} size="sm">{deadline.label}</Badge>
            )}
          </div>

          {/* Match reasons for signed-in users */}
          {job.match_reasons?.length > 0 && !compact && (
            <p className="mt-2.5 flex items-start gap-1.5 text-xs text-brand-800">
              <svg className="mt-0.5 h-3.5 w-3.5 shrink-0" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path d="M10 2l2.2 5.1 5.5.5-4.2 3.7 1.3 5.4L10 13.9 5.2 16.7l1.3-5.4L2.3 7.6l5.5-.5L10 2z" />
              </svg>
              {job.match_reasons[0]}
            </p>
          )}

          {/* Footer: posted date + source attribution */}
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-ink-100 pt-2.5">
            <span className="text-xs text-ink-500">{relativeTime(job.posted_at)}</span>
            {job.source && (
              <JobSourceBadge name={job.source.label ?? job.source.name} href={job.source.website_url} size="sm" />
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

function IconButton({
  children, label, onClick, disabled, active,
}: {
  children: React.ReactNode;
  label: string;
  onClick: (e: React.MouseEvent) => void;
  disabled?: boolean;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className={cn(
        "rounded-md p-2 transition-colors disabled:opacity-50",
        active ? "text-brand-700 hover:bg-brand-50" : "text-ink-400 hover:bg-ink-100 hover:text-ink-700",
      )}
    >
      {children}
    </button>
  );
}

function Fact({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="text-ink-400" aria-hidden="true">{icon}</span>
      {children}
    </span>
  );
}

const iconProps = {
  className: "h-3.5 w-3.5",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  "aria-hidden": true,
} as const;

const LocationIcon = () => (
  <svg {...iconProps}><path d="M12 21s-7-5.5-7-11a7 7 0 1114 0c0 5.5-7 11-7 11z" /><circle cx="12" cy="10" r="2.5" /></svg>
);
const WalletIcon = () => (
  <svg {...iconProps}><rect x="3" y="6" width="18" height="13" rx="2" /><path d="M3 10h18M16 14h2" strokeLinecap="round" /></svg>
);
const BriefcaseIcon = () => (
  <svg {...iconProps}><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M9 7V5a2 2 0 012-2h2a2 2 0 012 2v2" /></svg>
);
const LevelIcon = () => (
  <svg {...iconProps}><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" strokeLinecap="round" /></svg>
);
