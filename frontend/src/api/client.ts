import { apiBaseUrl } from "./baseUrls";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const API_BASE_URL = apiBaseUrl();

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
      // Pydantic validation errors (422) arrive as a list of {loc, msg, ...}.
      if (Array.isArray(detail)) {
        const messages = detail
          .map((item) => (typeof item === "object" && item !== null ? (item as { msg?: unknown }).msg : item))
          .filter((message): message is string => typeof message === "string");
        if (messages.length > 0) return messages.join("; ");
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

const MAX_QUERY_RETRIES = 3;

// React Query retry policy: retry transient failures (network errors, 5xx) up to 3 times like the
// default, but never a 4xx — a 404/422 won't change on retry, and retrying it only keeps the UI on
// [LOADING...] for several seconds of backoff before the error can be shown.
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < MAX_QUERY_RETRIES;
}
