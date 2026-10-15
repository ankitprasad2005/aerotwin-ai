import { useEffect, useRef, type ReactNode } from "react";

export function SlideOver({
  open,
  onClose,
  children,
  label = "Details",
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  /** Accessible name of the dialog. */
  label?: string;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  // Callers often pass an inline handler; keeping it in a ref stops every re-render from
  // re-running the effect below (which would steal focus back to the panel).
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onCloseRef.current();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div data-testid="slide-over-backdrop" className="absolute inset-0 bg-black/70" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        className="relative h-full w-full max-w-xl overflow-y-auto border-l border-line-strong bg-panel shadow-2xl focus:outline-none"
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close panel"
          className="absolute right-3 top-3 z-10 rounded-sm px-2 py-1 text-lg leading-none text-muted hover:bg-panel-raised hover:text-ink"
        >
          ×
        </button>
        {children}
      </div>
    </div>
  );
}
