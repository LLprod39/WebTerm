import type { ElementType } from "react";

export type RouteModelConfig = {
  key: "chat" | "agent" | "orchestrator";
  shortLabel: string;
  label: string;
  description: string;
  icon: ElementType;
  provider: string;
  model: string;
};

export type ProviderOverviewItem = {
  value: string;
  label: string;
  catalogSize: number;
  activeRoutes: string[];
  enabled: boolean;
  configured: boolean;
  isSelected: boolean;
};
