import type { FrontendGroup, FrontendServer } from "@/lib/api";

export type PlaybooksView =
  | { mode: "catalog" }
  | { mode: "guided" }
  | { mode: "edit"; playbookId: number | null }
  | { mode: "run-wizard"; playbookId: number }
  | { mode: "run-results"; runId: number };

export interface PlaybooksViewChangeOptions {
  /** Replace the current history entry when restoring a blocked navigation. */
  replace?: boolean;
}

export interface PlaybooksWorkspaceProps {
  /** When provided, skip bootstrap fetch for inventory targets */
  servers?: FrontendServer[];
  groups?: FrontendGroup[];
  /** Load data only when tab is active */
  enabled?: boolean;
  /** Route-derived view used for direct links and browser reloads. */
  initialView?: PlaybooksView;
  /** Keeps the canonical URL in sync with workspace navigation. */
  onViewChange?: (view: PlaybooksView, options?: PlaybooksViewChangeOptions) => void;
}
