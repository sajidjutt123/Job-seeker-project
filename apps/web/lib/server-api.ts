/**
 * Server-side data fetching helpers for React Server Components.
 *
 * Two guarantees:
 *  1. Cookies from the incoming request are forwarded, so SSR sees the signed-in user.
 *  2. Failures return a typed result instead of throwing, so a page can render a real
 *     error state rather than a 500.
 */

import { cookies, headers } from "next/headers";

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

/**
 * Headers every server-side API call must carry.
 *
 * SSR calls the API on behalf of many different visitors from one host. Two things follow:
 *
 *  - `x-internal-key` identifies the web tier as a trusted caller so its traffic is not charged
 *    to a single shared IP bucket. Without it, one busy minute rate-limits the whole site.
 *  - `x-forwarded-for` passes the real visitor's IP through, so per-visitor limiting and hashed
 *    IP records stay accurate. The API only believes this header from a trusted proxy.
 *
 * The key is server-only (no NEXT_PUBLIC_ prefix) and never reaches the browser.
 */
async function internalHeaders(): Promise<Record<string, string>> {
  const result: Record<string, string> = {};

  const key = process.env.INTERNAL_API_KEY;
  if (key) result["x-internal-key"] = key;

  const incoming = await headers();
  const forwarded = incoming.get("x-forwarded-for") ?? incoming.get("x-real-ip");
  if (forwarded) result["x-forwarded-for"] = forwarded;

  return result;
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
  return {
    ...options,
    cookieHeader: await cookieHeader(),
    headers: { ...(options.headers as Record<string, string>), ...(await internalHeaders()) },
    revalidate: false,
  };
}

/** For cacheable, non-user-specific fetches: internal key, but no cookies. */
async function shared(options: RequestOptions = {}): Promise<RequestOptions> {
  return {
    ...options,
    headers: { ...(options.headers as Record<string, string>), ...(await internalHeaders()) },
  };
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
  return safe(async () => api.get<JobFacets>("/jobs/facets", await shared({ revalidate: 300 })));
}

export async function fetchRecommended(limit = 8): Promise<Result<JobListItem[]>> {
  return safe(async () => api.get<JobListItem[]>(`/jobs/recommended?limit=${limit}`, await authed()));
}

/* --------------------------------------------------------------- catalog -- */

export async function fetchFilterOptions(): Promise<Result<FilterOptions>> {
  return safe(async () => api.get<FilterOptions>("/filters", await shared({ revalidate: 3600 })));
}

export async function fetchPublicSources(): Promise<Result<PublicSource[]>> {
  return safe(async () => api.get<PublicSource[]>("/sources", await shared({ revalidate: 600 })));
}

/* ------------------------------------------------------------------ user -- */

export async function fetchMe(): Promise<MeResponse | null> {
  const result = await safe(async () => api.get<MeResponse>("/auth/me", await authed()));
  return result.ok ? result.data : null;
}
