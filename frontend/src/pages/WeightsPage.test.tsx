import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse, type HttpHandler } from "msw";
import { describe, expect, it } from "vitest";
import { api, defaultHandlers, makeWeights } from "../test/fixtures";
import { server } from "../test/mswServer";
import { renderWithProviders } from "../test/render";
import { WeightsPage } from "./WeightsPage";

async function renderLoaded(...overrides: HttpHandler[]) {
  server.use(...defaultHandlers());
  server.use(...overrides);
  renderWithProviders(<WeightsPage />);
  await screen.findByRole("heading", { name: "Decision weights" });
}

const save = () => screen.getByRole("button", { name: "Save weights" });

describe("WeightsPage", () => {
  it("shows a loading state, then every weight, threshold and the profit scale", async () => {
    server.use(...defaultHandlers());
    renderWithProviders(<WeightsPage />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading weights");
    await screen.findByRole("heading", { name: "Decision weights" });
    expect(screen.getByLabelText("Profit weight")).toHaveValue(0.3);
    expect(screen.getByLabelText("Data quality weight")).toHaveValue(0.1);
    expect(screen.getByLabelText("Network weight")).toHaveValue(0.35);
    expect(screen.getByLabelText("Cargo weight")).toHaveValue(0.15);
    expect(screen.getByLabelText("Recommend at or above")).toHaveValue(70);
    expect(screen.getByLabelText("Review at or above")).toHaveValue(45);
    expect(screen.getByLabelText("Profit scale (USD / week)")).toHaveValue(10000);
    expect(screen.getByText(/Last saved/)).toBeInTheDocument();
    expect(screen.getByTestId("threshold-preview")).toBeInTheDocument();
    expect(save()).toBeDisabled();
    expect(screen.getByRole("button", { name: "Discard changes" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reset to defaults" })).toBeDisabled();
  });

  it("omits the saved-at label when the weights were never saved", async () => {
    server.use(http.get(api("/api/decision-weights"), () => HttpResponse.json({ ...makeWeights(), updated_at: null })), ...defaultHandlers());
    renderWithProviders(<WeightsPage />);
    await screen.findByRole("heading", { name: "Decision weights" });
    expect(screen.queryByText(/Last saved/)).not.toBeInTheDocument();
  });

  it("updates the normalised preview live and flags unsaved changes", async () => {
    await renderLoaded();
    expect(screen.getByRole("meter", { name: "Profit" })).toHaveAttribute("aria-valuenow", "30");
    fireEvent.change(screen.getByLabelText("Profit weight"), { target: { value: "0.7" } });
    // 0.7 / (0.7 + 0.2 + 0.25 + 0.15 + 0.1) = 0.5
    expect(screen.getByRole("meter", { name: "Profit" })).toHaveAttribute("aria-valuenow", "50");
    expect(screen.getByTestId("share-profit")).toHaveTextContent("50%");
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    expect(save()).toBeEnabled();
  });

  it("saves the edited weights without updated_at and confirms", async () => {
    let body: Record<string, unknown> | null = null;
    await renderLoaded(
      http.put(api("/api/decision-weights"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...body, updated_at: "2026-10-16T09:00:00Z" });
      }),
    );
    fireEvent.change(screen.getByLabelText("Cargo weight slider"), { target: { value: "0.5" } });
    fireEvent.change(screen.getByLabelText("Recommend at or above"), { target: { value: "80" } });
    await userEvent.click(save());
    expect(await screen.findByText("Weights saved. New runs will use them.")).toBeInTheDocument();
    expect(body).not.toHaveProperty("updated_at");
    expect((body as unknown as { agent_employee?: unknown }).agent_employee).toBeUndefined();
    expect((body as unknown as { agent_confidence: { CARGO: number } }).agent_confidence.CARGO).toBe(0.5);
    expect((body as unknown as { thresholds: { recommend: number } }).thresholds.recommend).toBe(80);
    expect(save()).toBeDisabled();
    expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
  });

  it("blocks saving and lists every problem when thresholds are inverted", async () => {
    await renderLoaded();
    fireEvent.change(screen.getByLabelText("Review at or above"), { target: { value: "90" } });
    expect(screen.getByTestId("weights-errors")).toHaveTextContent("The review threshold must be lower than the recommend threshold.");
    expect(save()).toBeDisabled();
    expect(screen.getByText("Fix the thresholds to preview the score zones.")).toBeInTheDocument();
  });

  it("rejects out-of-range thresholds, a non-positive profit scale and cleared fields", async () => {
    await renderLoaded();
    fireEvent.change(screen.getByLabelText("Recommend at or above"), { target: { value: "150" } });
    fireEvent.change(screen.getByLabelText("Review at or above"), { target: { value: "-5" } });
    fireEvent.change(screen.getByLabelText("Profit scale (USD / week)"), { target: { value: "0" } });
    const errors = screen.getByTestId("weights-errors");
    expect(errors).toHaveTextContent("cannot exceed 100");
    expect(errors).toHaveTextContent("cannot be below 0");
    expect(errors).toHaveTextContent("profit scale must be greater than zero");
    fireEvent.change(screen.getByLabelText("Profit scale (USD / week)"), { target: { value: "" } });
    expect(screen.getByLabelText("Profit scale (USD / week)")).toHaveValue(null);
    expect(errors).toHaveTextContent("profit scale must be greater than zero");
    fireEvent.change(screen.getByLabelText("Review at or above"), { target: { value: "" } });
    expect(screen.getByTestId("weights-errors")).toHaveTextContent("Thresholds must be numbers.");
    expect(save()).toBeDisabled();
  });

  it("rejects negative and all-zero weights", async () => {
    await renderLoaded();
    fireEvent.change(screen.getByLabelText("Fleet weight"), { target: { value: "-1" } });
    expect(screen.getByTestId("weights-errors")).toHaveTextContent("Agent confidence weights: weights cannot be negative.");
    for (const name of ["Profit", "Confidence", "Feasibility", "Risk", "Data quality"]) {
      fireEvent.change(screen.getByLabelText(`${name} weight`), { target: { value: "0" } });
    }
    expect(screen.getByTestId("weights-errors")).toHaveTextContent("Factor weights: at least one weight must be greater than zero.");
    expect(screen.getByTestId("share-profit")).toHaveTextContent("0%");
    expect(save()).toBeDisabled();
  });

  it("shows the server's validation message when it rejects the weights", async () => {
    await renderLoaded(
      http.put(api("/api/decision-weights"), () =>
        HttpResponse.json({ detail: [{ msg: "unknown factor key" }] }, { status: 422 }),
      ),
    );
    fireEvent.change(screen.getByLabelText("Profit weight"), { target: { value: "0.4" } });
    await userEvent.click(save());
    expect(await screen.findByTestId("weights-server-error")).toHaveTextContent("The server rejected the weights: unknown factor key");
    expect(screen.queryByText(/Weights saved/)).not.toBeInTheDocument();
    // Editing again clears the stale server error.
    fireEvent.change(screen.getByLabelText("Profit weight"), { target: { value: "0.5" } });
    expect(screen.queryByTestId("weights-server-error")).not.toBeInTheDocument();
  });

  it("discards edits and resets to the defaults", async () => {
    await renderLoaded(
      http.get(api("/api/decision-weights"), () =>
        HttpResponse.json({ ...makeWeights(), thresholds: { recommend: 60, review: 30 }, profit_scale_usd: 5000 }),
      ),
    );
    expect(screen.getByRole("button", { name: "Reset to defaults" })).toBeEnabled();
    fireEvent.change(screen.getByLabelText("Risk weight"), { target: { value: "0.9" } });
    await userEvent.click(screen.getByRole("button", { name: "Discard changes" }));
    expect(screen.getByLabelText("Risk weight")).toHaveValue(0.15);
    expect(screen.getByLabelText("Recommend at or above")).toHaveValue(60);

    await userEvent.click(screen.getByRole("button", { name: "Reset to defaults" }));
    expect(screen.getByLabelText("Recommend at or above")).toHaveValue(70);
    expect(screen.getByLabelText("Profit scale (USD / week)")).toHaveValue(10000);
    expect(save()).toBeEnabled();
  });

  it("shows an error with retry when the weights cannot be loaded", async () => {
    let calls = 0;
    server.use(
      http.get(api("/api/decision-weights"), () => {
        calls += 1;
        return calls === 1 ? HttpResponse.json({ detail: "db down" }, { status: 500 }) : HttpResponse.json(makeWeights());
      }),
    );
    renderWithProviders(<WeightsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("db down");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByRole("heading", { name: "Decision weights" });
  });

  it("keeps unsaved edits when the saved weights are refetched unchanged", async () => {
    await renderLoaded();
    fireEvent.change(screen.getByLabelText("Profit weight"), { target: { value: "0.6" } });
    await waitFor(() => expect(screen.getByLabelText("Profit weight")).toHaveValue(0.6));
  });
});
