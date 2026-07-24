import type { FrontendGroup, FrontendServer } from "@/lib/api";

export type PlaybooksView =
  | { mode: "catalog" }
  | { mode: "guided" }
  | { mode: "edit"; playbookId: number | null }
  | { mode: "run-wizard"; playbookId: number }
  | { mode: "run-results"; runId: number };

export interface PlaybooksWorkspaceProps {
  /** When provided, skip bootstrap fetch for inventory targets */
  servers?: FrontendServer[];
  groups?: FrontendGroup[];
  /** Load data only when tab is active */
  enabled?: boolean;
}
