import { describe, expect, it } from "vitest";

import { visibleSettingsNavGroups } from "./settings-nav-items";

function visibleItemIds(isAdmin: boolean, pluginsEnabled: boolean) {
  return visibleSettingsNavGroups(isAdmin, pluginsEnabled).flatMap((group) =>
    group.items.map((item) => item.id),
  );
}

describe("settings navigation release capabilities", () => {
  it("hides plugins from an admin when the release profile is disabled", () => {
    expect(visibleItemIds(true, false)).not.toContain("plugins");
  });

  it("shows plugins only when both admin access and the release capability are present", () => {
    expect(visibleItemIds(true, true)).toContain("plugins");
    expect(visibleItemIds(false, true)).not.toContain("plugins");
  });
});
