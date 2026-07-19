import {
  DEMO_BOOTSTRAP,
  DEMO_SESSION,
  demoSuccess,
} from "./demo";
import { demoKubernetesFallback } from "./api-demo-kubernetes";
import { demoLinuxUiCoreFallback } from "./api-demo-linux-core";
import { demoLinuxUiExtendedFallback } from "./api-demo-linux-extended";
import { demoServerAdminFallback } from "./api-demo-server-admin";
import { demoStudioFallback } from "./api-demo-studio";
import { demoMarsFallback } from "./demo-mars";

/** Provides mock data for known API paths when in demo mode */
export function demoFallback<T>(path: string, _options: RequestInit = {}): T {
  if (path.includes("/api/auth/session")) return DEMO_SESSION as T;
  if (path.includes("/api/auth/login")) return { success: true, authenticated: true, next_url: "/servers", user: DEMO_SESSION.user } as T;
  if (path.includes("/api/auth/logout")) return { success: true } as T;
  if (path.includes("/api/auth/ws-token")) return { token: "demo-token" } as T;
  if (path.includes("/frontend/bootstrap")) return DEMO_BOOTSTRAP as T;

  // Plugin surfaces: dashboards expect surfaces.dashboard_widgets[] even when empty.
  if (path.includes("/api/plugins/surfaces")) {
    return {
      success: true,
      surfaces: {
        pages: [],
        dashboard_widgets: [],
        connectors: [],
        studio_nodes: [],
        agent_tools: [],
        terminal_actions: [],
        hooks: [],
      },
    } as T;
  }
  if (path.includes("/api/plugins/catalog")) {
    return { success: true, packages: [], items: [], count: 0 } as T;
  }
  if (path.includes("/api/plugins/installed")) {
    return { success: true, installations: [], count: 0 } as T;
  }

  const kubernetesFallback = demoKubernetesFallback<T>(path, _options);
  if (kubernetesFallback !== undefined) return kubernetesFallback;

  const linuxCoreFallback = demoLinuxUiCoreFallback<T>(path, _options);
  if (linuxCoreFallback !== undefined) return linuxCoreFallback;

  const linuxExtendedFallback = demoLinuxUiExtendedFallback<T>(path, _options);
  if (linuxExtendedFallback !== undefined) return linuxExtendedFallback;

  const serverAdminFallback = demoServerAdminFallback<T>(path, _options);
  if (serverAdminFallback !== undefined) return serverAdminFallback;

  const studioFallback = demoStudioFallback<T>(path);
  if (studioFallback !== undefined) return studioFallback;

  const marsFallback = demoMarsFallback<T>(path, _options);
  if (marsFallback !== undefined) return marsFallback;

  return demoSuccess() as T;
}
