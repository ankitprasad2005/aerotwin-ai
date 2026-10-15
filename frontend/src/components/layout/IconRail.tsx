import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { Tooltip } from "../ui/Tooltip";

const ICON_PROPS = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

const ICONS: Record<string, ReactNode> = {
  overview: (
    <svg {...ICON_PROPS}>
      <rect x="3" y="3" width="7" height="9" />
      <rect x="14" y="3" width="7" height="5" />
      <rect x="14" y="12" width="7" height="9" />
      <rect x="3" y="16" width="7" height="5" />
    </svg>
  ),
  runs: (
    <svg {...ICON_PROPS}>
      <path d="M8 6h13M8 12h13M8 18h13" />
      <path d="M3 6h.01M3 12h.01M3 18h.01" />
    </svg>
  ),
  new: (
    <svg {...ICON_PROPS}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v8M8 12h8" />
    </svg>
  ),
  data: (
    <svg {...ICON_PROPS}>
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
    </svg>
  ),
  weights: (
    <svg {...ICON_PROPS}>
      <path d="M4 7h10M18 7h2M4 17h2M10 17h10" />
      <circle cx="16" cy="7" r="2" />
      <circle cx="8" cy="17" r="2" />
    </svg>
  ),
  events: (
    <svg {...ICON_PROPS}>
      <path d="M3 12h4l3-8 4 16 3-8h4" />
    </svg>
  ),
};

export const NAV_ITEMS = [
  { to: "/", label: "Overview", icon: "overview", end: true },
  { to: "/runs", label: "Runs", icon: "runs", end: false },
  { to: "/new", label: "New run", icon: "new", end: true },
  { to: "/data", label: "Data", icon: "data", end: true },
  { to: "/weights", label: "Weights", icon: "weights", end: true },
  { to: "/events", label: "Events", icon: "events", end: true },
] as const;

/** The narrow left navigation rail: icons only, with a tooltip and an accessible name each. */
export function IconRail() {
  return (
    <nav aria-label="Main" className="flex w-12 shrink-0 flex-col items-center gap-1 border-r border-line bg-panel py-2">
      <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-sm bg-accent-subtle font-mono text-xs font-bold text-accent" aria-hidden="true">
        AT
      </div>
      {NAV_ITEMS.map((item) => (
        <Tooltip key={item.to} content={item.label} side="right">
          <NavLink
            to={item.to}
            end={item.end}
            aria-label={item.label}
            className={({ isActive }) =>
              `flex h-9 w-9 items-center justify-center rounded-sm ${
                isActive ? "bg-accent-subtle text-accent" : "text-muted hover:bg-panel-raised hover:text-ink"
              }`
            }
          >
            {ICONS[item.icon]}
          </NavLink>
        </Tooltip>
      ))}
    </nav>
  );
}
