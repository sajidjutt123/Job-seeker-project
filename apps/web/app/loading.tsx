import { JobListSkeleton } from "@/components/ui/states";

export default function Loading() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <div className="skeleton mb-6 h-8 w-56 rounded-lg" />
      <JobListSkeleton count={5} />
    </div>
  );
}
