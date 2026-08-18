"use client";

import { useRouter, useSearchParams } from "next/navigation";

import { cn } from "@/lib/cn";

export function Pagination({
  page, totalPages, className,
}: {
  page: number;
  totalPages: number;
  className?: string;
}) {
  const router = useRouter();
  const params = useSearchParams();

  if (totalPages <= 1) return null;

  const goTo = (target: number) => {
    const next = new URLSearchParams(params.toString());
    if (target <= 1) next.delete("page");
    else next.set("page", String(target));
    router.push(`/jobs?${next.toString()}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <nav className={cn("flex items-center justify-center gap-1.5", className)} aria-label="Pagination">
      <PageButton disabled={page <= 1} onClick={() => goTo(page - 1)} label="Previous page">
        <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path fillRule="evenodd" d="M12.79 5.23a.75.75 0 01-.02 1.06L8.832 10l3.938 3.71a.75.75 0 11-1.04 1.08l-4.5-4.25a.75.75 0 010-1.08l4.5-4.25a.75.75 0 011.06.02z" clipRule="evenodd" />
        </svg>
      </PageButton>

      {pageWindow(page, totalPages).map((item, index) =>
        item === "…" ? (
          <span key={`gap-${index}`} className="px-1.5 text-sm text-ink-400" aria-hidden="true">…</span>
        ) : (
          <button
            key={item}
            type="button"
            onClick={() => goTo(item)}
            aria-current={item === page ? "page" : undefined}
            className={cn(
              "min-w-9 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              item === page
                ? "bg-brand-700 text-white"
                : "border border-ink-200 bg-white text-ink-700 hover:bg-ink-50",
            )}
          >
            {item}
          </button>
        ),
      )}

      <PageButton disabled={page >= totalPages} onClick={() => goTo(page + 1)} label="Next page">
        <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
        </svg>
      </PageButton>
    </nav>
  );
}

function PageButton({
  children, disabled, onClick, label,
}: {
  children: React.ReactNode;
  disabled: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className="rounded-lg border border-ink-200 bg-white p-2 text-ink-600 transition-colors hover:bg-ink-50 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}

/** Compact page window: 1 … 4 5 [6] 7 8 … 20 */
function pageWindow(page: number, total: number): (number | "…")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);

  const items: (number | "…")[] = [1];
  const start = Math.max(2, page - 1);
  const end = Math.min(total - 1, page + 1);

  if (start > 2) items.push("…");
  for (let i = start; i <= end; i += 1) items.push(i);
  if (end < total - 1) items.push("…");
  items.push(total);

  return items;
}
