import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/", label: "DASHBOARD" },
  { to: "/orchestration", label: "ORCHESTRATION" },
  { to: "/events", label: "EVENTS" },
];

export function Sidebar() {
  return (
    <nav className="w-48 shrink-0 border-r border-border bg-black p-md">
      <div className="mb-2xl font-display text-2xl text-text-display">AEROTWIN</div>
      <ul className="flex flex-col gap-sm">
        {LINKS.map((link) => (
          <li key={link.to}>
            <NavLink
              to={link.to}
              end={link.to === "/"}
              className={({ isActive }) =>
                `block font-mono text-[11px] uppercase tracking-[0.08em] py-sm px-sm ${
                  isActive ? "text-accent" : "text-text-secondary hover:text-text-primary"
                }`
              }
            >
              {link.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
