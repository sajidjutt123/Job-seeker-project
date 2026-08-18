import { NextResponse, type NextRequest } from "next/server";

/**
 * Edge gate for private areas (Next.js 16 `proxy` convention, formerly `middleware`).
 *
 * This is the *first* of three layers, and the weakest by design — it only checks whether a
 * session cookie is present, because the edge must not be trusted to validate a signature or
 * decide roles:
 *
 *   1. proxy (here)          — fast HTTP 307 for obviously-signed-out visitors. No render,
 *                              no data fetch, no flash of a protected shell.
 *   2. server component      — `fetchMe()` in the dashboard/admin layouts verifies the session
 *                              and the role against the API before rendering anything.
 *   3. the API               — the real security boundary. Every protected route re-checks the
 *                              token and every admin route re-checks the role, server-side.
 *
 * A forged cookie gets past step 1 and is rejected by steps 2 and 3, which is exactly the
 * intended split: this layer is a UX optimisation, not a security control.
 */

const PROTECTED_PREFIXES = ["/dashboard", "/admin"];
const SESSION_COOKIES = ["rozgar_access", "rozgar_refresh"];

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (!PROTECTED_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    return NextResponse.next();
  }

  const hasSession = SESSION_COOKIES.some((name) => request.cookies.has(name));
  if (hasSession) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", `${pathname}${search}`);

  const response = NextResponse.redirect(loginUrl, 307);
  // Never let a CDN cache the redirect for a URL that varies per visitor.
  response.headers.set("Cache-Control", "no-store");
  return response;
}

export const config = {
  matcher: ["/dashboard/:path*", "/admin/:path*"],
};
