// Where the browser should reach the backend.
//
// These are resolved from the page's own location rather than hardcoded, because the bundle runs
// in whatever browser opens the app: on the Docker host ("localhost"), on another machine, or in
// another container (e.g. a browser container), where "localhost" is that browser's own machine
// and not the backend at all. VITE_API_BASE_URL / VITE_WS_BASE_URL still override completely when
// the backend lives somewhere unrelated; VITE_API_PORT just changes the port on the current host.
const DEFAULT_API_PORT = "8000";

function apiPort(): string {
  return import.meta.env.VITE_API_PORT ?? DEFAULT_API_PORT;
}

export function apiBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL ?? `${window.location.protocol}//${window.location.hostname}:${apiPort()}`;
}

export function wsBaseUrl(): string {
  if (import.meta.env.VITE_WS_BASE_URL) return import.meta.env.VITE_WS_BASE_URL;
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.hostname}:${apiPort()}`;
}
