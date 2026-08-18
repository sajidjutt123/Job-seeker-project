"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { useToast } from "@/components/ui/Toast";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/states";
import { api, ApiError, buildQuery } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDate, relativeTime } from "@/lib/format";

interface AdminUser {
  id: string;
  email: string;
  role: string;
  status: string;
  email_verified: boolean;
  created_at?: string | null;
  last_login_at?: string | null;
  full_name?: string | null;
  city?: string | null;
  profile_completion: number;
}

export function AdminUsersClient() {
  const toast = useToast();
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => { setDebounced(query); setPage(1); }, 350);
    return () => clearTimeout(timer);
  }, [query]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.get<{ items: AdminUser[]; total: number }>(
        `/admin/users${buildQuery({ q: debounced || undefined, status: status || undefined, page, page_size: 25 })}`,
        { revalidate: false },
      );
      setUsers(result.items);
      setTotal(result.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load users.");
    } finally {
      setLoading(false);
    }
  }, [debounced, status, page]);

  useEffect(() => { void load(); }, [load]);

  const act = async (user: AdminUser, action: "suspend" | "restore") => {
    if (action === "suspend" && !window.confirm(`Suspend ${user.email}? They will be signed out immediately.`)) return;
    setBusy(user.id);
    try {
      await api.post(`/admin/users/${user.id}/${action}`, action === "suspend" ? { reason: "Admin action" } : {});
      toast.success(`User ${action}d.`);
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : `Could not ${action} the user.`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-bold tracking-tight text-ink-900 sm:text-2xl">Users</h1>
        <p className="mt-1 text-sm text-ink-500">{total.toLocaleString("en-PK")} registered accounts.</p>
      </header>

      <div className="flex flex-wrap gap-2.5">
        <Input
          type="search" placeholder="Search by email" value={query}
          onChange={(e) => setQuery(e.target.value)} wrapperClassName="min-w-56 flex-1"
          aria-label="Search users"
        />
        <Select
          aria-label="Status" placeholder="All statuses" value={status}
          onChange={(e) => { setStatus(e.target.value); setPage(1); }}
          options={[
            { value: "active", label: "Active" },
            { value: "pending_verification", label: "Pending verification" },
            { value: "suspended", label: "Suspended" },
          ]}
          wrapperClassName="w-52"
        />
      </div>

      {loading && !users ? (
        <LoadingBlock label="Loading users…" />
      ) : error ? (
        <ErrorState description={error} onRetry={() => void load()} />
      ) : !users || users.length === 0 ? (
        <EmptyState title="No users match" description="Try a different search or filter." />
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-ink-200 bg-white">
            <table className="w-full min-w-[48rem] text-sm">
              <thead className="border-b border-ink-200 bg-ink-50 text-left">
                <tr>
                  <th className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink-500">User</th>
                  <th className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink-500">Status</th>
                  <th className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink-500">Profile</th>
                  <th className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink-500">Joined</th>
                  <th className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink-500">Last login</th>
                  <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-ink-500">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {users.map((user) => (
                  <tr key={user.id}>
                    <td className="px-4 py-3">
                      <p className="font-medium text-ink-900">{user.email}</p>
                      <p className="mt-0.5 text-xs text-ink-500">
                        {user.full_name ?? "No name"}{user.city ? ` · ${user.city}` : ""}
                        {user.role !== "user" && (
                          <span className="ml-1.5 rounded bg-violet-100 px-1.5 py-0.5 text-[11px] font-semibold text-violet-800">
                            {user.role}
                          </span>
                        )}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn(
                        "rounded px-2 py-0.5 text-xs font-medium",
                        user.status === "active" ? "bg-emerald-100 text-emerald-800" :
                        user.status === "suspended" ? "bg-rose-100 text-rose-800" :
                        "bg-amber-100 text-amber-800",
                      )}>
                        {user.status.replace(/_/g, " ")}
                      </span>
                      {!user.email_verified && (
                        <p className="mt-1 text-[11px] text-ink-400">Email unverified</p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-ink-600">{user.profile_completion}%</td>
                    <td className="px-4 py-3 text-xs text-ink-500">{formatDate(user.created_at)}</td>
                    <td className="px-4 py-3 text-xs text-ink-500">
                      {user.last_login_at ? relativeTime(user.last_login_at) : "Never"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end">
                        {user.status === "suspended" ? (
                          <Button variant="outline" size="sm" disabled={busy === user.id}
                                  onClick={() => void act(user, "restore")}>
                            Restore
                          </Button>
                        ) : (
                          <Button variant="ghost" size="sm" disabled={busy === user.id}
                                  onClick={() => void act(user, "suspend")}>
                            Suspend
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-center gap-3">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <span className="text-sm text-ink-500">Page {page}</span>
            <Button variant="outline" size="sm" disabled={users.length < 25} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
