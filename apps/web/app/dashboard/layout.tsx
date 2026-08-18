import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { DashboardNav } from "@/components/dashboard/DashboardNav";
import { fetchMe } from "@/lib/server-api";

export const metadata: Metadata = {
  title: "Dashboard",
  robots: { index: false, follow: false },
};

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  // Server-side gate: the API also enforces this, but redirecting here avoids a flash of
  // unauthenticated UI.
  const me = await fetchMe();
  if (!me) redirect("/login?next=/dashboard");

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      <div className="flex flex-col gap-6 lg:flex-row lg:gap-8">
        <aside className="lg:w-56 lg:shrink-0">
          <DashboardNav
            email={me.user.email}
            emailVerified={me.user.email_verified}
            isAdmin={me.user.role === "admin"}
            savedCount={me.stats.saved_jobs ?? 0}
            alertCount={me.stats.active_alerts ?? 0}
          />
        </aside>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
