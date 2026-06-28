import { describe, expect, it } from "vitest";

import { buildDynamicFrontendBundleSrcDoc } from "./pluginDynamicBundleFrame";

describe("buildDynamicFrontendBundleSrcDoc", () => {
  it("builds a sandbox bootstrap that verifies bundle integrity before import", () => {
    const srcDoc = buildDynamicFrontendBundleSrcDoc({
      title: "Dynamic <Plugin>",
      pluginId: "acme.dynamic",
      pageId: "main",
      runtime: {
        renderer: "javascript",
        bundle_url: "https://cdn.example/plugins/dynamic.js",
        bundle_sha256: "a".repeat(64),
      },
    });

    expect(srcDoc).toContain('crypto.subtle.digest("SHA-256"');
    expect(srcDoc).toContain("Bundle SHA-256 mismatch.");
    expect(srcDoc).toContain("connect-src https://cdn.example");
    expect(srcDoc).toContain("script-src 'unsafe-inline' blob:");
    expect(srcDoc).toContain("Dynamic &lt;Plugin&gt;");
    expect(srcDoc).not.toContain("Dynamic <Plugin>");
  });
});
