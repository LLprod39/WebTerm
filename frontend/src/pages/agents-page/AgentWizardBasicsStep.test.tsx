import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { AgentWizardBasicsStep } from "./AgentWizardBasicsStep";
import type { AgentMode } from "./agentWizardStepTypes";

function ModeHarness() {
  const [mode, setMode] = useState<AgentMode>("full");

  return (
    <AgentWizardBasicsStep
      lang="ru"
      t={(key) => key}
      mode={mode}
      setMode={setMode}
      name="Диагностика"
      setName={() => undefined}
      commands="hostname"
      setCommands={() => undefined}
      aiPrompt=""
      setAiPrompt={() => undefined}
      goal="Проверить серверы"
      setGoal={() => undefined}
      systemPrompt=""
      setSystemPrompt={() => undefined}
      sudoPolicy="disabled"
      setSudoPolicy={() => undefined}
      sudoRiskAcknowledged={false}
      setSudoRiskAcknowledged={() => undefined}
    />
  );
}

describe("AgentWizardBasicsStep modes", () => {
  it("shows mini, full, and multi modes in the visible first step", () => {
    render(<ModeHarness />);

    expect(screen.getByRole("button", { name: /Мини/ })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: /Полный/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /Мульти/ })).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(screen.getByRole("button", { name: /Мульти/ }));

    expect(screen.getByRole("button", { name: /Мульти/ })).toHaveAttribute("aria-pressed", "true");
  });
});
