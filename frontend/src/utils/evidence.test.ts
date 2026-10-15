import { describe, expect, it } from "vitest";
import type { EvidenceItem, RunEvidenceEntry } from "../types/api";
import { contentPreview, groupEvidence, safeHref, sourceLabel, unknownCitations } from "./evidence";

function item(id: string, source: EvidenceItem["source"], reliability = 0.5): EvidenceItem {
  return { id, source, kind: source === "web" ? "web" : "dataset", title: id, url: null, fetched_at: null, reliability, content: "x" };
}

function entry(agent_type: string, evidence: EvidenceItem[], cited_sources: string[] = []): RunEvidenceEntry {
  return { agent_execution_id: agent_type, agent_type, iteration: 1, evidence, evidence_unavailable: [], cited_sources };
}

describe("groupEvidence", () => {
  it("returns no groups for no entries or entries without evidence", () => {
    expect(groupEvidence([])).toEqual([]);
    expect(groupEvidence([entry("NETWORK", [])])).toEqual([]);
  });

  it("groups by source in reliability order, with unknown sources last", () => {
    const weird = { ...item("w", "web"), source: "mystery" } as unknown as EvidenceItem;
    const groups = groupEvidence([
      entry("NETWORK", [item("web:1", "web"), item("fuel:1", "eia_jet_fuel"), item("dgca:1", "dgca"), weird]),
    ]);
    expect(groups.map((g) => g.source)).toEqual(["dgca", "eia_jet_fuel", "web", "mystery"]);
    expect(groups[3].label).toBe("mystery");
  });

  it("de-duplicates items shared by agents and records who saw and cited them", () => {
    const shared = item("fuel:1", "eia_jet_fuel");
    const groups = groupEvidence([
      entry("NETWORK", [shared], ["fuel:1"]),
      entry("FLEET", [shared], []),
      entry("CARGO", [shared], ["fuel:1"]),
      entry("CARGO", [shared], ["fuel:1"]),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].items).toHaveLength(1);
    expect(groups[0].items[0].seenBy).toEqual(["NETWORK", "FLEET", "CARGO"]);
    expect(groups[0].items[0].citedBy).toEqual(["NETWORK", "CARGO"]);
  });
});

describe("unknownCitations", () => {
  it("lists cited ids that no agent was given, once each", () => {
    const entries = [entry("NETWORK", [item("a", "web")], ["a", "ghost"]), entry("FLEET", [], ["ghost", "ghost2"])];
    expect(unknownCitations(entries)).toEqual(["ghost", "ghost2"]);
    expect(unknownCitations([])).toEqual([]);
  });
});

describe("contentPreview", () => {
  it("returns strings as-is and flattens objects", () => {
    expect(contentPreview("hello")).toBe("hello");
    expect(contentPreview({ price: 2.1, nested: { a: 1 } })).toBe('price: 2.1 · nested: {"a":1}');
  });
  it("truncates long content", () => {
    expect(contentPreview("a".repeat(500), 20)).toHaveLength(20);
  });
  it("tolerates null content", () => {
    expect(contentPreview(null as unknown as string)).toBe("");
  });
});

describe("safeHref", () => {
  it("allows http and https only", () => {
    expect(safeHref("https://example.com/a")).toBe("https://example.com/a");
    expect(safeHref("http://example.com")).toBe("http://example.com/");
    expect(safeHref("javascript:alert(1)")).toBeNull();
    expect(safeHref("data:text/html,x")).toBeNull();
    expect(safeHref("not a url")).toBeNull();
    expect(safeHref(null)).toBeNull();
    expect(safeHref("")).toBeNull();
  });
});

describe("sourceLabel", () => {
  it("maps known sources and falls back to the raw name", () => {
    expect(sourceLabel("fx")).toBe("USD/INR rate");
    expect(sourceLabel("other")).toBe("other");
  });
});
