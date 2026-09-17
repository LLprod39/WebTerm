import { demoAccessFallback } from "./api-demo/demo-access";
import { demoAdminFallback } from "./api-demo/demo-admin";
import { demoAgentsEarlyFallback } from "./api-demo/demo-agents-early";
import { demoAgentsLateFallback } from "./api-demo/demo-agents-late";
import { demoFilesOpsFallback } from "./api-demo/demo-files-ops";
import { demoMonitoringFallback } from "./api-demo/demo-monitoring";
import { demoPlaybooksFallback } from "./api-demo/demo-playbooks";
import { demoServerCrudFallback } from "./api-demo/demo-server-crud";
import { demoSettingsModelsFallback } from "./api-demo/demo-settings-models";

/**
 * Demo-mode fallbacks for server admin / settings / agents / playbooks APIs.
 * Domain helpers are tried in the original path-match order — do not reorder.
 */
export function demoServerAdminFallback<T>(path: string, _options: RequestInit = {}): T | undefined {
  return (
    demoFilesOpsFallback<T>(path, _options) ??
    demoSettingsModelsFallback<T>(path, _options) ??
    demoAdminFallback<T>(path, _options) ??
    demoMonitoringFallback<T>(path, _options) ??
    demoAgentsEarlyFallback<T>(path, _options) ??
    demoPlaybooksFallback<T>(path, _options) ??
    demoAgentsLateFallback<T>(path, _options) ??
    demoServerCrudFallback<T>(path, _options) ??
    demoAccessFallback<T>(path, _options)
  );
}
