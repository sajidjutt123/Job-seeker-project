"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Checkbox, Input, Select } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/states";
import { api, ApiError } from "@/lib/api";
import { formatDate, relativeTime } from "@/lib/format";
import type { FilterOptions, JobAlert, JobListItem } from "@/lib/types";

interface AlertDraft {
  name: string;
  keywords: string;
  city: string;
  category: string;
  experience: string;
  remote_only: boolean;
  government_only: boolean;
  internship_only: boolean;
  salary_min: string;
  frequency: "instant" | "daily" | "weekly";
}

const EMPTY_DRAFT: AlertDraft = {
  name: "", keywords: "", city: "", category: "", experience: "",
  remote_only: false, government_only: false, internship_only: false,
  salary_min: "", frequency: "daily",
};

export function AlertsClient({ options }: { options: FilterOptions | null }) {
  const toast = useToast();
  const [alerts, setAlerts] = useState<JobAlert[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [draft, setDraft] = useState<AlertDraft>(EMPTY_DRAFT);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ id: string; jobs: JobListItem[] } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setAlerts(await api.get<JobAlert[]>("/alerts", { revalidate: false }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load your alerts.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const create = async () => {
    if (!draft.name.trim()) {
      setFormError("Give your alert a name so you can recognise it later.");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      await api.post("/alerts", {
        name: draft.name.trim(),
        keywords: draft.keywords.trim() || undefined,
        cities: draft.city ? [draft.city] : [],
        categories: draft.category ? [draft.category] : [],
        experience_levels: draft.experience ? [draft.experience] : [],
        remote_only: draft.remote_only,
        government_only: draft.government_only,
        internship_only: draft.internship_only,
        salary_min: draft.salary_min ? Number(draft.salary_min) : undefined,
        frequency: draft.frequency,
      });
      toast.success("Alert created. We will email you when matching jobs appear.");
      setModalOpen(false);
      setDraft(EMPTY_DRAFT);
      await load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not create the alert.");
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (alert: JobAlert) => {
    // Optimistic toggle with rollback.
    setAlerts((current) =>
      current?.map((a) => (a.id === alert.id ? { ...a, is_active: !a.is_active } : a)) ?? null,
    );
    try {
      await api.patch(`/alerts/${alert.id}`, { is_active: !alert.is_active });
    } catch {
      setAlerts((current) =>
        current?.map((a) => (a.id === alert.id ? { ...a, is_active: alert.is_active } : a)) ?? null,
      );
      toast.error("Could not update the alert.");
    }
  };

  const remove = async (alert: JobAlert) => {
    if (!window.confirm(`Delete the alert “${alert.name}”?`)) return;
    try {
      await api.delete(`/alerts/${alert.id}`);
      setAlerts((current) => current?.filter((a) => a.id !== alert.id) ?? null);
      toast.toast("Alert deleted.");
    } catch {
      toast.error("Could not delete the alert.");
    }
  };

  const runPreview = async (alert: JobAlert) => {
    try {
      const result = await api.post<{ count: number; items: JobListItem[] }>(`/alerts/${alert.id}/preview`);
      setPreview({ id: alert.id, jobs: result.items });
      if (result.count === 0) toast.toast("No jobs match this alert right now.");
    } catch {
      toast.error("Could not preview this alert.");
    }
  };

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-ink-900 sm:text-2xl">Job alerts</h1>
          <p className="mt-1 text-sm text-ink-500">
            We match new jobs against your criteria and email you the results.
          </p>
        </div>
        <Button size="sm" onClick={() => { setDraft(EMPTY_DRAFT); setFormError(null); setModalOpen(true); }}>
          Create alert
        </Button>
      </header>

      {loading ? (
        <LoadingBlock label="Loading your alerts…" />
      ) : error ? (
        <ErrorState description={error} onRetry={() => void load()} />
      ) : !alerts || alerts.length === 0 ? (
        <EmptyState
          title="No alerts yet"
          description="Create an alert and we will email you as soon as a matching job is published — you will not have to keep checking."
          action={<Button size="sm" onClick={() => setModalOpen(true)}>Create your first alert</Button>}
        />
      ) : (
        <ul className="space-y-3">
          {alerts.map((alert) => (
            <li key={alert.id} className="rounded-xl border border-ink-200 bg-white p-4 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="text-sm font-semibold text-ink-900">{alert.name}</h2>
                  <p className="mt-1 text-xs text-ink-500">{describeCriteria(alert)}</p>
                  <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-400">
                    <span>{alert.frequency === "instant" ? "Checked every 20 min" : alert.frequency === "daily" ? "Daily digest" : "Weekly digest"}</span>
                    <span>{alert.match_count} matches sent</span>
                    {alert.last_notified_at && <span>Last sent {relativeTime(alert.last_notified_at)}</span>}
                    {alert.created_at && <span>Created {formatDate(alert.created_at)}</span>}
                  </p>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  <label className="flex cursor-pointer items-center gap-1.5 text-xs text-ink-600">
                    <input
                      type="checkbox"
                      checked={alert.is_active}
                      onChange={() => void toggleActive(alert)}
                      className="h-4 w-4 rounded border-ink-300 accent-brand-700"
                    />
                    {alert.is_active ? "Active" : "Paused"}
                  </label>
                  <Button variant="ghost" size="sm" onClick={() => void runPreview(alert)}>Preview</Button>
                  <Button variant="ghost" size="sm" onClick={() => void remove(alert)}>Delete</Button>
                </div>
              </div>

              {preview?.id === alert.id && preview.jobs.length > 0 && (
                <div className="mt-3 rounded-lg border border-ink-200 bg-ink-50 p-3">
                  <p className="mb-2 text-xs font-semibold text-ink-700">
                    {preview.jobs.length} job{preview.jobs.length === 1 ? "" : "s"} match right now
                  </p>
                  <ul className="space-y-1.5">
                    {preview.jobs.slice(0, 5).map((job) => (
                      <li key={job.id}>
                        <a href={`/jobs/${job.slug}`} className="text-xs text-brand-700 hover:underline">
                          {job.title} — {job.company_name ?? "Company not stated"}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Create a job alert"
        description="We will email you when new jobs match these criteria."
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button size="sm" onClick={create} loading={saving}>Create alert</Button>
          </div>
        }
      >
        <div className="space-y-4">
          {formError && (
            <p role="alert" className="rounded-lg bg-rose-50 p-3 text-sm text-rose-800">{formError}</p>
          )}

          <Input
            label="Alert name"
            required
            placeholder="e.g. Software Engineer — Lahore"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          />
          <Input
            label="Keywords"
            hint="Job title, skill or company. Leave blank to match everything else you select."
            placeholder="e.g. software engineer python"
            value={draft.keywords}
            onChange={(e) => setDraft({ ...draft, keywords: e.target.value })}
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <Select
              label="City"
              placeholder="Any city"
              options={options?.cities.map((c) => ({ value: c.value, label: c.label })) ?? []}
              value={draft.city}
              onChange={(e) => setDraft({ ...draft, city: e.target.value })}
            />
            <Select
              label="Category"
              placeholder="Any category"
              options={options?.categories ?? []}
              value={draft.category}
              onChange={(e) => setDraft({ ...draft, category: e.target.value })}
            />
            <Select
              label="Experience level"
              placeholder="Any level"
              options={options?.experience_levels ?? []}
              value={draft.experience}
              onChange={(e) => setDraft({ ...draft, experience: e.target.value })}
            />
            <Input
              type="number"
              label="Minimum salary (PKR/month)"
              min={0}
              step={5000}
              placeholder="Optional"
              value={draft.salary_min}
              onChange={(e) => setDraft({ ...draft, salary_min: e.target.value })}
            />
          </div>

          <div className="space-y-2.5 rounded-lg border border-ink-200 p-3">
            <Checkbox
              label="Remote jobs only"
              checked={draft.remote_only}
              onChange={(e) => setDraft({ ...draft, remote_only: e.target.checked })}
            />
            <Checkbox
              label="Government jobs only"
              checked={draft.government_only}
              onChange={(e) => setDraft({ ...draft, government_only: e.target.checked })}
            />
            <Checkbox
              label="Internships only"
              checked={draft.internship_only}
              onChange={(e) => setDraft({ ...draft, internship_only: e.target.checked })}
            />
          </div>

          <Select
            label="How often should we email you?"
            options={[
              { value: "instant", label: "As soon as a job matches" },
              { value: "daily", label: "Once a day" },
              { value: "weekly", label: "Once a week" },
            ]}
            value={draft.frequency}
            onChange={(e) => setDraft({ ...draft, frequency: e.target.value as AlertDraft["frequency"] })}
          />
        </div>
      </Modal>
    </div>
  );
}

function describeCriteria(alert: JobAlert): string {
  const parts: string[] = [];
  if (alert.keywords) parts.push(`“${alert.keywords}”`);
  if (alert.cities.length) parts.push(alert.cities.join(", "));
  if (alert.categories.length) parts.push(alert.categories.join(", ").replace(/-/g, " "));
  if (alert.experience_levels.length) parts.push(alert.experience_levels.join(", ").replace(/_/g, " "));
  if (alert.remote_only) parts.push("remote only");
  if (alert.government_only) parts.push("government only");
  if (alert.internship_only) parts.push("internships only");
  if (alert.salary_min) parts.push(`min PKR ${Number(alert.salary_min).toLocaleString("en-PK")}`);
  return parts.length ? parts.join(" · ") : "All new jobs";
}
