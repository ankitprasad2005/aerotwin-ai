import type { EvidenceItem, RunEvidenceEntry } from "../types/api";

export const SOURCE_LABEL: Record<string, string> = {
  openflights: "OpenFlights routes",
  eia_jet_fuel: "EIA jet fuel",
  fx: "USD/INR rate",
  dgca: "DGCA traffic",
  aviation_weather: "Aviation weather (METAR)",
  open_meteo: "Open-Meteo forecast",
  web: "Web search",
};

export function sourceLabel(source: string): string {
  return SOURCE_LABEL[source] ?? source;
}

export interface GroupedEvidenceItem {
  item: EvidenceItem;
  // Agent types that were given this item (an item can reach several agents).
  seenBy: string[];
  // Agent types that cited this item in their recommendation.
  citedBy: string[];
}

export interface EvidenceGroup {
  source: string;
  label: string;
  items: GroupedEvidenceItem[];
}

const SOURCE_ORDER = ["dgca", "eia_jet_fuel", "fx", "openflights", "aviation_weather", "open_meteo", "web"];

/** Groups evidence by source across agents, de-duplicating items that several agents received
 * (same id) and recording which agents saw and cited each one. Highest-reliability sources come
 * first; unknown sources sort last. */
export function groupEvidence(entries: readonly RunEvidenceEntry[]): EvidenceGroup[] {
  const byId = new Map<string, GroupedEvidenceItem>();
  for (const entry of entries) {
    const cited = new Set(entry.cited_sources);
    for (const item of entry.evidence) {
      let grouped = byId.get(item.id);
      if (!grouped) {
        grouped = { item, seenBy: [], citedBy: [] };
        byId.set(item.id, grouped);
      }
      if (!grouped.seenBy.includes(entry.agent_type)) grouped.seenBy.push(entry.agent_type);
      if (cited.has(item.id) && !grouped.citedBy.includes(entry.agent_type)) grouped.citedBy.push(entry.agent_type);
    }
  }

  const groups = new Map<string, EvidenceGroup>();
  for (const grouped of byId.values()) {
    const source = grouped.item.source;
    if (!groups.has(source)) groups.set(source, { source, label: sourceLabel(source), items: [] });
    groups.get(source)?.items.push(grouped);
  }
  const rank = (source: string) => {
    const index = SOURCE_ORDER.indexOf(source);
    return index === -1 ? SOURCE_ORDER.length : index;
  };
  return [...groups.values()].sort((a, b) => rank(a.source) - rank(b.source));
}

/** Evidence ids cited by an agent that do not appear in any evidence list: a hallucinated or stale
 * citation worth flagging. */
export function unknownCitations(entries: readonly RunEvidenceEntry[]): string[] {
  const known = new Set(entries.flatMap((entry) => entry.evidence.map((item) => item.id)));
  const unknown = new Set<string>();
  for (const entry of entries) {
    for (const id of entry.cited_sources) if (!known.has(id)) unknown.add(id);
  }
  return [...unknown];
}

/** A short single-line preview of an item's content. */
export function contentPreview(content: EvidenceItem["content"], max = 140): string {
  const text =
    typeof content === "string"
      ? content
      : Object.entries(content ?? {})
          .map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : String(value)}`)
          .join(" · ");
  return text.length <= max ? text : `${text.slice(0, max - 1).trimEnd()}…`;
}

/** Only http(s) links are rendered as anchors: web evidence is untrusted, so a `javascript:` URL
 * must never reach an href. */
export function safeHref(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}

/** Whether an evidence entry belongs to the iteration with this sequence. The API reports `null`
 * for executions outside any iteration; the run page shows those as a single prompt, sequence 1. */
export function inIteration(entry: RunEvidenceEntry, sequence: number | undefined): boolean {
  return entry.iteration === sequence || (entry.iteration === null && sequence === 1);
}
