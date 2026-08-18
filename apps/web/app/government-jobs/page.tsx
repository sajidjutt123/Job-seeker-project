import type { Metadata } from "next";

import { CategoryLandingPage } from "@/components/jobs/CategoryLandingPage";

export const revalidate = 600;

export const metadata: Metadata = {
  title: "Government jobs in Pakistan",
  description:
    "Public sector vacancies from federal and provincial departments, autonomous bodies and " +
    "government-linked organisations across Pakistan.",
  alternates: { canonical: "/government-jobs" },
};

export default function GovernmentJobsPage() {
  return (
    <CategoryLandingPage
      title="Government jobs in Pakistan"
      intro="Federal, provincial and public sector vacancies. Always confirm eligibility, age limits and closing dates on the official advertisement before applying."
      filters={{ government: true }}
      searchHref="/jobs?government=true"
      emptyTitle="No government vacancies listed right now"
      emptyDescription="Government listings arrive from official portal feeds. An administrator can enable additional government RSS sources in the admin panel."
      notice="Government advertisements are published by the issuing department. RozgarPK links to the official notice — we never collect application fees, and neither should any legitimate recruiter."
    />
  );
}
