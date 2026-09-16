import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../test/mswServer";
import { createQueryWrapper } from "../test/renderWithQueryClient";
import { useAddRunPrompt, useCreateRun, useRunDetail, useRunGraph, useRunKnowledgeGraph, useRuns } from "./useRuns";

describe("useRuns", () => {
  it("fetches and returns the run list", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs", () =>
        HttpResponse.json([
          { id: "1", objective: "x", status: "COMPLETED", created_at: "2026-09-11T00:00:00Z", completed_at: null },
        ]),
      ),
    );
    const { result } = renderHook(() => useRuns(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
  });

  it("surfaces an error state when the request fails", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
    );
    const { result } = renderHook(() => useRuns(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useRunDetail", () => {
  it("does not fetch when runId is undefined", () => {
    const { result } = renderHook(() => useRunDetail(undefined), { wrapper: createQueryWrapper() });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("fetches run detail when runId is provided", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/1", () =>
        HttpResponse.json({
          id: "1",
          objective: "x",
          status: "COMPLETED",
          created_at: "2026-09-11T00:00:00Z",
          completed_at: null,
          agent_executions: [],
          decision: null,
        }),
      ),
    );
    const { result } = renderHook(() => useRunDetail("1"), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe("1");
  });
});

describe("useRunGraph", () => {
  it("fetches the run graph", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/1/graph", () =>
        HttpResponse.json({
          nodes: [{ id: "orchestrator", type: "ORCHESTRATOR", status: "COMPLETED" }],
          edges: [],
        }),
      ),
    );
    const { result } = renderHook(() => useRunGraph("1"), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.nodes).toHaveLength(1);
  });
});

describe("useCreateRun", () => {
  it("posts the objective and returns the created run", async () => {
    server.use(
      http.post("http://localhost:8000/api/runs", async ({ request }) => {
        const body = (await request.json()) as { objective: string };
        return HttpResponse.json({
          id: "2",
          objective: body.objective,
          status: "COMPLETED",
          created_at: "2026-09-11T00:00:00Z",
          completed_at: "2026-09-11T00:00:05Z",
        });
      }),
    );
    const { result } = renderHook(() => useCreateRun(), { wrapper: createQueryWrapper() });
    result.current.mutate("Improve profitability");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.objective).toBe("Improve profitability");
  });

  it("surfaces an error state when run creation fails", async () => {
    server.use(
      http.post("http://localhost:8000/api/runs", () => HttpResponse.json({ detail: "boom" }, { status: 422 })),
    );
    const { result } = renderHook(() => useCreateRun(), { wrapper: createQueryWrapper() });
    result.current.mutate("");
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useRunKnowledgeGraph", () => {
  it("fetches the run's knowledge graph", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/7/knowledge-graph", () =>
        HttpResponse.json({
          nodes: [{ id: "agent-a1", type: "AGENT", label: "NETWORK AGENT", detail: "COMPLETED" }],
          edges: [{ source: "agent-a1", target: "route-DEL-BOM", label: "knows" }],
        }),
      ),
    );
    const { result } = renderHook(() => useRunKnowledgeGraph("7"), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.nodes[0].label).toBe("NETWORK AGENT");
  });

  it("does not fetch without a run id", async () => {
    const { result } = renderHook(() => useRunKnowledgeGraph(undefined), { wrapper: createQueryWrapper() });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("useAddRunPrompt", () => {
  it("posts a follow-up prompt to the run", async () => {
    let received: unknown = null;
    server.use(
      http.post("http://localhost:8000/api/runs/7/prompts", async ({ request }) => {
        received = await request.json();
        return HttpResponse.json({
          id: "7",
          objective: "Improve profitability",
          status: "COMPLETED",
          created_at: "2026-09-11T00:00:00Z",
          completed_at: "2026-09-11T00:01:00Z",
        });
      }),
    );
    const { result } = renderHook(() => useAddRunPrompt("7"), { wrapper: createQueryWrapper() });

    result.current.mutate("Protect load factor");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(received).toEqual({ objective: "Protect load factor" });
  });
});
