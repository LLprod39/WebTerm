import { useMemo } from "react";
import {
  Maximize2,
  Minimize2,
  Server,
  Workflow,
} from "lucide-react";
import { Link } from "react-router-dom";
import { PageShell, PageHero, QueryStateBlock } from "@/components/ui/page-shell";
import { SkeletonMetrics, SkeletonList } from "@/components/ui/list-state";
import { CustomizableDashboard } from "@/components/dashboard/CustomizableDashboard";
import { isRunFailure, isRunSuccess } from "@/lib/runStatus";
import { localize } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { buildUserDashboardWidgets } from "@/pages/user-dashboard/buildUserDashboardWidgets";
import { FlowKpiStrip } from "@/pages/user-dashboard/FlowKpiStrip";
import { useUserDashboardData } from "@/pages/user-dashboard/useUserDashboardData";

export default function UserDashboard() {
  const data = useUserDashboardData();
  const {
    lang,
    isFullWidth,
    toggleWidth,
    boot,
    runs,
    mon,
    monLoading,
    monFetching,
    liveConnected,
    liveMetrics,
    isLoading,
    pluginSurfaces,
  } = data;

  const availableWidgets = useMemo(
    () => buildUserDashboardWidgets(data),
    // Rebuild when underlying dashboard inputs change (same deps as pre-split).
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `data` is a fresh object each render
    [boot, runs, mon, monLoading, monFetching, liveConnected, liveMetrics, pluginSurfaces?.surfaces?.dashboard_widgets, lang],
  );

  return (
    <PageShell width={isFullWidth ? "full" : "7xl"}>
      <PageHero
        kicker={localize(lang, "Операции", "Operations")}
        title={localize(lang, "Мой воркспейс", "My workspace")}
        description={localize(
          lang,
          "Обзор активных задач, доступных серверов и последних событий в вашей рабочей среде.",
          "Overview of active tasks, available servers and recent events in your workspace.",
        )}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={toggleWidth} className="gap-1.5">
              {isFullWidth ? (
                <>
                  <Minimize2 className="h-3.5 w-3.5" />
                  <span>{localize(lang, "Обычный экран", "Normal width")}</span>
                </>
              ) : (
                <>
                  <Maximize2 className="h-3.5 w-3.5" />
                  <span>{localize(lang, "На весь экран", "Full width")}</span>
                </>
              )}
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to="/servers/hub">
                <Server className="mr-1.5 h-3.5 w-3.5" /> {localize(lang, "Хаб серверов", "Server hub")}
              </Link>
            </Button>
            <Button size="sm" asChild>
              <Link to="/studio">
                <Workflow className="mr-1.5 h-3.5 w-3.5" /> {localize(lang, "Студия", "Studio")}
              </Link>
            </Button>
          </div>
        }
      />

      {isLoading ? (
        <div className="space-y-4">
          <SkeletonMetrics count={4} />
          <SkeletonList rows={4} />
        </div>
      ) : (
        <>
          <FlowKpiStrip
            lang={lang}
            onlineServers={
              mon?.summary
                ? (mon.summary.healthy || 0) + (mon.summary.warning || 0)
                : null
            }
            totalServers={mon?.summary?.total_servers ?? boot?.servers?.length ?? 0}
            runs7d={runs?.recent?.length ?? 0}
            runSpark={
              (runs?.recent ?? [])
                .slice()
                .reverse()
                .map((r) => (isRunSuccess(r.status) ? 1 : isRunFailure(r.status) ? 0 : 0.5))
            }
            activeAlerts={mon?.summary?.active_alerts ?? 0}
            tokensHint={localize(lang, "из LLM-слоя", "from LLM layer")}
          />
          <QueryStateBlock loading={false}>
            <CustomizableDashboard type="user" availableWidgets={availableWidgets} />
          </QueryStateBlock>
        </>
      )}
    </PageShell>
  );
}
