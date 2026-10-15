/** Formatters shared across the UI. Every one tolerates null/undefined/NaN and renders "—", so a
 * missing field (an older decision without a score, a run without a duration) never crashes a view. */
export const DASH = "—";

function isNum(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export function formatUsdValue(value: number | null | undefined): string {
  return isNum(value) ? usd.format(value) : DASH;
}

/** "+$1,200" / "-$300" / "$0": the sign makes a profit change readable at a glance. */
export function formatSignedUsd(value: number | null | undefined): string {
  if (!isNum(value)) return DASH;
  const rounded = Math.round(value);
  if (rounded === 0) return usd.format(0);
  return `${rounded > 0 ? "+" : "-"}${usd.format(Math.abs(rounded))}`;
}

export function formatCompact(value: number | null | undefined): string {
  if (!isNum(value)) return DASH;
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${(value / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
  return String(Math.round(value));
}

export function formatDuration(ms: number | null | undefined): string {
  if (!isNum(ms) || ms < 0) return DASH;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds - minutes * 60);
  // 59.6 s rounds to 60: carry it into the minutes instead of printing "1m 60s".
  return rest === 60 ? `${minutes + 1}m 00s` : `${minutes}m ${String(rest).padStart(2, "0")}s`;
}

/** Confidence and other 0..1 fractions as a whole-number percentage. */
export function formatFraction(value: number | null | undefined): string {
  return isNum(value) ? `${Math.round(value * 100)}%` : DASH;
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  return isNum(value) ? `${value.toFixed(digits)}%` : DASH;
}

export function formatScore(value: number | null | undefined): string {
  return isNum(value) ? String(Math.round(value)) : DASH;
}

export function formatNumber(value: number | null | undefined): string {
  return isNum(value) ? new Intl.NumberFormat("en-US").format(value) : DASH;
}

export function formatFuelPrice(value: number | null | undefined): string {
  return isNum(value) ? `$${value.toFixed(2)}/gal` : DASH;
}

export function formatRate(value: number | null | undefined): string {
  return isNum(value) ? value.toFixed(2) : DASH;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return DASH;
  return date.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function formatRelative(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return DASH;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return DASH;
  const seconds = Math.max(0, Math.round((now.getTime() - then) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function truncate(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}

/** "2026-10-15" -> "15 Oct". Falls back to the raw string when it is not a date. */
export function formatDay(date: string): string {
  const parsed = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return date;
  return parsed.toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" });
}
