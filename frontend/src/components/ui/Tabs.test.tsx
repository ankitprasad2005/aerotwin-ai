import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { TabPanel, Tabs } from "./Tabs";

const TABS = [
  { key: "a", label: "Alpha" },
  { key: "b", label: "Beta", badge: 3 },
  { key: "c", label: "Gamma", badge: 0 },
] as const;

function Harness({ onChange }: { onChange?: (key: string) => void }) {
  const [active, setActive] = useState<"a" | "b" | "c">("a");
  return (
    <>
      <Tabs
        label="Sections"
        tabs={TABS}
        active={active}
        onChange={(key) => {
          setActive(key);
          onChange?.(key);
        }}
      />
      <TabPanel id={active}>panel {active}</TabPanel>
    </>
  );
}

describe("Tabs", () => {
  it("renders an accessible tablist with the active tab selected", () => {
    render(<Harness />);
    expect(screen.getByRole("tablist", { name: "Sections" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Alpha" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /Beta/ })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", "tab-a");
  });

  it("shows badges, including a zero count", () => {
    render(<Harness />);
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("switches on click", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await userEvent.click(screen.getByRole("tab", { name: /Beta/ }));
    expect(onChange).toHaveBeenCalledWith("b");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("panel b");
  });

  it("uses a roving tabindex", () => {
    render(<Harness />);
    expect(screen.getByRole("tab", { name: "Alpha" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tab", { name: /Beta/ })).toHaveAttribute("tabindex", "-1");
  });

  it("moves with the arrow keys, wrapping around, and with Home and End", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("tab", { name: "Alpha" }));
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: /Beta/ })).toHaveFocus();
    expect(screen.getByRole("tab", { name: /Beta/ })).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{ArrowRight}{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Alpha" })).toHaveFocus();
    await userEvent.keyboard("{ArrowLeft}");
    expect(screen.getByRole("tab", { name: /Gamma/ })).toHaveFocus();
    await userEvent.keyboard("{Home}");
    expect(screen.getByRole("tab", { name: "Alpha" })).toHaveFocus();
    await userEvent.keyboard("{End}");
    expect(screen.getByRole("tab", { name: /Gamma/ })).toHaveFocus();
  });

  it("ignores other keys", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await userEvent.click(screen.getByRole("tab", { name: "Alpha" }));
    onChange.mockClear();
    await userEvent.keyboard("x");
    expect(onChange).not.toHaveBeenCalled();
  });
});
