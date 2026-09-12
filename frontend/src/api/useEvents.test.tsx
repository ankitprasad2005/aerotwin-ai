import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../test/mswServer";
import { createQueryWrapper } from "../test/renderWithQueryClient";
import { useEvents } from "./useEvents";

describe("useEvents", () => {
  it("fetches events with no filters", async () => {
    server.use(
      http.get("http://localhost:8000/api/events", ({ request }) => {
        const url = new URL(request.url);
        expect(url.search).toBe("");
        return HttpResponse.json([]);
      }),
    );
    const { result } = renderHook(() => useEvents({}), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([]);
  });

  it("passes filters as query params", async () => {
    server.use(
      http.get("http://localhost:8000/api/events", ({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.get("run_id")).toBe("2");
        expect(url.searchParams.get("severity")).toBe("ERROR");
        return HttpResponse.json([
          {
            id: "7",
            run_id: "2",
            agent_execution_id: null,
            event_type: "tool.failed",
            severity: "ERROR",
            entity_type: null,
            entity_id: null,
            payload: {},
            created_at: "2026-09-11T00:00:00Z",
          },
        ]);
      }),
    );
    const { result } = renderHook(() => useEvents({ run_id: "2", severity: "ERROR" }), {
      wrapper: createQueryWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
  });

  it("omits undefined filter values from the query string", async () => {
    server.use(
      http.get("http://localhost:8000/api/events", ({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.has("event_type")).toBe(false);
        expect(url.searchParams.get("limit")).toBe("50");
        return HttpResponse.json([]);
      }),
    );
    const { result } = renderHook(() => useEvents({ event_type: undefined, limit: 50 }), {
      wrapper: createQueryWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});
