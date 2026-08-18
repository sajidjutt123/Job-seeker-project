/**
 * Server-side data fetching helpers for React Server Components.
 *
 * Two guarantees:
 *  1. Cookies from the incoming request are forwarded, so SSR sees the signed-in user.
 *  2. Failures return a typed result instead of throwing, so a page can render a real
 *     error state rather than a 500.
 */

import { cookies } from "next/headers";

import { api, ApiError, buildQuery, type RequestOptions } from "./api";
import type {
  FilterOptions, JobDetail, JobFacets, JobListItem, JobSearchResponse, MeResponse, PublicSource,
} from "./types";

export async function cookieHeader(): Promise<string> {
  const store = await cookies();
  return store
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");
}

export type Result<T> = { ok: true; data: T } | { ok: false; error: string; status: number; code: string };

/** Wraps a fetch so route handlers/pages can branch on failure instead of crashing. */
export async function safe<T>(fn: () => Promise<T>): Promise<Result<T>> {
  try {
    return { ok: true, data: await fn() };
  } catch (error) {
    if (error instanceof ApiError) {
      return { ok: false, error: error.message, status: error.status, code: error.code };
    }
    return {
      ok: false,
      error: "We could not load this right now. Please try again.",
      status: 500,
      code: "unknown",
    };
  }
}

async function authed(options: RequestOptions = {}): Promise<RequestOptions> {
  return { ...options, cookieHeader: await cookieHeader(), revalidate: false };
}

/* ------------------------------------------------------------------ jobs -- */

export interface SearchParams {
  q?: string;
  city?: string;
  province?: string;
  category?: string | string[];
  employment_type?: string | string[];
  experience?: string | string[];
  education?: string;
  company?: string;
  skills?: string | string[];
  remote?: boolean;
  government?: boolean;
  internship?: boolean;
  fresh_graduate?: boolean;
  salary_min?: number;
  salary_max?: number;
  posted_within_days?: number;
  sort?: string;
  page?: number;
  page_size?: number;
  facets?: boolean;
}

export async function fetchJobs(params: SearchParams): Promise<Result<JobSearchResponse>> {
  return safe(async () =>
    api.get<JobSearchResponse>(`/jobs${buildQuery(params as Record<string, unknown>)}`, await authed()),
  );
}

export async function fetchLatestJobs(
  params: { limit?: number; remote?: boolean; government?: boolean; internship?: boolean; city?: string; category?: string },
): Promise<Result<JobListItem[]>> {
  return safe(async () =>
    api.get<JobListItem[]>(`/jobs/latest${buildQuery(params as Record<string, unknown>)}`, await authed()),
  );
}

export async function fetchJobDetail(slug: string): Promise<Result<JobDetail>> {
  return safe(async () => api.get<JobDetail>(`/jobs/${encodeURIComponent(slug)}`, await authed()));
}

export async function fetchJobFacets(): Promise<Result<JobFacets>> {
  // Homepage counts change slowly; a short cache keeps first load fast.
  return safe(() => api.get<JobFacets>("/jobs/facets", { revalidate: 300 }));
}

export async function fetchRecommended(limit = 8): Promise<Result<JobListItem[]>> {
  return safe(async () => api.get<JobListItem[]>(`/jobs/recommended?limit=${limit}`, await authed()));
}

/* --------------------------------------------------------------- catalog -- */

export async function fetchFilterOptions(): Promise<Result<FilterOptions>> {
  return safe(() => api.get<FilterOptions>("/filters", { revalidate: 3600 }));
}

export async function fetchPublicSources(): Promise<Result<PublicSource[]>> {
  return safe(() => api.get<PublicSource[]>("/sources", { revalidate: 600 }));
}

/* ------------------------------------------------------------------ user -- */

export async function fetchMe(): Promise<MeResponse | null> {
  const result = await safe(async () => api.get<MeResponse>("/auth/me", await authed()));
  return result.ok ? result.data : null;
}
