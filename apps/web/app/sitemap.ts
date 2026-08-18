import type { MetadataRoute } from "next";

import { api } from "@/lib/api";

interface SitemapData {
  site_url: string;
  jobs: { slug: string; lastmod: string }[];
  cities: { slug: string; count: number }[];
  categories: { slug: string; count: number }[];
}

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export const revalidate = 3600;

/**
 * Sitemap built from real inventory only. Landing pages with too little content are excluded
 * by the API, so we never submit thin auto-generated pages.
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticEntries: MetadataRoute.Sitemap = [
    { url: `${SITE_URL}/`, changeFrequency: "hourly", priority: 1 },
    { url: `${SITE_URL}/jobs`, changeFrequency: "hourly", priority: 0.9 },
    { url: `${SITE_URL}/remote-jobs`, changeFrequency: "daily", priority: 0.8 },
    { url: `${SITE_URL}/government-jobs`, changeFrequency: "daily", priority: 0.8 },
    { url: `${SITE_URL}/internships`, changeFrequency: "daily", priority: 0.8 },
    { url: `${SITE_URL}/sources`, changeFrequency: "weekly", priority: 0.5 },
    { url: `${SITE_URL}/about`, changeFrequency: "monthly", priority: 0.4 },
    { url: `${SITE_URL}/privacy`, changeFrequency: "yearly", priority: 0.2 },
    { url: `${SITE_URL}/terms`, changeFrequency: "yearly", priority: 0.2 },
  ];

  let data: SitemapData | null = null;
  try {
    data = await api.get<SitemapData>("/seo/sitemap?limit=5000", { revalidate: 3600 });
  } catch {
    // A failing API must not produce a broken sitemap — serve the static section only.
    return staticEntries;
  }

  return [
    ...staticEntries,
    ...data.cities.map((city) => ({
      url: `${SITE_URL}/jobs-in-${city.slug}`,
      changeFrequency: "daily" as const,
      priority: 0.7,
    })),
    ...data.jobs.map((job) => ({
      url: `${SITE_URL}/jobs/${job.slug}`,
      lastModified: new Date(job.lastmod),
      changeFrequency: "daily" as const,
      priority: 0.6,
    })),
  ];
}
