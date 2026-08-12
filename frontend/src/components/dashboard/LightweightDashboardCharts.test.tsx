import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  AgentRunsChart,
  HourlyActivityChart,
} from "./LightweightDashboardCharts";

describe("lightweight dashboard charts", () => {
  it("exposes agent-run chart values as an accessible table", () => {
    render(
      <AgentRunsChart
        data={[{ date: "2026-08-11", succeeded: 3, failed: 1 }]}
        formatDay={() => "11/08"}
        lang="en"
      />,
    );

    expect(screen.getByRole("img", { name: "Agent runs by day" })).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Agent run data" });
    expect(within(table).getByRole("cell", { name: "3" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "1" })).toBeInTheDocument();
  });

  it("exposes hourly activity without loading the charting runtime", () => {
    render(
      <HourlyActivityChart
        data={[{ hour: "2026-08-11T12:00:00Z", count: 7 }]}
        formatHour={() => "12:00"}
        lang="en"
      />,
    );

    expect(screen.getByRole("img", { name: "Hourly system activity" })).toBeInTheDocument();
    expect(within(screen.getByRole("table", { name: "Hourly activity data" })).getByRole("cell", { name: "7" })).toBeInTheDocument();
  });
});
