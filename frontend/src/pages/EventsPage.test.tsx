import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../test/mswServer";
import { EventsPage } from "./EventsPage";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <EventsPage />
    </QueryClientProvider>,
  );
}

describe("EventsPage", () => {
  it("renders the page title, filters, and table", async () => {
    server.use(http.get("http://localhost:8000/api/events", () => HttpResponse.json([])));
    renderPage();
    expect(screen.getByTestId("page-content")).toBeInTheDocument();
    expect(screen.getByText("EVENTS")).toBeInTheDocument();
    expect(screen.getByLabelText("Severity")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("[NO EVENTS MATCH]")).toBeInTheDocument());
  });

  it("refetches events when a filter changes", async () => {
    let lastSeverity: string | null = null;
    server.use(
      http.get("http://localhost:8000/api/events", ({ request }) => {
        lastSeverity = new URL(request.url).searchParams.get("severity");
        return HttpResponse.json([]);
      }),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("[NO EVENTS MATCH]")).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Severity"), "ERROR");
    await waitFor(() => expect(lastSeverity).toBe("ERROR"));
  });
});
