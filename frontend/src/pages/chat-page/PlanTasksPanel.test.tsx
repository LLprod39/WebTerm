import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { mapStepStatus, planToAgentProgressSteps, PlanTasksPanel } from "./PlanTasksPanel";

describe("PlanTasksPanel status mapping", () => {
  it("maps awaiting_confirm to waiting, not running", () => {
    expect(mapStepStatus("awaiting_confirm")).toBe("waiting");
    expect(mapStepStatus("running")).toBe("running");
    expect(mapStepStatus("done")).toBe("done");
    expect(mapStepStatus("failed")).toBe("error");
    expect(mapStepStatus("pending")).toBe("pending");
  });

  it("downgrades stuck running to waiting when turn is idle", () => {
    const steps = planToAgentProgressSteps(
      {
        title: "Ops",
        steps: [
          { id: 1, text: "Done step", status: "done" },
          { id: 2, text: "Stuck", status: "running" },
        ],
      },
      { turnActive: false },
    );
    expect(steps[1]?.status).toBe("waiting");
  });

  it("keeps running when turn is active", () => {
    const steps = planToAgentProgressSteps(
      { steps: [{ id: 1, text: "Live", status: "running" }] },
      { turnActive: true },
    );
    expect(steps[0]?.status).toBe("running");
  });

  it("renders AgentProgress in controlled mode", () => {
    render(
      <PlanTasksPanel
        plan={{
          title: "Cleanup",
          steps: [
            { id: 1, text: "List files", status: "pending" },
            { id: 2, text: "Confirm delete", status: "awaiting_confirm" },
          ],
        }}
      />,
    );

    expect(screen.getByTestId("agent-progress")).toHaveAttribute("data-controlled", "true");
    expect(screen.getByTestId("agent-progress-waiting")).toBeInTheDocument();
    expect(document.querySelector('[data-step-status="waiting"]')).not.toBeNull();
    expect(document.querySelector(".agent-progress-loading-text")).toBeNull();
  });
});
