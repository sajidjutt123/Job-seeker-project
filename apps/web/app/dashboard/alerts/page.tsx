import { AlertsClient } from "@/components/dashboard/AlertsClient";
import { fetchFilterOptions } from "@/lib/server-api";

export const metadata = { title: "Job alerts" };

export default async function AlertsPage() {
  const options = await fetchFilterOptions();
  return <AlertsClient options={options.ok ? options.data : null} />;
}
