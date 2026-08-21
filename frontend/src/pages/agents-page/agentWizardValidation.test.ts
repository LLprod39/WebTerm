import { describe, expect, it } from "vitest";

import {
  buildAgentWizardReadiness,
  firstFailedCheckForStep,
  readinessPercent,
  stepHasBlockingFailure,
  type AgentWizardReadinessInput,
  validateAgentWizardSchema,
} from "./agentWizardValidation";

const validInput: AgentWizardReadinessInput = {
  selectedType: "custom",
  mode: "mini",
  name: "Проверка инфраструктуры",
  commands: "uptime",
  goal: "",
  selectedServers: [7],
  targetScope: "servers",
  hasServerDependentTools: false,
  hasServerDependentSkills: false,
  sudoPolicy: "ask",
  sudoRiskAcknowledged: false,
  scheduleConfig: {
    mode: "manual",
    timezone: "UTC",
    interval_minutes: 0,
    time: "09:00",
    weekdays: [0, 1, 2, 3, 4],
    day_of_month: 1,
    run_at: "",
  },
  schedule: 0,
  telegramEnabled: false,
  telegramChatId: "",
};

describe("agent wizard validation", () => {
  it("accepts a runnable manual agent and reports full readiness", () => {
    expect(validateAgentWizardSchema(validInput)).toEqual({ isValid: true, issues: [] });

    const checks = buildAgentWizardReadiness(validInput);
    expect(checks.every((check) => check.passed)).toBe(true);
    expect(readinessPercent(checks)).toBe(100);
    expect(firstFailedCheckForStep(checks, "basics")).toBeUndefined();
    expect(stepHasBlockingFailure(checks, "servers")).toBe(false);
  });

  it("accepts a non-server agent for API, MCP, document, and SaaS work", () => {
    const externalInput: AgentWizardReadinessInput = {
      ...validInput,
      mode: "full",
      commands: "",
      goal: "Собрать отчёт из документов и отправить через подключённый API",
      selectedServers: [],
      targetScope: "external",
      sudoPolicy: "disabled",
    };

    expect(validateAgentWizardSchema(externalInput)).toEqual({ isValid: true, issues: [] });
    expect(buildAgentWizardReadiness(externalInput).find((check) => check.key === "servers")?.passed).toBe(true);
  });

  it("requires a server when an SSH-dependent capability is enabled", () => {
    const externalSshInput: AgentWizardReadinessInput = {
      ...validInput,
      mode: "full",
      commands: "",
      goal: "Проверить журналы",
      selectedServers: [],
      targetScope: "external",
      sudoPolicy: "disabled",
      hasServerDependentTools: true,
    };

    expect(validateAgentWizardSchema(externalSshInput).isValid).toBe(false);
    expect(buildAgentWizardReadiness(externalSshInput).find((check) => check.key === "servers")?.passed).toBe(false);
  });

  it("maps unsafe and incomplete configuration to actionable wizard steps", () => {
    const invalidInput: AgentWizardReadinessInput = {
      ...validInput,
      selectedType: "",
      name: "",
      commands: "rm -rf /tmp/example",
      selectedServers: [],
      sudoPolicy: "approved",
      scheduleConfig: { ...validInput.scheduleConfig, mode: "interval", interval_minutes: 0 },
      telegramEnabled: true,
    };

    const validation = validateAgentWizardSchema(invalidInput);
    expect(validation.isValid).toBe(false);
    expect(validation.issues.map((issue) => issue.step)).toEqual(
      expect.arrayContaining(["template", "basics", "servers", "capabilities"]),
    );

    const checks = buildAgentWizardReadiness(invalidInput);
    expect(firstFailedCheckForStep(checks, "basics")?.key).toBe("behavior");
    expect(stepHasBlockingFailure(checks, "servers")).toBe(true);
    expect(checks.find((check) => check.key === "commands")?.risk).toBe("warning");
    expect(checks.find((check) => check.key === "sudo")?.risk).toBe("danger");
    expect(readinessPercent([])).toBe(0);
  });
});
