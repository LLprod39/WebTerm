import { waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { applyUiStyleToDocument } from "./ui-style";

describe("pilot and experimental UI styles", () => {
  afterEach(() => {
    applyUiStyleToDocument("flow-dark");
    document.getElementById("webterm-experimental-theme-fonts")?.remove();
  });

  it("keeps flow-dark available without experimental inline tokens", () => {
    applyUiStyleToDocument("flow-dark");

    expect(document.documentElement).toHaveAttribute("data-ui-style", "flow-dark");
    expect(document.documentElement.style.getPropertyValue("--background")).toBe("");
  });

  it("loads experimental tokens on demand and clears them when returning to flow-dark", async () => {
    applyUiStyleToDocument("catalog");

    await waitFor(() => {
      expect(document.documentElement.style.getPropertyValue("--background")).toBe("240 10% 4%");
    });
    expect(document.getElementById("webterm-experimental-theme-fonts")).toHaveAttribute(
      "href",
      expect.stringContaining("fonts.googleapis.com"),
    );

    applyUiStyleToDocument("flow-dark");
    expect(document.documentElement.style.getPropertyValue("--background")).toBe("");
  });
});
