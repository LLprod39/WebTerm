import type { AgentRunDetail } from "@/lib/api";

export type AgentRunTab = "pipeline" | "report" | "timeline";
export type PlanTask = AgentRunDetail["plan_tasks"][number];
