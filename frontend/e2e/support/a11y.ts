import AxeBuilder from "@axe-core/playwright";
import { expect, Page } from "@playwright/test";

export type A11yImpact = "serious" | "critical";

export type A11yViolationSummary = {
  id: string;
  impact: A11yImpact;
  nodes: number;
  targets: string[];
};

export type A11yBudget = Record<
  string,
  {
    impact?: A11yImpact;
    maxNodes: number;
  }
>;

function formatSummaries(violations: readonly A11yViolationSummary[]): string {
  if (!violations.length) return "none";
  return violations
    .map((violation) => {
      const targets = violation.targets.length ? ` targets=${violation.targets.join(", ")}` : "";
      return `${violation.id} (${violation.impact}) nodes=${violation.nodes}${targets}`;
    })
    .join("; ");
}

export async function collectSeriousAndCriticalViolations(page: Page): Promise<A11yViolationSummary[]> {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  return results.violations
    .filter((violation) => violation.impact === "serious" || violation.impact === "critical")
    .map((violation) => ({
      id: violation.id,
      impact: violation.impact as A11yImpact,
      nodes: violation.nodes.length,
      targets: violation.nodes.slice(0, 8).flatMap((node) => node.target),
    }));
}

export function expectViolationsWithinBudget(violations: readonly A11yViolationSummary[], budget: A11yBudget): void {
  const critical = violations.filter((violation) => violation.impact === "critical");
  expect(critical, `Critical accessibility violations are never budgeted: ${formatSummaries(critical)}`).toEqual([]);

  const byId = new Map(violations.map((violation) => [violation.id, violation]));
  const unexpected = violations.filter((violation) => !Object.prototype.hasOwnProperty.call(budget, violation.id));

  expect(unexpected, `Unexpected serious/critical violations: ${formatSummaries(unexpected)}`).toEqual([]);

  for (const [id, expected] of Object.entries(budget)) {
    const actual = byId.get(id);
    if (!actual) continue;
    expect(
      actual.nodes,
      `Violation '${id}' exceeded node budget (${expected.maxNodes}); targets=${actual.targets.join(", ")}`,
    ).toBeLessThanOrEqual(expected.maxNodes);
    if (expected.impact) {
      expect(actual.impact, `Violation '${id}' has unexpected impact`).toBe(expected.impact);
    }
  }
}
