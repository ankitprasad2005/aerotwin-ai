import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "ghost";

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  const base = "font-mono text-[11px] uppercase tracking-[0.08em] px-md py-sm transition-colors duration-200 disabled:cursor-not-allowed";
  const variants: Record<Variant, string> = {
    primary: "bg-accent text-text-display hover:bg-accent/90 disabled:bg-border disabled:text-text-disabled",
    ghost: "border border-border-visible text-text-primary hover:border-text-secondary disabled:text-text-disabled disabled:border-border",
  };

  return <button className={`${base} ${variants[variant]} ${className}`} {...props} />;
}
