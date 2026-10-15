import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Badge, Chip, ReliabilityBar, RiskBadge, VerdictBadge } from "./Badge";

describe("Badge and Chip", () => {
  it("render children with the tone class and title", () => {
    render(
      <>
        <Badge tone="bad" title="why">
          Bad
        </Badge>
        <Badge>Plain</Badge>
        <Chip title="full id" tone="accent">
          fuel:eia
        </Chip>
        <Chip>web:1</Chip>
      </>,
    );
    expect(screen.getByText("Bad")).toHaveClass("text-bad");
    expect(screen.getByText("Bad")).toHaveAttribute("title", "why");
    expect(screen.getByText("Plain")).toHaveClass("text-muted");
    expect(screen.getByText("fuel:eia")).toHaveAttribute("title", "full id");
    expect(screen.getByText("web:1")).toBeInTheDocument();
  });
});

describe("VerdictBadge", () => {
  it.each([
    ["RECOMMEND", "Recommend", "text-ok"],
    ["REVIEW", "Review", "text-warn"],
    ["REJECT", "Reject", "text-bad"],
  ] as const)("renders %s", (verdict, label, tone) => {
    render(<VerdictBadge verdict={verdict} />);
    expect(screen.getByText(label)).toHaveClass(tone);
  });

  it("renders a dash for a decision without a verdict", () => {
    const { rerender } = render(<VerdictBadge verdict={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    rerender(<VerdictBadge verdict={undefined} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("explains the verdict in a tooltip when asked", async () => {
    render(<VerdictBadge verdict="REVIEW" withHelp />);
    await userEvent.hover(screen.getByText("Review"));
    expect(screen.getByRole("tooltip")).toHaveTextContent(/human should look/);
  });
});

describe("RiskBadge", () => {
  it("colours known levels and falls back to muted for others", () => {
    const { rerender } = render(<RiskBadge risk="HIGH" />);
    expect(screen.getByText("HIGH")).toHaveClass("text-bad");
    rerender(<RiskBadge risk="LOW" />);
    expect(screen.getByText("LOW")).toHaveClass("text-ok");
    rerender(<RiskBadge risk="WEIRD" />);
    expect(screen.getByText("WEIRD")).toHaveClass("text-muted");
  });
  it("renders a dash when there is no risk", () => {
    render(<RiskBadge risk={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});

describe("ReliabilityBar", () => {
  it.each([
    [0.95, "bg-ok", "95%"],
    [0.6, "bg-accent", "60%"],
    [0.4, "bg-warn", "40%"],
  ])("colours %s", (value, color, text) => {
    const { container } = render(<ReliabilityBar value={value} />);
    expect(screen.getByText(text)).toBeInTheDocument();
    expect(container.querySelector(`.${color}`)).not.toBeNull();
  });

  it("clamps and survives bad values", () => {
    const { rerender } = render(<ReliabilityBar value={3} />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "100");
    rerender(<ReliabilityBar value={Number.NaN} />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "0");
  });
});
