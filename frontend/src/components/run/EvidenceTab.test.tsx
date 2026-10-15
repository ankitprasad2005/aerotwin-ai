import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { api, defaultHandlers, makeEvidence, makeEvidenceItem } from "../../test/fixtures";
import { server } from "../../test/mswServer";
import { renderWithProviders } from "../../test/render";
import { EvidenceList, EvidenceTab } from "./EvidenceTab";

describe("EvidenceTab", () => {
  it("groups evidence by source with reliability, links, citations and unavailable providers", async () => {
    server.use(...defaultHandlers());
    renderWithProviders(<EvidenceTab runId="run-1" iteration={1} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading evidence");
    await waitFor(() => expect(screen.getByTestId("evidence-list")).toBeInTheDocument());

    const fuel = screen.getByTestId("evidence-group-eia_jet_fuel");
    expect(within(fuel).getByRole("link", { name: "Jet fuel, US Gulf Coast" })).toHaveAttribute(
      "href",
      "https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm",
    );
    expect(within(fuel).getByText("90%")).toBeInTheDocument();
    expect(within(fuel).getAllByText("Network")).toHaveLength(2); // seen by + cited by
    expect(within(fuel).getByText(/usd_per_gallon: 2.31/)).toBeInTheDocument();

    const web = screen.getByTestId("evidence-group-web");
    expect(within(web).getByText("not cited")).toBeInTheDocument();
    expect(within(web).getByText("40%")).toBeInTheDocument();
    expect(screen.getByTestId("evidence-unavailable")).toHaveTextContent("dgca_market: no data");
    // The DGCA group is absent, and group order puts reliable sources first.
    expect(screen.queryByTestId("evidence-group-dgca")).not.toBeInTheDocument();
    const order = screen.getAllByTestId(/^evidence-group-/).map((el) => el.getAttribute("data-testid"));
    expect(order).toEqual(["evidence-group-eia_jet_fuel", "evidence-group-web"]);
  });

  it("only shows the selected iteration's evidence", async () => {
    server.use(
      http.get(api("/api/runs/:id/evidence"), () =>
        HttpResponse.json([
          { ...makeEvidence()[0], iteration: 1 },
          { ...makeEvidence()[0], agent_execution_id: "a9", iteration: 2, evidence: [makeEvidenceItem({ id: "fx:2", source: "fx", title: "USD/INR" })], cited_sources: [], evidence_unavailable: [] },
        ]),
      ),
    );
    renderWithProviders(<EvidenceTab runId="run-1" iteration={2} />);
    await waitFor(() => expect(screen.getByTestId("evidence-group-fx")).toBeInTheDocument());
    expect(screen.queryByTestId("evidence-group-eia_jet_fuel")).not.toBeInTheDocument();
    expect(screen.queryByTestId("evidence-unavailable")).not.toBeInTheDocument();
  });

  it("shows an empty state when no evidence was gathered", async () => {
    server.use(http.get(api("/api/runs/:id/evidence"), () => HttpResponse.json([])));
    renderWithProviders(<EvidenceTab runId="run-1" iteration={1} />);
    expect(await screen.findByText(/No external evidence was gathered/)).toBeInTheDocument();
  });

  it("shows an error with a retry", async () => {
    let calls = 0;
    server.use(
      http.get(api("/api/runs/:id/evidence"), () => {
        calls += 1;
        return calls === 1 ? HttpResponse.json({ detail: "Run not found" }, { status: 404 }) : HttpResponse.json(makeEvidence());
      }),
    );
    renderWithProviders(<EvidenceTab runId="run-1" iteration={1} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Run not found");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByTestId("evidence-list")).toBeInTheDocument());
  });
});

describe("EvidenceList safety and edge cases", () => {
  const base = makeEvidence()[0];

  it("never renders a javascript: URL as a link and shows the title as text", () => {
    renderWithProviders(
      <EvidenceList
        entries={[{ ...base, evidence: [makeEvidenceItem({ id: "web:x", source: "web", kind: "web", title: "<img src=x onerror=alert(1)>", url: "javascript:alert(1)" })] }]}
      />,
    );
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });

  it("renders string content, a missing url and a missing fetched_at", () => {
    renderWithProviders(
      <EvidenceList entries={[{ ...base, evidence: [makeEvidenceItem({ id: "d:1", source: "dgca", url: null, fetched_at: null, content: "Plain text content" })] }]} />,
    );
    expect(screen.getByText("Plain text content")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("flags citations that match no evidence", () => {
    renderWithProviders(<EvidenceList entries={[{ ...base, cited_sources: ["fuel:eia:2026-10-10", "made-up:1"] }]} />);
    expect(screen.getByTestId("evidence-unknown-citations")).toHaveTextContent("made-up:1");
  });

  it("de-duplicates items shared by several agents and lists each agent", () => {
    const fleet = { ...base, agent_execution_id: "a2", agent_type: "FLEET", cited_sources: [], evidence_unavailable: [] };
    renderWithProviders(<EvidenceList entries={[base, fleet]} />);
    const fuel = screen.getByTestId("evidence-group-eia_jet_fuel");
    expect(within(fuel).getAllByRole("row")).toHaveLength(2); // header + one item
    expect(within(fuel).getByText("Fleet")).toBeInTheDocument();
  });

  it("shows unavailable providers even when there is no evidence at all", () => {
    renderWithProviders(<EvidenceList entries={[{ ...base, evidence: [], evidence_unavailable: ["web_search: timeout"], cited_sources: [] }]} />);
    expect(screen.getByTestId("evidence-unavailable")).toHaveTextContent("web_search: timeout");
  });

  it("handles very long titles by wrapping them", () => {
    const title = "T".repeat(600);
    renderWithProviders(<EvidenceList entries={[{ ...base, evidence: [makeEvidenceItem({ title, url: null })] }]} />);
    expect(screen.getByText(title)).toHaveClass("break-words");
  });
});
