import { useId, useState, type ReactNode } from "react";

interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  /** "right" suits the left icon rail; "bottom" suits the top bar. */
  side?: "right" | "bottom";
  className?: string;
}

/** A hover/focus tooltip. The trigger stays whatever the child is; the tooltip is linked with
 * aria-describedby and is dismissible with Escape (WCAG 1.4.13). */
export function Tooltip({ content, children, side = "bottom", className = "" }: TooltipProps) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const position = side === "right" ? "left-full top-1/2 ml-2 -translate-y-1/2" : "left-1/2 top-full mt-1.5 -translate-x-1/2";

  return (
    <span
      className={`relative inline-flex ${className}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onKeyDown={(event) => {
        if (event.key === "Escape") setOpen(false);
      }}
      aria-describedby={open ? id : undefined}
    >
      {children}
      {open && (
        <span
          id={id}
          role="tooltip"
          className={`pointer-events-none absolute z-50 w-max max-w-[260px] rounded-sm border border-line-strong bg-panel-raised px-2 py-1 text-xs text-ink shadow-lg ${position}`}
        >
          {content}
        </span>
      )}
    </span>
  );
}
