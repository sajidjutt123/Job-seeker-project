"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { cn } from "@/lib/cn";

interface OverlayProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
}

/** Accessible modal: Escape to close, focus trapped, background scroll locked. */
export function Modal({ open, onClose, title, description, children, footer, size = "md" }: OverlayProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  useDialogBehaviour(open, onClose, panelRef);

  if (!open) return null;

  const widths = { sm: "max-w-sm", md: "max-w-lg", lg: "max-w-2xl" };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4">
      <div
        className="absolute inset-0 bg-ink-950/40 animate-[fade-in_0.15s_ease-out]"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        className={cn(
          "relative w-full rounded-t-2xl bg-white shadow-panel sm:rounded-xl",
          "animate-[slide-up_0.24s_cubic-bezier(0.16,1,0.3,1)]",
          "max-h-[92vh] overflow-y-auto",
          widths[size],
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-ink-200 px-5 py-4">
          <div className="min-w-0">
            <h2 id="modal-title" className="text-base font-semibold text-ink-900">{title}</h2>
            {description && <p className="mt-1 text-sm text-ink-500">{description}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="-m-1.5 shrink-0 rounded-md p-1.5 text-ink-400 transition-colors hover:bg-ink-100 hover:text-ink-700"
            aria-label="Close dialog"
          >
            <CloseIcon />
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer && <div className="border-t border-ink-200 px-5 py-3.5">{footer}</div>}
      </div>
    </div>
  );
}

/** Slide-in panel — used for mobile filters. */
export function Drawer({ open, onClose, title, children, footer, side = "left" }: Omit<OverlayProps, "size"> & { side?: "left" | "right" }) {
  const panelRef = useRef<HTMLDivElement>(null);
  useDialogBehaviour(open, onClose, panelRef);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <div className="absolute inset-0 bg-ink-950/40 animate-[fade-in_0.15s_ease-out]" onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        className={cn(
          "absolute inset-y-0 flex w-[88%] max-w-sm flex-col bg-white shadow-panel",
          side === "left" ? "left-0" : "right-0",
        )}
        style={{ animation: "slide-up 0.22s cubic-bezier(0.16,1,0.3,1)" }}
      >
        <div className="flex items-center justify-between border-b border-ink-200 px-4 py-3.5">
          <h2 id="drawer-title" className="text-base font-semibold text-ink-900">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="-m-1.5 rounded-md p-1.5 text-ink-400 transition-colors hover:bg-ink-100 hover:text-ink-700"
            aria-label="Close panel"
          >
            <CloseIcon />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">{children}</div>
        {footer && <div className="border-t border-ink-200 px-4 py-3">{footer}</div>}
      </div>
    </div>
  );
}

function useDialogBehaviour(
  open: boolean,
  onClose: () => void,
  panelRef: React.RefObject<HTMLDivElement | null>,
) {
  useEffect(() => {
    if (!open) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;

      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    // Move focus into the dialog for screen-reader and keyboard users.
    requestAnimationFrame(() => {
      panelRef.current
        ?.querySelector<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
        ?.focus();
    });

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = originalOverflow;
      previouslyFocused?.focus?.();
    };
  }, [open, onClose, panelRef]);
}

function CloseIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
    </svg>
  );
}
