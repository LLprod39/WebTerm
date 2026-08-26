import { Suspense, useEffect, useLayoutEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "./AppSidebar";
import { FlowChrome } from "./FlowChrome";
import { FlowTopbar } from "./FlowTopbar";
import { EnterpriseTopbar } from "./EnterpriseTopbar";
import { PageTransition } from "@/components/PageTransition";
import { Outlet, useLocation, Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { localize, useI18n } from "@/lib/i18n";
import {
  applyUiStyleToDocument,
  isEnterpriseStyle,
  isFlowStyle,
  resolveDocumentUiStyle,
  useUiStyle,
} from "@/lib/ui-style";
import { prefetchCoreRoutes } from "@/lib/route-prefetch";
import { SkeletonMetrics, SkeletonList } from "@/components/ui/list-state";
import { fetchMonitoringDashboard } from "@/lib/api";
import { writeMonitoringDashboardCache } from "@/lib/monitoring-cache";
import { AshitaAtmosphere } from "@/components/AshitaAtmosphere";

const immersiveMeta: Array<{ match: RegExp; titleRu: string; titleEn: string; backTo: string; hideHeader?: boolean }> = [
  { match: /^\/servers\/hub$/, titleRu: "Терминалы", titleEn: "Terminal Hub", backTo: "/servers", hideHeader: true },
  { match: /^\/servers\/\d+\/terminal$/, titleRu: "Терминал", titleEn: "Terminal", backTo: "/servers", hideHeader: true },
  { match: /^\/agents\/run\/\d+$/, titleRu: "Отчёт агента", titleEn: "Agent Run", backTo: "/agents", hideHeader: true },
  { match: /^\/studio\/pipeline\/(?:new|\d+)$/, titleRu: "Редактор пайплайна", titleEn: "Pipeline Editor", backTo: "/studio", hideHeader: true },
];

/** Inline content placeholder — never replaces the sidebar shell. */
function ContentFallback() {
  return (
    <div className="space-y-4 px-4 py-5 md:px-6 xl:px-8" aria-hidden>
      <SkeletonMetrics count={4} />
      <SkeletonList rows={5} />
    </div>
  );
}

export default function AppLayout() {
  const location = useLocation();
  const { lang } = useI18n();
  const { style } = useUiStyle();
  const queryClient = useQueryClient();
  const isChatRoute = location.pathname === "/chat" || location.pathname.startsWith("/chat/");
  const effectiveStyle = resolveDocumentUiStyle(style, location.pathname);
  const isFlow = isFlowStyle(effectiveStyle);
  const isEnterprise = isEnterpriseStyle(style) && !isChatRoute;
  const isAshita = style === "ashita";
  const routeSection = location.pathname.split("/").filter(Boolean)[0] ?? "dashboard";
  const immersive = immersiveMeta.find(({ match }) => match.test(location.pathname));
  const openNavigationLabel = localize(lang, "Открыть навигацию", "Open navigation");

  // Warm lazy page chunks so first nav click is already cached.
  useEffect(() => {
    prefetchCoreRoutes();
  }, []);

  // Keep Chat pixel-compatible with the current flow-dark UI without changing
  // the saved Enterprise preference. Leaving Chat restores Enterprise instantly.
  useLayoutEffect(() => {
    applyUiStyleToDocument(style, location.pathname);
  }, [location.pathname, style]);

  // Prefetch fleet monitoring as soon as the shell mounts so dashboard/servers
  // open with last-known numbers instead of a "нет связи" flash.
  useEffect(() => {
    void queryClient
      .prefetchQuery({
        queryKey: ["monitoring-dashboard"],
        queryFn: fetchMonitoringDashboard,
        staleTime: 30_000,
      })
      .then(() => {
        const data = queryClient.getQueryData(["monitoring-dashboard"]) as
          | Awaited<ReturnType<typeof fetchMonitoringDashboard>>
          | undefined;
        if (data) writeMonitoringDashboardCache(data);
      })
      .catch(() => {
        /* ignore — page will fetch on demand */
      });
  }, [queryClient]);

  const mobileSidebarTrigger = (
    <div className="pointer-events-none fixed left-4 top-4 z-40 md:hidden">
      <SidebarTrigger
        className="pointer-events-auto h-11 w-11 rounded-xl border border-border bg-card/95 text-foreground shadow-lg shadow-background/30"
        aria-label={openNavigationLabel}
        title={openNavigationLabel}
      />
    </div>
  );

  if (immersive) {
    return (
      <SidebarProvider data-ui-shell={isEnterprise ? "enterprise" : isFlow ? "flow" : "legacy"}>
        <FlowChrome>
          <a href="#main-content" className="sr-only fixed left-3 top-3 z-[100] rounded-md bg-primary px-4 py-2 text-primary-foreground focus:not-sr-only">
            {localize(lang, "Перейти к содержимому", "Skip to content")}
          </a>
          {isAshita ? <AshitaAtmosphere /> : null}
          {mobileSidebarTrigger}
          <div className="app-shell-bg flex h-screen min-h-0 w-full overflow-hidden" data-ui-slot="app-shell">
            <AppSidebar />
            <div className="flex min-h-0 min-w-0 flex-1 flex-col">
              {!immersive.hideHeader && (
                <header className="flex h-12 items-center gap-3 border-b border-border/70 bg-card/75 px-3 backdrop-blur">
                  <SidebarTrigger className="h-9 w-9 text-muted-foreground hover:text-foreground" />
                  <Link
                    to={immersive.backTo}
                    className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                  >
                    <ArrowLeft className="h-3 w-3" />
                    {localize(lang, "Назад", "Back")}
                  </Link>
                  <span className="text-xs font-medium text-foreground">{localize(lang, immersive.titleRu, immersive.titleEn)}</span>
                </header>
              )}
              <main
                id="main-content"
                tabIndex={-1}
                data-enterprise-content={isEnterprise ? "true" : undefined}
                data-route-section={routeSection}
                data-route-path={location.pathname}
                className="flex min-h-0 flex-1 flex-col overflow-hidden pt-16 md:pt-0"
              >
                <Suspense fallback={<ContentFallback />}>
                  <PageTransition>
                    <Outlet />
                  </PageTransition>
                </Suspense>
              </main>
            </div>
          </div>
        </FlowChrome>
      </SidebarProvider>
    );
  }

  return (
    <SidebarProvider data-ui-shell={isEnterprise ? "enterprise" : isFlow ? "flow" : "legacy"}>
      <FlowChrome>
        <a href="#main-content" className="sr-only fixed left-3 top-3 z-[100] rounded-md bg-primary px-4 py-2 text-primary-foreground focus:not-sr-only">
          {localize(lang, "Перейти к содержимому", "Skip to content")}
        </a>
        {isAshita ? <AshitaAtmosphere /> : null}
        {mobileSidebarTrigger}
        <div className="app-shell-bg flex h-screen min-h-0 w-full overflow-hidden" data-ui-slot="app-shell">
          <AppSidebar />
          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            {isEnterprise ? <EnterpriseTopbar /> : isFlow ? <FlowTopbar effectiveStyle={effectiveStyle} /> : null}
            <main
              id="main-content"
              tabIndex={-1}
              data-enterprise-content={isEnterprise ? "true" : undefined}
              data-route-section={routeSection}
              data-route-path={location.pathname}
              className={
                isEnterprise
                  ? "enterprise-sheet min-h-0 flex-1 overflow-auto pt-16 md:pt-0"
                  : isFlow
                  ? isChatRoute
                    ? "flow-sheet min-h-0 flex-1 overflow-hidden pt-16 md:pt-0"
                    : "flow-sheet min-h-0 flex-1 overflow-auto pt-16 md:pt-0"
                  : isChatRoute
                    ? "min-h-0 flex-1 overflow-hidden pt-16 md:pt-0"
                    : "min-h-0 flex-1 overflow-auto pt-16 md:pt-0"
              }
            >
              <Suspense fallback={<ContentFallback />}>
                <PageTransition>
                  <Outlet />
                </PageTransition>
              </Suspense>
            </main>
          </div>
        </div>
      </FlowChrome>
    </SidebarProvider>
  );
}
