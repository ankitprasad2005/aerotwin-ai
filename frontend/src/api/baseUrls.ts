// Where the browser should reach the backend.
//
// Same origin by default: the dev server proxies /api and /ws to the backend (see vite.config.ts),
// so the page needs no second reachable port and no CORS. This matters because the bundle runs in
// whatever browser opens the app — on the Docker host, on another device, in a browser container,
// or through a tunnel or reverse proxy — and anything hardcoded there is wrong for most of them.
//
// VITE_API_PORT points at a backend served directly on another port of the same host (no proxy);
// VITE_API_BASE_URL / VITE_WS_BASE_URL replace the origin entirely, for a backend somewhere else.
function directPort(): string | undefined {
  const port = import.meta.env.VITE_API_PORT;
  return port ? String(port) : undefined;
}

export function apiBaseUrl(): string {
  const explicit = import.meta.env.VITE_API_BASE_URL;
  if (explicit) return explicit;
  const port = directPort();
  // "" makes every request same-origin and relative: fetch("/api/runs").
  return port ? `${window.location.protocol}//${window.location.hostname}:${port}` : "";
}

export function wsBaseUrl(): string {
  const explicit = import.meta.env.VITE_WS_BASE_URL;
  if (explicit) return explicit;
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const port = directPort();
  // window.location.host keeps the page's own port, so the WebSocket rides the same proxy.
  return port ? `${protocol}//${window.location.hostname}:${port}` : `${protocol}//${window.location.host}`;
}
