import type { Metadata } from "next";

import { CategoryLandingPage } from "@/components/jobs/CategoryLandingPage";

export const revalidate = 600;

export const metadata: Metadata = {
  title: "Internships in Pakistan",
  description:
    "Paid internships, management trainee programmes and graduate schemes for students and " +
    "fresh graduates across Pakistan.",
  alternates: { canonical: "/internships" },
};

export default function InternshipsPage() {
  return (
    <CategoryLandingPage
      title="Internships in Pakistan"
      intro="Internships, management trainee programmes and graduate schemes — a practical first step for students and fresh graduates."
      filters={{ internship: true }}
      searchHref="/jobs?internship=true"
      emptyTitle="No internships are open right now"
      emptyDescription="Internship intakes are seasonal. Create an alert and we will email you the moment one opens."
    />
  );
}
