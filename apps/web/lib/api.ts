/**
 * Typed API client.
 *
 * Works in both runtimes:
 *  - browser: same-origin relative `/api/...` (cookies flow, no CORS)
 *  - server components: absolute internal URL, forwarding the incoming cookie header
 *
 * Every failure becomes an `ApiError` carrying a user-safe message — callers never see
 * raw fetch/JSON exceptions.
 */

import type { ApiErrorBody } from "./types";

const API_PREFIX = "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: Record<string, unknown>;
  readonly requestId?: string;

  constructor(
    message: string,
    status: number,
    code = "error",
    details?: Record<string, unknown>,
    requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }

  /** Field-level errors from the API's validation envelope, for inline form messages. */
  get fieldErrors(): Record<string, string> {
    const fields = this.details?.fields;
    return fields && typeof fields === "object" ? (fields as Record<string, string>) : {};
  }

  get isUnauthorized() {
    return this.status === 401;
  }
  get isNotFound() {
    return this.status === 404;
  }
  get isRateLimited() {
    return this.status === 429;
  }
  get isServerError() {
    return this.status >= 500;
  }
}

function resolveBase(): string {
  if (typeof window !== "undefined") return "";
  return process.env.API_INTERNAL_URL ?? "http://localhost:8000";
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Server components must forward cookies explicitly. */
  cookieHeader?: string;
  /** Next.js fetch caching controls. */
  revalidate?: number | false;
  tags?: string[];
  timeoutMs?: number;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, cookieHeader, revalidate, tags, timeoutMs = 15000, ...init } = options;

  const headers = new Headers(init.headers);
  if (body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Accept", "application/json");
  if (cookieHeader) headers.set("cookie", cookieHeader);

  const nextOptions =
    revalidate === undefined && !tags
      ? undefined
      : { revalidate: revalidate === false ? undefined : revalidate, tags };

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${resolveBase()}${API_PREFIX}${path}`, {
      ...init,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "include",
      cache: revalidate === false ? "no-store" : init.cache,
      signal: controller.signal,
      ...(nextOptions ? { next: nextOptions } : {}),
    });
  } catch (error) {
    clearTimeout(timer);
    if (error instanceof Error && error.name === "AbortError") {
      throw new ApiError("The request took too long. Please try again.", 504, "timeout");
    }
    throw new ApiError(
      "We could not reach the server. Check your connection and try again.",
      503,
      "network_error",
    );
  }
  clearTimeout(timer);

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const envelope = payload as ApiErrorBody | null;
    throw new ApiError(
      envelope?.error?.message ?? "Something went wrong. Please try again.",
      response.status,
      envelope?.error?.code ?? "error",
      envelope?.error?.details,
      envelope?.error?.request_id,
    );
  }

  return payload as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "POST", body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "PUT", body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "DELETE" }),
};

/** Builds a query string, dropping empty values and expanding arrays into repeated keys. */
export function buildQuery(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      value.filter((v) => v !== undefined && v !== null && v !== "").forEach((v) => search.append(key, String(v)));
    } else if (typeof value === "boolean") {
      search.set(key, value ? "true" : "false");
    } else {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}
