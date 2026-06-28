import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { PluginDashboardWidgetHost } from "./DashboardWidgetHost";

describe("PluginDashboardWidgetHost", () => {
  it("renders reviewed dynamic widget bundles inside a sandboxed iframe", () => {
    render(
      <MemoryRouter>
        <PluginDashboardWidgetHost
          config={{ id: "plugin:acme.widget:dynamic", x: 0, y: 0, w: 4, h: 1 }}
          widget={{
            plugin_id: "acme.widget",
            id: "dynamic",
            title: "Dynamic Widget",
            frontend_bundle_runtime: {
              renderer: "remote",
              bundle_url: "https://cdn.example/widget.js",
              bundle_sha256: "c".repeat(64),
            },
          }}
        />
      </MemoryRouter>,
    );

    const iframe = screen.getByTitle("Dynamic Widget");
    expect(iframe).toHaveAttribute("sandbox", "allow-scripts");
    expect(iframe).toHaveAttribute("referrerPolicy", "no-referrer");
    expect(iframe.getAttribute("srcdoc")).toContain("Bundle SHA-256 mismatch.");
    expect(iframe.getAttribute("srcdoc")).toContain("dashboard_widget:dynamic");
  });
});
