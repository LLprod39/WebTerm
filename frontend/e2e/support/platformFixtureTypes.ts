import type { ApiHarness } from "./apiHarness";

export type SessionUser = {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  features: Record<string, boolean> & {
    servers: boolean;
    dashboard: boolean;
    agents: boolean;
    studio: boolean;
    settings: boolean;
    orchestrator: boolean;
  };
};

export type ServerItem = {
  id: number;
  name: string;
  host: string;
  port: number;
  username: string;
  server_type: "ssh";
  status: "online" | "offline" | "unknown";
  group_id: number | null;
  group_name: string;
  is_shared: boolean;
  can_edit: boolean;
  share_context_enabled: boolean;
  shared_by_username: string;
  terminal_path: string;
  minimal_terminal_path: string;
  last_connected: string | null;
};

export type PlatformMockOptions = {
  authenticated?: boolean;
  isStaff?: boolean;
  lang?: "en" | "ru";
  features?: Partial<SessionUser["features"]>;
  agentList?: "default" | "empty";
  kubernetesState?: "empty" | "healthy" | "degraded";
  settingsReadiness?: "ready" | "warning" | "error";
  /** Populate server-detail tabs (sharing, notes, AI memory) for the product demo tour. */
  demoData?: boolean;
};

export type PlatformMockResult = {
  harness: ApiHarness;
  state: {
    authenticated: boolean;
  };
};

export const FIXED_DATE = "2026-03-01T08:00:00.000Z";

export function makeSessionUser(isStaff: boolean, username = "admin"): SessionUser {
  return {
    id: 1,
    username,
    email: `${username}@example.com`,
    is_staff: isStaff,
    features: {
      servers: true,
      dashboard: true,
      agents: true,
      studio: true,
      kubernetes: false,
      mars: false,
      settings: true,
      orchestrator: true,
    },
  };
}
