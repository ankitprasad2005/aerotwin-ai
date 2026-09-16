import { afterEach, describe, expect, it, vi } from "vitest";
import { apiBaseUrl, wsBaseUrl } from "./baseUrls";

const originalLocation = window.location;

function setLocation(href: string) {
  Object.defineProperty(window, "location", { value: new URL(href), writable: true, configurable: true });
}

afterEach(() => {
  Object.defineProperty(window, "location", { value: originalLocation, writable: true, configurable: true });
  vi.unstubAllEnvs();
});

describe("baseUrls", () => {
  it("addresses the backend on VITE_API_PORT of the current host when one is set", () => {
    // vite.config.ts sets VITE_API_PORT=8000 for unit tests, matching the msw handlers.
    expect(apiBaseUrl()).toBe("http://localhost:8000");
    expect(wsBaseUrl()).toBe("ws://localhost:8000");
  });

  it("keeps the host from the page's own address, not a hardcoded one", () => {
    // The bug this guards against: a hardcoded localhost made every request fail when the UI was
    // opened from another device or container, where localhost is the browser's own machine.
    vi.stubEnv("VITE_API_PORT", "8005");
    setLocation("http://192.168.68.179:3005/orchestration");
    expect(apiBaseUrl()).toBe("http://192.168.68.179:8005");
    expect(wsBaseUrl()).toBe("ws://192.168.68.179:8005");
  });

  it("goes same-origin when no port is configured, so the dev server can proxy it", () => {
    vi.stubEnv("VITE_API_PORT", "");
    setLocation("http://192.168.68.179:3005/orchestration");
    // Relative: fetch("/api/runs") on the page's own origin — one port, no CORS.
    expect(apiBaseUrl()).toBe("");
    expect(wsBaseUrl()).toBe("ws://192.168.68.179:3005");
  });

  it("uses a secure websocket when the page is served over https", () => {
    vi.stubEnv("VITE_API_PORT", "");
    setLocation("https://twin.example.com/");
    expect(apiBaseUrl()).toBe("");
    expect(wsBaseUrl()).toBe("wss://twin.example.com");

    vi.stubEnv("VITE_API_PORT", "8005");
    expect(apiBaseUrl()).toBe("https://twin.example.com:8005");
    expect(wsBaseUrl()).toBe("wss://twin.example.com:8005");
  });

  it("lets explicit base URLs override everything", () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.com");
    vi.stubEnv("VITE_WS_BASE_URL", "wss://api.example.com");
    setLocation("http://192.168.68.179:3005/");
    expect(apiBaseUrl()).toBe("https://api.example.com");
    expect(wsBaseUrl()).toBe("wss://api.example.com");
  });
});
