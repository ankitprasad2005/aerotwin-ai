import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../test/mswServer";
import { ApiError, apiFetch } from "./client";

describe("apiFetch", () => {
  it("returns parsed JSON on success", async () => {
    server.use(http.get("http://localhost:8000/api/health", () => HttpResponse.json({ status: "ok" })));
    const result = await apiFetch<{ status: string }>("/api/health");
    expect(result).toEqual({ status: "ok" });
  });

  it("throws ApiError on a non-ok response", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/missing", () =>
        HttpResponse.json({ detail: "run not found" }, { status: 404 }),
      ),
    );
    await expect(apiFetch("/api/runs/missing")).rejects.toThrow(ApiError);
  });

  it("ApiError carries the HTTP status code", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/missing", () =>
        HttpResponse.json({ detail: "run not found" }, { status: 404 }),
      ),
    );
    try {
      await apiFetch("/api/runs/missing");
      throw new Error("expected apiFetch to throw");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).status).toBe(404);
    }
  });

  it("returns undefined for a 204 No Content response", async () => {
    server.use(http.post("http://localhost:8000/api/noop", () => new HttpResponse(null, { status: 204 })));
    const result = await apiFetch("/api/noop", { method: "POST" });
    expect(result).toBeUndefined();
  });

  it("sends a JSON Content-Type header by default", async () => {
    let receivedContentType: string | null = null;
    server.use(
      http.post("http://localhost:8000/api/echo", ({ request }) => {
        receivedContentType = request.headers.get("content-type");
        return HttpResponse.json({ ok: true });
      }),
    );
    await apiFetch("/api/echo", { method: "POST", body: JSON.stringify({ a: 1 }) });
    expect(receivedContentType).toContain("application/json");
  });
});
