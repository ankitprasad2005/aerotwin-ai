import { describe, expect, it } from "vitest";
import { useConnectionStore } from "./connectionStore";

describe("connectionStore", () => {
  it("defaults to connecting", () => {
    useConnectionStore.setState({ status: "connecting" });
    expect(useConnectionStore.getState().status).toBe("connecting");
  });

  it("setStatus updates the status", () => {
    useConnectionStore.getState().setStatus("open");
    expect(useConnectionStore.getState().status).toBe("open");
  });
});
