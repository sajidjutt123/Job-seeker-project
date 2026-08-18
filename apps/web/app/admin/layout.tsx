import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AdminNav } from "@/components/admin/AdminNav";
import { fetchMe } from "@/lib/server-api";

export const metadata: Metadata = {
  title: "Admin",
  robots: { index: false, follow: false },
};

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  // Defence in depth: the API enforces the admin role on every route; this only avoids
  // rendering an admin shell to a non-admin.
  const me = await fetchMe();
  if (!me) redirect("/login?next=/admin");
  if (me.user.role !== "admin") redirect("/dashboard");

  return (
    <div className="mx-auto max-w-[100rem] px-4 py-6 sm:px-6 lg:px-8">
      <div className="flex flex-col gap-6 lg:flex-row lg:gap-8">
        <aside className="lg:w-52 lg:shrink-0">
          <AdminNav email={me.user.email} />
        </aside>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
