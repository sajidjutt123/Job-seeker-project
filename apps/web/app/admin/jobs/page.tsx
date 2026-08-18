import { Suspense } from "react";

import { AdminJobsClient } from "@/components/admin/AdminJobsClient";
import { LoadingBlock } from "@/components/ui/states";

export const metadata = { title: "Jobs — Admin" };

export default function AdminJobsPage() {
  return (
    <Suspense fallback={<LoadingBlock />}>
      <AdminJobsClient />
    </Suspense>
  );
}
