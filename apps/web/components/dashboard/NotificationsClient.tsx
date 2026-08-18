"use client";

import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/states";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { relativeTime } from "@/lib/format";
import type { NotificationItem } from "@/lib/types";

export function NotificationsClient() {
  const [items, setItems] = useState<NotificationItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await api.get<NotificationItem[]>("/notifications?limit=30", { revalidate: false }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load your notifications.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const markRead = async (item: NotificationItem) => {
    if (item.read_at) return;
    setItems((current) =>
      current?.map((n) => (n.id === item.id ? { ...n, read_at: new Date().toISOString() } : n)) ?? null,
    );
    await api.post(`/notifications/${item.id}/read`, {}).catch(() => undefined);
  };

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-bold tracking-tight text-ink-900 sm:text-2xl">Notifications</h1>
        <p className="mt-1 text-sm text-ink-500">Alert digests and account messages sent to you.</p>
      </header>

      {loading ? (
        <LoadingBlock label="Loading notifications…" />
      ) : error ? (
        <ErrorState description={error} onRetry={() => void load()} />
      ) : !items || items.length === 0 ? (
        <EmptyState
          title="No notifications yet"
          description="When one of your alerts matches a new job, the digest will appear here."
        />
      ) : (
        <ul className="space-y-2.5">
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => void markRead(item)}
                className={cn(
                  "w-full rounded-xl border p-4 text-left transition-colors",
                  item.read_at ? "border-ink-200 bg-white" : "border-brand-200 bg-brand-50/50",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm font-semibold text-ink-900">{item.subject}</p>
                  <span className="shrink-0 text-xs text-ink-400">{relativeTime(item.created_at)}</span>
                </div>
                {item.body && (
                  <p className="mt-1.5 line-clamp-3 whitespace-pre-wrap text-xs leading-relaxed text-ink-600">
                    {item.body}
                  </p>
                )}
                {item.status === "failed" && (
                  <p className="mt-2 text-xs font-medium text-amber-700">
                    Delivery to your email failed — check your address in Profile.
                  </p>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
