import { describe, expect, it } from "vitest";

import { visibleSettingsNavGroups } from "./settings-nav-items";
import type { AuthUser } from "@/lib/api";
import { featureMap } from "@/test/featureFlags";

function user(
  isAdmin: boolean,
  features = featureMap({ settings: true, plugins: true }),
  canManageAiRouting = isAdmin,
): AuthUser {
  return {
    id: 1,
    username: "pilot",
    email: "pilot@example.test",
    is_staff: isAdmin,
    can_manage_ai_routing: canManageAiRouting,
    features,
  };
}

function visibleItemIds(authUser: AuthUser, pluginsEnabled: boolean) {
  return visibleSettingsNavGroups(authUser, pluginsEnabled).flatMap((group) =>
    group.items.map((item) => item.id),
  );
}

describe("settings navigation release capabilities", () => {
  it("hides plugins from an admin when the release profile is disabled", () => {
    expect(visibleItemIds(user(true), false)).not.toContain("plugins");
  });

  it("shows plugins only when both admin access and the release capability are present", () => {
    expect(visibleItemIds(user(true), true)).toContain("plugins");
    expect(visibleItemIds(user(false), true)).not.toContain("plugins");
  });

  it("hides Kubernetes when the deployment capability is disabled", () => {
    expect(visibleItemIds(user(true, featureMap({ settings: true, kubernetes: false })), true)).not.toContain("kubernetes");
    expect(visibleItemIds(user(true, featureMap({ settings: true, kubernetes: true })), true)).toContain("kubernetes");
  });

  it("hides personal AI connections from a pilot user without platform AI authority", () => {
    const pilot = user(false, featureMap({ ai_connections_personal: true }));

    expect(visibleItemIds(pilot, false)).toEqual([]);
  });

  it("hides AI model settings from ordinary staff without platform AI authority", () => {
    expect(visibleItemIds(user(true, featureMap({ settings: true }), false), false)).not.toContain("ai");
    expect(visibleItemIds(user(true, featureMap({ settings: true }), true), false)).toContain("ai");
    expect(visibleItemIds(user(false, featureMap({ settings: true }), true), false)).toContain("ai");
  });
});
