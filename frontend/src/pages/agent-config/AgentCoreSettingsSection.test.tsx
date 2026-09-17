import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AgentCoreSettingsSection } from "./AgentFormAccessSections";

describe("AgentCoreSettingsSection model and limits gate", () => {
  it("always shows read-only model and iterations (Settings → AI only)", () => {
    render(
      <AgentCoreSettingsSection
        form={{ name: "Ops", model: "gemini-2.0-flash", max_iterations: 12 }}
        lang="en"
        readOnly={false}
        onFieldChange={vi.fn()}
      />,
    );

    expect(screen.getByText("gemini-2.0-flash")).toBeInTheDocument();
    expect(screen.getByText(/Selection here is not available/i)).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText(/Editing here is not available/i)).toBeInTheDocument();
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });
});
