import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

class FakeWebSocket {
  onopen: (() => void) | null = null;
  onmessage: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  url: string;

  constructor(url: string) {
    this.url = url;
  }

  close() {
    // no-op for App-level rendering tests
  }
}

beforeEach(() => {
  vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderApp(initialPath = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("App", () => {
  it("renders the sidebar, header, and dashboard route by default", () => {
    renderApp("/");
    expect(screen.getByRole("heading", { name: "DASHBOARD" })).toBeInTheDocument();
    expect(screen.getByText("+ NEW RUN")).toBeInTheDocument();
    expect(screen.getByTestId("page-content")).toHaveTextContent("DASHBOARD");
  });

  it("renders the orchestration page at /orchestration", () => {
    renderApp("/orchestration");
    expect(screen.getByTestId("page-content")).toHaveTextContent("ORCHESTRATION");
  });

  it("renders the events page at /events", () => {
    renderApp("/events");
    expect(screen.getByTestId("page-content")).toHaveTextContent("EVENTS");
  });
});
