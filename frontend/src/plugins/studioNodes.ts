import { Puzzle, type LucideIcon } from "lucide-react";

import type { StudioCapabilityNode } from "@/lib/api";
import { StudioPluginNodeHost } from "./StudioPluginNodeHost";

export type PluginPaletteNode = {
  type: string;
  label: string;
  description: string;
  icon: LucideIcon;
  iconClassName?: string;
};

export type PluginPaletteCategory = {
  category: string;
  nodes: PluginPaletteNode[];
};

export function isPluginStudioNode(manifest: StudioCapabilityNode | undefined): manifest is StudioCapabilityNode {
  return Boolean(manifest?.metadata?.plugin_id);
}

export function pluginNodeLabel(manifest: StudioCapabilityNode): string {
  const metadata = manifest.metadata || {};
  return String(metadata.label || metadata.title || manifest.type);
}

export function pluginNodeDescription(manifest: StudioCapabilityNode): string {
  const metadata = manifest.metadata || {};
  return String(metadata.palette_description || manifest.purpose || manifest.type);
}

export function buildPluginNodePalette(manifests: StudioCapabilityNode[]): PluginPaletteCategory[] {
  const nodes = manifests
    .filter(isPluginStudioNode)
    .map((manifest) => ({
      type: manifest.type,
      label: pluginNodeLabel(manifest),
      description: pluginNodeDescription(manifest),
      icon: Puzzle,
      iconClassName: String(manifest.metadata?.icon_class_name || "text-teal-400"),
    }));
  return nodes.length ? [{ category: "Plugin", nodes }] : [];
}

export function buildPluginNodeTypes(manifests: StudioCapabilityNode[]) {
  return Object.fromEntries(
    manifests
      .filter(isPluginStudioNode)
      .map((manifest) => [manifest.type, StudioPluginNodeHost]),
  );
}

export function buildSchemaDefaultData(manifest?: StudioCapabilityNode): Record<string, unknown> {
  if (!manifest) return {};
  const properties = manifest.input_schema?.properties;
  if (!properties || typeof properties !== "object" || Array.isArray(properties)) return {};
  const defaults: Record<string, unknown> = {
    plugin_node_label: pluginNodeLabel(manifest),
    description: pluginNodeDescription(manifest),
    source_handles: manifest.source_handles,
  };
  Object.entries(properties as Record<string, Record<string, unknown>>).forEach(([field, property]) => {
    if ("default" in property) {
      defaults[field] = property.default;
    }
  });
  return defaults;
}
