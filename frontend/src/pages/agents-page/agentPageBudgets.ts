/** Budget profiles aligned with servers.agents.agent_runtime_guidance.FULL_BUDGET_PROFILES */
export type AgentBudgetProfileId = "quick" | "standard" | "complex";

export const AGENT_BUDGET_PROFILES: Record<
  AgentBudgetProfileId,
  { maxIterations: number; sessionTimeoutSeconds: number; commandTimeout: number; labelRu: string; labelEn: string; descRu: string; descEn: string }
> = {
  quick: {
    maxIterations: 15,
    sessionTimeoutSeconds: 600,
    commandTimeout: 45,
    labelRu: "Быстрый",
    labelEn: "Quick",
    descRu: "Короткие задачи: 15 шагов, 10 мин",
    descEn: "Short tasks: 15 steps, 10 min",
  },
  standard: {
    maxIterations: 40,
    sessionTimeoutSeconds: 1200,
    commandTimeout: 90,
    labelRu: "Стандарт",
    labelEn: "Standard",
    descRu: "Обычные ops: 40 шагов, 20 мин",
    descEn: "Typical ops: 40 steps, 20 min",
  },
  complex: {
    maxIterations: 60,
    sessionTimeoutSeconds: 1800,
    commandTimeout: 120,
    labelRu: "Сложная",
    labelEn: "Complex",
    descRu: "Инциденты / multi-step: 60 шагов, 30 мин",
    descEn: "Incidents / multi-step: 60 steps, 30 min",
  },
};

export function resolveBudgetProfileId(maxIter: number, sessionTimeout: number): AgentBudgetProfileId | "custom" {
  for (const [id, profile] of Object.entries(AGENT_BUDGET_PROFILES) as [AgentBudgetProfileId, (typeof AGENT_BUDGET_PROFILES)[AgentBudgetProfileId]][]) {
    if (profile.maxIterations === maxIter && profile.sessionTimeoutSeconds === sessionTimeout) {
      return id;
    }
  }
  return "custom";
}
