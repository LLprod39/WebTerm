import { describe, expect, it } from "vitest";

import { visibleSettingsNavGroups } from "./settings-nav-items";
import type { AuthUser } from "@/lib/api";
import { featureMap } from "@/test/featureFlags";

function user(isAdmin: boolean, features = featureMap({ settings: true, plugins: true })): AuthUser {
  return { id: 1, username: "pilot", email: "pilot@example.test", is_staff: isAdmin, features };
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

  it("shows only personal AI connections to a pilot user without Settings access", () => {
    const pilot = user(false, featureMap({ ai_connections_personal: true }));

    expect(visibleItemIds(pilot, false)).toEqual(["ai-connections"]);
  });
});
