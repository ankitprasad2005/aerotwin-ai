import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "ghost" | "danger";

export function Button({
  variant = "primary",
  className = "",
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-sm px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed";
  const variants: Record<Variant, string> = {
    primary: "bg-accent text-canvas hover:bg-accent/90 disabled:bg-line-strong disabled:text-faint",
    ghost:
      "border border-line-strong text-ink hover:border-muted hover:bg-panel-raised disabled:border-line disabled:text-faint disabled:hover:bg-transparent",
    danger: "border border-bad/60 text-bad hover:bg-bad/10 disabled:border-line disabled:text-faint",
  };

  return <button type={type} className={`${base} ${variants[variant]} ${className}`} {...props} />;
}
