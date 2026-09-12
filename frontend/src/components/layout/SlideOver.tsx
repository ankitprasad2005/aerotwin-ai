import type { ReactNode } from "react";

export function SlideOver({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div data-testid="slide-over-backdrop" className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative h-full w-full max-w-xl overflow-y-auto border-l border-border-visible bg-surface">
        {children}
      </div>
    </div>
  );
}
