import { describe, expect, it } from "vitest";

import { buildPluginDashboardWidgets } from "./dashboardWidgets";

describe("buildPluginDashboardWidgets", () => {
  it("builds namespaced dashboard widget definitions", () => {
    const widgets = buildPluginDashboardWidgets([
      {
        plugin_id: "webtrerm.demo-dashboard",
        id: "demo-health",
        title: "Plugin Runtime Status",
        frontend_bundle_runtime: {
          renderer: "javascript",
          bundle_url: "https://cdn.example/widget.js",
          bundle_sha256: "a".repeat(64),
        },
      },
      { plugin_id: "", id: "invalid" },
    ]);

    expect(widgets).toHaveLength(1);
    expect(widgets[0].id).toBe("plugin:webtrerm.demo-dashboard:demo-health");
    expect(widgets[0].title).toBe("Plugin Runtime Status");
    expect(widgets[0].defaultSize.w).toBe(4);
    expect(widgets[0].render({ id: widgets[0].id, x: 0, y: 0, w: 4, h: 1 })).toBeTruthy();
  });
});
