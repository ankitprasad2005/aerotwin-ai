import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { api } from "../test/fixtures";
import { server } from "../test/mswServer";
import { renderWithProviders } from "../test/render";
import { EventsPage } from "./EventsPage";

describe("EventsPage", () => {
  it("renders the page title, filters, and table", async () => {
    server.use(http.get(api("/api/events"), () => HttpResponse.json([])));
    renderWithProviders(<EventsPage />);
    expect(screen.getByTestId("page-content")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Events" })).toBeInTheDocument();
    expect(screen.getByLabelText("Severity")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("No events match")).toBeInTheDocument());
  });

  it("refetches events when a filter changes", async () => {
    let lastSeverity: string | null = null;
    server.use(
      http.get(api("/api/events"), ({ request }) => {
        lastSeverity = new URL(request.url).searchParams.get("severity");
        return HttpResponse.json([]);
      }),
    );
    renderWithProviders(<EventsPage />);
    await waitFor(() => expect(screen.getByText("No events match")).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Severity"), "ERROR");
    await waitFor(() => expect(lastSeverity).toBe("ERROR"));
  });
});
