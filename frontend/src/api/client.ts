export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// Backend errors are FastAPI's default `{"detail": "..."}` JSON shape. Unwrap it so
// UI code never has to display a raw JSON string as a human-readable error message.
function extractErrorMessage(body: string): string {
  try {
    const parsed: unknown = JSON.parse(body);
    if (typeof parsed === "object" && parsed !== null && "detail" in parsed) {
      const detail = (parsed as { detail: unknown }).detail;
      if (typeof detail === "string") {
        return detail;
      }
    }
  } catch {
    // Not JSON — fall through to returning the raw body.
  }
  return body;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  // Headers (not an object spread) so a caller-supplied Headers instance isn't silently dropped.
  const headers = new Headers(init?.headers);
  // Only declare a JSON body when there is one: on a bodiless GET the header means nothing, and
  // as a non-CORS-safelisted header it forces a preflight before every cross-origin read.
  if (init?.body != null && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, extractErrorMessage(body) || response.statusText);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
