"use client";

import { useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Select, Textarea, Input } from "@/components/ui/Input";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import type { JobDetail } from "@/lib/types";

const REPORT_REASONS = [
  { value: "expired", label: "This job is no longer open" },
  { value: "broken_link", label: "The apply link is broken" },
  { value: "scam", label: "Looks like a scam" },
  { value: "spam", label: "Spam or advertising" },
  { value: "duplicate", label: "Duplicate listing" },
  { value: "wrong_information", label: "Information is wrong" },
  { value: "offensive", label: "Offensive content" },
  { value: "other", label: "Something else" },
];

export function JobActions({ job }: { job: JobDetail }) {
  const { user } = useAuth();
  const toast = useToast();
  const [saved, setSaved] = useState(Boolean(job.is_saved));
  const [savePending, setSavePending] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);

  const isOpen = job.status === "active";

  const trackApply = () => {
    // Fire-and-forget: navigation to the source must never wait on analytics.
    api.post(`/jobs/${job.id}/apply-click`, {}).catch(() => undefined);
  };

  const toggleSave = async () => {
    if (!user) {
      window.location.href = `/login?next=${encodeURIComponent(`/jobs/${job.slug}`)}`;
      return;
    }
    setSavePending(true);
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
    } catch (error) {
      setSaved(!next);
      toast.error(error instanceof ApiError ? error.message : "Could not update your saved jobs.");
    } finally {
      setSavePending(false);
    }
  };

  const share = async () => {
    const url = `${window.location.origin}/jobs/${job.slug}`;
    try {
      if (navigator.share) {
        await navigator.share({ title: job.title, text: `${job.title} at ${job.company_name ?? "a company"}`, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      toast.success("Link copied to clipboard.");
    } catch {
      /* user cancelled */
    }
  };

  return (
    <>
      <div className="space-y-2.5">
        {isOpen ? (
          <ButtonLink
            href={job.apply_url}
            external
            size="lg"
            fullWidth
            onClick={trackApply}
            rightIcon={
              <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path d="M11 3a1 1 0 100 2h2.586l-6.293 6.293a1 1 0 101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z" />
                <path d="M5 5a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2v-3a1 1 0 10-2 0v3H5V7h3a1 1 0 000-2H5z" />
              </svg>
            }
          >
            Apply on original source
          </ButtonLink>
        ) : (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3.5 text-center">
            <p className="text-sm font-semibold text-amber-900">
              This opportunity is no longer accepting applications.
            </p>
            <p className="mt-1 text-xs text-amber-800">
              The source has closed or withdrawn this listing.
            </p>
          </div>
        )}

        <Button variant="outline" size="lg" fullWidth onClick={toggleSave} loading={savePending}
          leftIcon={
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill={saved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
              <path d="M6 4h12a1 1 0 011 1v15l-7-4-7 4V5a1 1 0 011-1z" strokeLinejoin="round" />
            </svg>
          }
        >
          {saved ? "Saved" : "Save job"}
        </Button>

        <div className="flex gap-2">
          <Button variant="ghost" size="sm" fullWidth onClick={share}>Share</Button>
          <Button variant="ghost" size="sm" fullWidth onClick={() => setReportOpen(true)}>
            Report this job
          </Button>
        </div>
      </div>

      <ReportModal
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        jobId={job.id}
        signedIn={Boolean(user)}
      />
    </>
  );
}

function ReportModal({
  open, onClose, jobId, signedIn,
}: {
  open: boolean;
  onClose: () => void;
  jobId: string;
  signedIn: boolean;
}) {
  const toast = useToast();
  const [reason, setReason] = useState("expired");
  const [details, setDetails] = useState("");
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await api.post(`/jobs/${jobId}/report`, {
        reason,
        details: details.trim() || undefined,
        reporter_email: signedIn ? undefined : email.trim() || undefined,
      });
      toast.success("Thank you. Our team will review this listing.");
      onClose();
      setDetails("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send your report. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Report this job"
      description="Tell us what is wrong and we will review it."
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={submit} loading={submitting}>Send report</Button>
        </div>
      }
    >
      <div className="space-y-4">
        {error && (
          <p role="alert" className="rounded-lg bg-rose-50 p-3 text-sm text-rose-800">{error}</p>
        )}
        <Select
          label="Reason"
          value={reason}
          options={REPORT_REASONS}
          onChange={(e) => setReason(e.target.value)}
        />
        <Textarea
          label="Details (optional)"
          placeholder="Anything else we should know?"
          maxLength={2000}
          value={details}
          onChange={(e) => setDetails(e.target.value)}
        />
        {!signedIn && (
          <Input
            type="email"
            label="Your email"
            hint="So we can follow up if we need more information."
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        )}
      </div>
    </Modal>
  );
}
