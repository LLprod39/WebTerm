import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LlmQueryConfig } from "./AgentConfigSections";

const baseProps = {
  type: "agent/llm_query",
  data: { prompt: "Summarize", provider: "auto" },
  lang: "en" as const,
  nodeId: "llm_summary",
  provider: "auto",
  modelList: [],
  loadingModelsFor: null,
  onSet: vi.fn(),
  onProviderChange: vi.fn(),
};

describe("LlmQueryConfig AI routing policy", () => {
  it("hides provider and model controls from ordinary users", () => {
    render(<LlmQueryConfig {...baseProps} canSelectModels={false} />);

    expect(screen.getByText(/Uses the workspace default agent model from settings/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Provider$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Model$/)).not.toBeInTheDocument();
  });

  it("lets policy admins keep workspace routing selected", () => {
    render(<LlmQueryConfig {...baseProps} canSelectModels />);

    expect(screen.getByText(/^Provider$/)).toBeInTheDocument();
    expect(screen.getAllByRole("combobox")[0]).toHaveTextContent("Auto");
  });
});
