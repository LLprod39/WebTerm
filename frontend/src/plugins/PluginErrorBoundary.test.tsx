import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PluginErrorBoundary } from "./PluginErrorBoundary";

function BrokenPluginSurface(): ReactNode {
  throw new Error("boom");
}

describe("PluginErrorBoundary", () => {
  const preventExpectedError = (event: ErrorEvent) => {
    if (event.error?.message === "boom") event.preventDefault();
  };

  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    window.addEventListener("error", preventExpectedError);
  });

  afterEach(() => {
    window.removeEventListener("error", preventExpectedError);
    vi.restoreAllMocks();
  });

  it("renders a contained fallback when a plugin surface throws", () => {
    render(
      <PluginErrorBoundary pluginId="acme.broken" surface="dashboard_widget:broken">
        <BrokenPluginSurface />
      </PluginErrorBoundary>,
    );

    expect(screen.getByText("Plugin surface failed")).toBeInTheDocument();
    expect(screen.getByText(/acme\.broken/)).toBeInTheDocument();
  });
});
