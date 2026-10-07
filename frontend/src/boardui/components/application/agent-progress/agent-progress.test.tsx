import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AgentProgress } from "./agent-progress";

describe("AgentProgress", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not auto-advance when controlled with all-pending steps", () => {
    render(
      <AgentProgress
        controlled
        steps={[
          { id: 1, label: "Check disk", status: "pending" },
          { id: 2, label: "Restart nginx", status: "pending" },
        ]}
      />,
    );

    expect(screen.getByTestId("agent-progress")).toHaveAttribute("data-controlled", "true");
    expect(screen.getByText("2 steps left")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(10_000);
    });

    expect(screen.getByText("2 steps left")).toBeInTheDocument();
    expect(screen.queryByText("All steps complete")).not.toBeInTheDocument();
    expect(document.querySelector('[data-step-status="running"]')).toBeNull();
  });

  it("does not auto-advance when autoDemo is false", () => {
    render(
      <AgentProgress
        autoDemo={false}
        steps={[
          { id: 1, label: "A", status: "pending" },
          { id: 2, label: "B", status: "pending" },
        ]}
      />,
    );

    act(() => {
      vi.advanceTimersByTime(5_000);
    });

    expect(screen.getByText("2 steps left")).toBeInTheDocument();
  });

  it("auto-advances demo mode for string steps", () => {
    render(<AgentProgress steps={["One", "Two"]} stepDuration={1000} />);

    expect(screen.getByTestId("agent-progress")).toHaveAttribute("data-controlled", "false");
    expect(document.querySelector('[data-step-status="running"]')).not.toBeNull();

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByText("1 step left")).toBeInTheDocument();
  });

  it("renders waiting glyph without execution spinner class", () => {
    render(
      <AgentProgress
        controlled
        steps={[{ id: 1, label: "Confirm restart", status: "waiting" }]}
      />,
    );

    expect(screen.getByTestId("agent-progress-waiting")).toBeInTheDocument();
    expect(document.querySelector(".agent-progress-loading-text")).toBeNull();
  });
});
