import { describe, expect, it } from "vitest";
import { useDebugStore } from "./debugStore";

describe("debugStore", () => {
  it("defaults to disabled", () => {
    useDebugStore.setState({ enabled: false });
    expect(useDebugStore.getState().enabled).toBe(false);
  });

  it("toggle flips the enabled flag", () => {
    useDebugStore.setState({ enabled: false });
    useDebugStore.getState().toggle();
    expect(useDebugStore.getState().enabled).toBe(true);
    useDebugStore.getState().toggle();
    expect(useDebugStore.getState().enabled).toBe(false);
  });
});
