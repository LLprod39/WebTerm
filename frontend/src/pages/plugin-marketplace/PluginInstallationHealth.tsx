import { AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { PluginInstallation } from "@/plugins/types";

function hasHealthIssue(installation: PluginInstallation) {
  const healthStatus = installation.health_status || "";
  return Boolean(
    installation.last_error
      || installation.status === "quarantined"
      || healthStatus === "sandbox_failed"
      || healthStatus === "blocked",
  );
}

export function PluginInstallationHealthBadge({ installation }: { installation: PluginInstallation }) {
  const healthStatus = installation.health_status || "";
  if (!healthStatus) return null;
  return (
    <Badge variant={hasHealthIssue(installation) ? "destructive" : "outline"}>
      health: {healthStatus}
    </Badge>
  );
}

export function PluginInstallationHealthNotice({ installation }: { installation: PluginInstallation }) {
  if (!hasHealthIssue(installation)) return null;
  return (
    <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs leading-5 text-destructive">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span className="min-w-0 break-words">
        {installation.last_error || "Plugin is quarantined after repeated failures."}
        {installation.health_failure_count ? ` Failure count: ${installation.health_failure_count}.` : ""}
      </span>
    </div>
  );
}
