// Dev-server settings derived from the environment, kept free of Vite imports so they can be unit-tested.
//
// Vite refuses requests whose Host header it does not recognise ("Blocked request. This host is not allowed"),
// which breaks the UI behind a domain or reverse proxy. The hosts a deployment serves the UI from are the same
// origins the backend must accept for CORS, so both read AEROTWIN_CORS_ORIGINS: one setting, no drift.
// VITE_ALLOWED_HOSTS adds more (comma-separated; a leading dot such as ".example.com" allows subdomains),
// and "all" or "true" turns the check off.

type Env = Record<string, string | undefined>;

function entries(raw: string | undefined): string[] {
  if (!raw?.trim()) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed.filter((item): item is string => typeof item === "string");
  } catch {
    // Not JSON: fall back to a comma-separated list below.
  }
  return raw.replace(/^\s*\[|\]\s*$/g, "").split(",");
}

function hostOf(entry: string): string | null {
  const value = entry.trim().replace(/^["']|["']$/g, "");
  if (!value || value === "*") return null;
  if (value.startsWith(".")) return value.toLowerCase(); // Vite's subdomain wildcard
  try {
    const url = new URL(value.includes("://") ? value : `http://${value}`);
    return url.hostname && !/\s/.test(value) ? url.hostname.toLowerCase() : null;
  } catch {
    return null;
  }
}

export function allowedHosts(env: Env): string[] | true {
  if (/^(all|true)$/i.test(env.VITE_ALLOWED_HOSTS?.trim() ?? "")) return true;
  const hosts = [...entries(env.AEROTWIN_CORS_ORIGINS), ...entries(env.VITE_ALLOWED_HOSTS)]
    .map(hostOf)
    .filter((host): host is string => host !== null);
  return Array.from(new Set(hosts));
}

// Behind an HTTPS reverse proxy the browser must open the HMR WebSocket on the proxy's port (usually 443),
// not on the dev server's own port. Unset or invalid keeps Vite's default.
export function hmrClientPort(env: Env): number | undefined {
  const port = Number(env.VITE_HMR_CLIENT_PORT);
  return Number.isInteger(port) && port > 0 && port <= 65535 ? port : undefined;
}
