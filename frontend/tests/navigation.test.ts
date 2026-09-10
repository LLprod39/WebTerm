import { describe, expect, it } from "vitest";
import {
  canSeeNavigation,
  navigation,
  sectionLanding,
  visibleNavigation,
} from "@/layouts/navigation";
import type { SessionUser } from "@/api/auth";
const user = (features: Record<string, boolean>, staff = false) =>
  ({ features, is_staff: staff }) as SessionUser;
const item = (path: string) =>
  navigation.flatMap((g) => g.items).find((i) => i.path === path)!;
describe("navigation follows independent backend permissions", () => {
  it("does not infer automation or agents access from servers or staff", () => {
    expect(
      canSeeNavigation(
        item("/automation/playbooks"),
        user({ servers: true }, true),
      ),
    ).toBe(false);
    expect(
      canSeeNavigation(
        item("/intelligence/agents"),
        user({ servers: true }, true),
      ),
    ).toBe(false);
  });
  it("respects independent Studio subfeatures and combined runs availability", () => {
    expect(
      canSeeNavigation(item("/intelligence/mcp"), user({ studio_mcp: true })),
    ).toBe(true);
    expect(
      canSeeNavigation(item("/automation/runs"), user({ automation: true })),
    ).toBe(true);
    expect(
      canSeeNavigation(item("/automation/runs"), user({ studio_runs: true })),
    ).toBe(true);
    expect(
      canSeeNavigation(item("/automation/pipelines"), user({ studio: true })),
    ).toBe(false);
  });
  it("requires all plugin administrative capabilities", () => {
    expect(
      canSeeNavigation(
        item("/governance/plugins"),
        user({ plugins: true, settings: true }),
      ),
    ).toBe(false);
    expect(
      canSeeNavigation(
        item("/governance/plugins"),
        user({ plugins: true, settings: true }, true),
      ),
    ).toBe(true);
  });
  it("opens the independently allowed tool instead of a forbidden settings page", () => {
    const mcpOnly = visibleNavigation(user({ studio_mcp: true }));
    expect(mcpOnly.map((group) => group.id)).toEqual(["settings"]);
    expect(sectionLanding(mcpOnly[0]).path).toBe("/settings/integrations");
    expect(mcpOnly[0].items.map((entry) => entry.path)).toEqual([
      "/settings/integrations",
      "/intelligence/mcp",
    ]);
    expect(visibleNavigation(user({ settings: true }))).toEqual([]);
  });
  it("exposes AI routing only with its explicit capability and keeps profiles independent", () => {
    expect(
      canSeeNavigation(item("/settings/ai"), user({ settings: true }, true)),
    ).toBe(false);
    expect(
      canSeeNavigation(item("/settings/ai"), {
        ...user({ settings: true }),
        can_manage_ai_routing: true,
      }),
    ).toBe(true);
    const profileOnly = visibleNavigation(user({ studio_agents: true }));
    expect(profileOnly.map((group) => group.id)).toEqual(["automation"]);
    expect(sectionLanding(profileOnly[0]).path).toBe("/intelligence/profiles");
  });
});
