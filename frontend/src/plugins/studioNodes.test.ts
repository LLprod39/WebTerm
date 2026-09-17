import { describe, expect, it } from "vitest";

import type { StudioCapabilityNode } from "@/lib/api";
import {
  buildPluginNodePalette,
  buildPluginNodeTypes,
  buildSchemaDefaultData,
} from "./studioNodes";

const manifest: StudioCapabilityNode = {
  type: "plugin/webtrerm.demo-dashboard/demo-connector-ping",
  category: "Plugin",
  purpose: "Runs a safe connector ping.",
  source_handles: ["success", "error", "out"],
  risk_level: "network_read",
  mutates_state: false,
  supports_dry_run: true,
  requires_approval_by_default: true,
  recommended_verification: [],
  tags: ["plugin"],
  input_schema: {
    type: "object",
    properties: {
      connector_id: { type: "string", default: "demo-connector" },
      message: { type: "string", default: "Ping" },
    },
  },
  output_schema: { type: "object", properties: {} },
  metadata: {
    plugin_id: "webtrerm.demo-dashboard",
    label: "Demo Connector Ping",
    palette_description: "Permission-gated ping",
  },
};

describe("studio plugin node helpers", () => {
  it("builds palette, ReactFlow node types and default data from manifests", () => {
    const palette = buildPluginNodePalette([manifest]);
    const nodeTypes = buildPluginNodeTypes([manifest]);
    const defaults = buildSchemaDefaultData(manifest);

    expect(palette[0].category).toBe("Plugin");
    expect(palette[0].nodes[0]).toMatchObject({
      type: manifest.type,
      label: "Demo Connector Ping",
      description: "Permission-gated ping",
    });
    expect(nodeTypes[manifest.type]).toBeTruthy();
    expect(defaults).toMatchObject({
      plugin_node_label: "Demo Connector Ping",
      connector_id: "demo-connector",
      message: "Ping",
      source_handles: ["success", "error", "out"],
    });
  });
});
