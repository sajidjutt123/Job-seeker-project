import type { Metadata } from "next";

import { CategoryLandingPage } from "@/components/jobs/CategoryLandingPage";

export const revalidate = 600;

export const metadata: Metadata = {
  title: "Remote jobs in Pakistan",
  description:
    "Work-from-home and fully remote roles open to candidates in Pakistan, aggregated from " +
    "authorised sources and linked back to the original posting.",
  alternates: { canonical: "/remote-jobs" },
};

export default function RemoteJobsPage() {
  return (
    <CategoryLandingPage
      title="Remote jobs in Pakistan"
      intro="Roles you can do from anywhere in Pakistan — fully remote and work-from-home positions from employers hiring across the country and internationally."
      filters={{ remote: true }}
      searchHref="/jobs?remote=true"
      emptyTitle="No remote roles are open right now"
      emptyDescription="Remote listings appear here as soon as our sources publish them. Create an alert and we will email you first."
    />
  );
}
