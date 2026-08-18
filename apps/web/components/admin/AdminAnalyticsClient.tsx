"use client";

import { useCallback, useEffect, useState } from "react";

import { Select } from "@/components/ui/Input";
import { ErrorState, LoadingBlock } from "@/components/ui/states";
import { api, ApiError } from "@/lib/api";

interface Analytics {
  period_days: number;
  searches: number;
  job_views: number;
  apply_clicks: number;
  saves: number;
  alerts_created: number;
  zero_result_searches: number;
  top_queries: { value: string; count: number }[];
  top_cities: { value: string; count: number }[];
  top_categories: { value: string; count: number }[];
}

export function AdminAnalyticsClient() {
  const [data, setData] = useState<Analytics | null>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.get<Analytics>(`/admin/analytics?days=${days}`, { revalidate: false }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load analytics.");
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { void load(); }, [load]);

  if (loading && !data) return <LoadingBlock label="Loading analytics…" />;
  if (error) return <ErrorState description={error} onRetry={() => void load()} />;
  if (!data) return null;

  const applyRate = data.job_views > 0 ? ((data.apply_clicks / data.job_views) * 100).toFixed(1) : "0.0";
  const zeroRate = data.searches > 0 ? ((data.zero_result_searches / data.searches) * 100).toFixed(1) : "0.0";

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-ink-900 sm:text-2xl">Analytics</h1>
          <p className="mt-1 text-sm text-ink-500">
            Aggregate product metrics. No personal data is collected.
          </p>
        </div>
        <Select
          aria-label="Time period" value={String(days)}
          onChange={(e) => setDays(Number(e.target.value))}
          options={[
            { value: "7", label: "Last 7 days" },
            { value: "30", label: "Last 30 days" },
            { value: "90", label: "Last 90 days" },
          ]}
          wrapperClassName="w-40"
        />
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Metric label="Searches" value={data.searches} />
        <Metric label="Job views" value={data.job_views} />
        <Metric label="Apply clicks" value={data.apply_clicks} />
        <Metric label="Saves" value={data.saves} />
        <Metric label="Alerts created" value={data.alerts_created} />
        <Metric label="Apply rate" value={`${applyRate}%`} />
      </div>

      {data.searches > 0 && Number(zeroRate) > 20 && (
        <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <span className="font-semibold">{zeroRate}% of searches returned nothing.</span>{" "}
          That usually means inventory gaps — consider enabling more sources for the terms below.
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <TopList title="Most searched terms" items={data.top_queries} empty="No searches recorded yet." />
        <TopList title="Most searched cities" items={data.top_cities} empty="No city filters used yet." />
        <TopList
          title="Largest categories"
          items={data.top_categories.map((c) => ({ value: c.value.replace(/-/g, " "), count: c.count }))}
          empty="No jobs indexed yet."
        />
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl border border-ink-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</p>
      <p className="mt-1.5 text-xl font-bold tracking-tight text-ink-900">
        {typeof value === "number" ? value.toLocaleString("en-PK") : value}
      </p>
    </div>
  );
}

function TopList({ title, items, empty }: { title: string; items: { value: string; count: number }[]; empty: string }) {
  return (
    <section className="rounded-xl border border-ink-200 bg-white p-4">
      <h2 className="text-sm font-bold text-ink-900">{title}</h2>
      {items.length === 0 ? (
        <p className="mt-3 text-sm text-ink-500">{empty}</p>
      ) : (
        <ol className="mt-3 space-y-1.5">
          {items.map((item, index) => (
            <li key={`${item.value}-${index}`} className="flex items-center justify-between gap-3 text-sm">
              <span className="truncate text-ink-700">{item.value}</span>
              <span className="shrink-0 font-mono text-xs text-ink-500">{item.count}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
