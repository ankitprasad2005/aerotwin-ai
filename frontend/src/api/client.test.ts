import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../test/mswServer";
import { ApiError, apiFetch, shouldRetryQuery } from "./client";

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

  it("falls back to statusText when the error response body is empty", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/broken", () => new HttpResponse(null, { status: 500 })),
    );
    await expect(apiFetch("/api/runs/broken")).rejects.toMatchObject({ status: 500 });
  });

  it("unwraps a FastAPI-style {detail} JSON error body into a plain message", async () => {
    server.use(
      http.get("http://localhost:8000/api/runs/missing", () =>
        HttpResponse.json({ detail: "run not found" }, { status: 404 }),
      ),
    );
    await expect(apiFetch("/api/runs/missing")).rejects.toThrow("run not found");
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

  it("omits Content-Type on a bodiless GET so cross-origin reads need no CORS preflight", async () => {
    let receivedContentType: string | null = "unset";
    server.use(
      http.get("http://localhost:8000/api/health", ({ request }) => {
        receivedContentType = request.headers.get("content-type");
        return HttpResponse.json({ status: "ok" });
      }),
    );
    await apiFetch("/api/health");
    expect(receivedContentType).toBeNull();
  });

  it("keeps caller-supplied headers, including a Headers instance and an explicit Content-Type", async () => {
    let received: { custom: string | null; contentType: string | null } = { custom: null, contentType: null };
    server.use(
      http.post("http://localhost:8000/api/echo", ({ request }) => {
        received = { custom: request.headers.get("x-custom"), contentType: request.headers.get("content-type") };
        return HttpResponse.json({ ok: true });
      }),
    );
    await apiFetch("/api/echo", {
      method: "POST",
      body: "plain",
      headers: new Headers({ "X-Custom": "1", "Content-Type": "text/plain" }),
    });
    expect(received).toEqual({ custom: "1", contentType: "text/plain" });
  });
});

describe("shouldRetryQuery", () => {
  it("never retries a 4xx ApiError", () => {
    expect(shouldRetryQuery(0, new ApiError(404, "agent execution not found"))).toBe(false);
    expect(shouldRetryQuery(0, new ApiError(422, "invalid run_id"))).toBe(false);
  });

  it("retries 5xx and network errors up to 3 times", () => {
    expect(shouldRetryQuery(0, new ApiError(500, "boom"))).toBe(true);
    expect(shouldRetryQuery(2, new TypeError("Failed to fetch"))).toBe(true);
    expect(shouldRetryQuery(3, new ApiError(503, "unavailable"))).toBe(false);
  });
});
