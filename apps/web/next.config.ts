import type { NextConfig } from "next";

/**
 * The browser never talks to the API host directly — it calls same-origin `/api/*`, which this
 * rewrite proxies to the backend. That keeps cookies first-party, avoids CORS in the browser,
 * and means the deployed frontend works behind any proxy without a public API hostname.
 */
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Emits a self-contained server bundle for a minimal production container.
  output: "standalone",
  outputFileTracingRoot: process.cwd(),

  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_INTERNAL_URL}/api/:path*` },
      // Keep the SEO-friendly /jobs-in-lahore URL while using a normal dynamic segment
      // internally (Next.js does not match partial path segments like `jobs-in-[city]`).
      { source: "/jobs-in-:city", destination: "/city-jobs/:city" },
    ];
  },

  images: {
    // Company logos come from arbitrary employer domains; keep them optimised but bounded.
    remotePatterns: [{ protocol: "https", hostname: "**" }],
    formats: ["image/avif", "image/webp"],
    minimumCacheTTL: 86400,
  },

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-DNS-Prefetch-Control", value: "on" },
          {
            key: "Permissions-Policy",
            value: "geolocation=(), microphone=(), camera=(), interest-cohort=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
