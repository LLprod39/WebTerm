import { waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { applyUiStyleToDocument, resolveDocumentUiStyle } from "./ui-style";

describe("pilot and experimental UI styles", () => {
  afterEach(() => {
    applyUiStyleToDocument("flow-dark");
    document.getElementById("webterm-experimental-theme-fonts")?.remove();
    document.getElementById("webterm-supported-theme-fonts")?.remove();
  });

  it("keeps enterprise styles self-hosted and restores flow-dark for chat only", () => {
    expect(resolveDocumentUiStyle("enterprise-light", "/servers")).toBe("enterprise-light");
    expect(resolveDocumentUiStyle("enterprise-light", "/chat")).toBe("flow-dark");
    expect(resolveDocumentUiStyle("enterprise-light", "/chat/session/1")).toBe("flow-dark");
    expect(resolveDocumentUiStyle("enterprise-dark", "/servers")).toBe("enterprise-dark");
    expect(resolveDocumentUiStyle("enterprise-dark", "/chat")).toBe("flow-dark");
    expect(resolveDocumentUiStyle("enterprise-dark", "/chat/session/1")).toBe("flow-dark");

    applyUiStyleToDocument("enterprise-light", "/servers");
    expect(document.documentElement).toHaveAttribute("data-ui-preference", "enterprise-light");
    expect(document.documentElement).toHaveAttribute("data-ui-style", "enterprise-light");
    expect(document.documentElement.style.colorScheme).toBe("light");
    expect(document.getElementById("webterm-supported-theme-fonts")).toBeNull();

    applyUiStyleToDocument("enterprise-light", "/chat");
    expect(document.documentElement).toHaveAttribute("data-ui-preference", "enterprise-light");
    expect(document.documentElement).toHaveAttribute("data-ui-style", "flow-dark");
    expect(document.getElementById("webterm-supported-theme-fonts")).not.toBeNull();

    applyUiStyleToDocument("enterprise-dark", "/servers");
    expect(document.documentElement).toHaveAttribute("data-ui-preference", "enterprise-dark");
    expect(document.documentElement).toHaveAttribute("data-ui-style", "enterprise-dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
    expect(document.getElementById("webterm-supported-theme-fonts")).toBeNull();

    applyUiStyleToDocument("enterprise-dark", "/chat");
    expect(document.documentElement).toHaveAttribute("data-ui-preference", "enterprise-dark");
    expect(document.documentElement).toHaveAttribute("data-ui-style", "flow-dark");
    expect(document.getElementById("webterm-supported-theme-fonts")).not.toBeNull();
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
