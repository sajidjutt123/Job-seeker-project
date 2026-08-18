import { ProfileClient } from "@/components/dashboard/ProfileClient";
import { fetchFilterOptions, fetchMe } from "@/lib/server-api";

export const metadata = { title: "Your profile" };

export default async function ProfilePage() {
  const [me, options] = await Promise.all([fetchMe(), fetchFilterOptions()]);
  return (
    <ProfileClient
      initialProfile={me?.profile ?? null}
      options={options.ok ? options.data : null}
    />
  );
}
