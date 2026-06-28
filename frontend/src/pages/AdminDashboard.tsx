import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Maximize2, Minimize2 } from "lucide-react";

import { fetchAdminDashboard } from "@/api";
import { fetchPluginSurfaces } from "@/api";
import { Button } from "@/components/ui/button";
import { CustomizableDashboard } from "@/components/dashboard/CustomizableDashboard";
import { PageHero, PageShell, QueryStateBlock } from "@/components/ui/page-shell";
import { localize, useI18n } from "@/lib/i18n";
import { buildAdminDashboardWidgets } from "./admin-dashboard/adminDashboardWidgets";
import { buildPluginDashboardWidgets } from "@/plugins/dashboardWidgets";

export default function AdminDashboard() {
  const { lang } = useI18n();
  const [isFullWidth, setIsFullWidth] = useState(() => localStorage.getItem("admin_dashboard_full_width") === "true");

  const toggleWidth = () => {
    setIsFullWidth((prev) => {
      const next = !prev;
      localStorage.setItem("admin_dashboard_full_width", String(next));
      return next;
    });
  };

  const { data: dashResponse, isLoading, error, refetch } = useQuery({
    queryKey: ["admin", "dashboard"],
    queryFn: fetchAdminDashboard,
    refetchInterval: 30000,
  });
  const { data: pluginSurfaces } = useQuery({
    queryKey: ["plugins", "surfaces", "dashboard", "admin"],
    queryFn: fetchPluginSurfaces,
  });

  const d = dashResponse?.data;
  const availableWidgets = useMemo(() => {
    const builtins = d ? buildAdminDashboardWidgets(d, lang) : [];
    const pluginWidgets = buildPluginDashboardWidgets(pluginSurfaces?.surfaces.dashboard_widgets ?? []);
    return [...builtins, ...pluginWidgets];
  }, [d, lang, pluginSurfaces?.surfaces.dashboard_widgets]);

  return (
    <PageShell width={isFullWidth ? "full" : "7xl"}>
      <PageHero
        kicker={localize(lang, "Состояние платформы", "Platform Status")}
        title={localize(lang, "Панель администратора", "Admin Dashboard")}
        description={localize(
          lang,
          "Мониторинг инфраструктуры, активности пользователей и запусков агентов в реальном времени.",
          "Live monitoring for infrastructure, user activity, and agent runs.",
        )}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={toggleWidth}
              className="h-8 gap-1.5 text-xs font-semibold hover:border-primary/50 shadow-sm transition-all"
            >
              {isFullWidth ? (
                <>
                  <Minimize2 className="h-3.5 w-3.5" />
                  <span>Обычный экран</span>
                </>
              ) : (
                <>
                  <Maximize2 className="h-3.5 w-3.5" />
                  <span>На весь экран</span>
                </>
              )}
            </Button>
            <div className="flex items-center gap-3 px-3 py-1.5 rounded-xl bg-card border border-border/80 shadow-sm h-8 shrink-0">
              <Activity className="h-4 w-4 text-info" />
              <span className="text-xs font-semibold text-foreground/90">{localize(lang, "Версия", "Version")} v{d?.app_version || "2.0.0"}</span>
              <div className="h-3.5 w-px bg-border mx-1" />
              <span className="text-xs text-muted-foreground">{localize(lang, "Автообновление 30 с", "Refreshes every 30s")}</span>
            </div>
          </div>
        }
      />

      <QueryStateBlock loading={isLoading} error={error} onRetry={() => refetch()}>
        <CustomizableDashboard type="admin" availableWidgets={availableWidgets} />
      </QueryStateBlock>
    </PageShell>
  );
}
