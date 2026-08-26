import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Suspense, lazy, type ReactNode } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { I18nProvider, localize, useI18n } from "./lib/i18n";
import { UiStyleProvider } from "./lib/ui-style";
import AppLayout from "./components/AppLayout";
import { fetchAuthSession } from "./lib/api";
import { canAccessStudio, canManageAiRouting, hasAnyFeatureAccess, hasFeatureAccess } from "./lib/featureAccess";
import { FirstRunReadinessGate } from "./components/FirstRunReadinessGate";
import { AppMotionProvider } from "./components/AppMotionProvider";
import { firstAllowedApplicationPath } from "./lib/navigation";

const queryClient = new QueryClient();
const Index = lazy(() => import("./pages/Index"));
const Login = lazy(() => import("./pages/Login"));
const Servers = lazy(() => import("./pages/Servers"));
const AutomationPage = lazy(() => import("./pages/AutomationPage"));
const TerminalPage = lazy(() => import("./pages/TerminalPage"));
const DashboardRouter = lazy(() => import("./pages/DashboardRouter"));
const NotFound = lazy(() => import("./pages/NotFound"));
const SettingsUsersPage = lazy(() => import("./pages/SettingsUsersPage"));
const SettingsGroupsPage = lazy(() => import("./pages/SettingsGroupsPage"));
const SettingsPermissionsPage = lazy(() => import("./pages/SettingsPermissionsPage"));
// New Settings Pages with Layout
const SettingsLayout = lazy(() => import("./components/settings/SettingsLayout"));
const SettingsIndexRedirect = lazy(() =>
  import("./components/settings/SettingsLayout").then((mod) => ({ default: mod.SettingsIndexRedirect })),
);
const SettingsReadinessPage = lazy(() => import("./pages/settings/SettingsReadinessPage"));
const SettingsAppearancePage = lazy(() => import("./pages/settings/SettingsAppearancePage"));
const SettingsLimitsPage = lazy(() => import("./pages/settings/SettingsLimitsPage"));
const SettingsAIPage = lazy(() => import("./pages/settings/SettingsAIPage"));
const SettingsAIConnectionsPage = lazy(() => import("./pages/settings/SettingsAIConnectionsPage"));
const SettingsAccessPage = lazy(() => import("./pages/settings/SettingsAccessPage"));
const SettingsMemoryPage = lazy(() => import("./pages/settings/SettingsMemoryPage"));
const SettingsAuditPage = lazy(() => import("./pages/settings/SettingsAuditPage"));
const SettingsSSOPage = lazy(() => import("./pages/settings/SettingsSSOPage"));
const SettingsKubernetesPage = lazy(() => import("./pages/settings/SettingsKubernetesPage"));
const SettingsPluginsPage = lazy(() => import("./pages/plugin-marketplace/InstalledPluginsPage"));
const PluginPageHost = lazy(() => import("./plugins/PluginPageHost"));
const AgentsPage = lazy(() => import("./pages/AgentsPage"));
const AgentRunPage = lazy(() => import("./pages/AgentRunPage"));
const ChatPage = lazy(() => import("./pages/ChatPage"));
const StudioPage = lazy(() => import("./pages/StudioPage"));
const StudioDraftsPage = lazy(() => import("./pages/StudioDraftsPage"));
const PipelineEditorPage = lazy(() => import("./pages/PipelineEditorPage"));
const PipelineRunsPage = lazy(() => import("./pages/PipelineRunsPage"));
const AgentConfigPage = lazy(() => import("./pages/AgentConfigPage"));
const StudioSkillsPage = lazy(() => import("./pages/StudioSkillsPage"));
const NotificationsSettingsPage = lazy(() => import("./pages/NotificationsSettingsPage"));
const MCPHubPage = lazy(() => import("./pages/MCPHubPage"));
const KubernetesPage = lazy(() => import("./pages/KubernetesPage"));
const KubernetesAdminPage = lazy(() => import("./pages/KubernetesAdminPage"));
const KubernetesClusterDetailPage = lazy(() => import("./pages/KubernetesClusterDetailPage"));
const KubernetesFleetPage = lazy(() => import("./pages/KubernetesFleetPage"));
const KubernetesDevtronPage = lazy(() => import("./pages/KubernetesDevtronPage"));
const MarsPage = lazy(() => import("./pages/MarsPage"));
const MarsRunPage = lazy(() => import("./pages/MarsRunPage"));
const MonitoringInsightsPage = lazy(() => import("./pages/monitoring-insights/MonitoringInsightsPage"));

function RouteLoader() {
  const { t } = useI18n();
  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-6">
      <div className="flex items-center gap-3 rounded-xl border border-border bg-card px-5 py-3.5 text-sm text-muted-foreground shadow-sm">
        <span className="relative flex h-2.5 w-2.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-primary" />
        </span>
        {t("app.loading_workspace")}
      </div>
    </div>
  );
}

function AuthGate({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { t } = useI18n();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">
        {t("loading")}
      </div>
    );
  }

  if (isError) {
    return <SessionUnavailable onRetry={() => void refetch()} />;
  }

  if (!data?.authenticated) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <>{children}</>;
}

function PermissionDenied() {
  const { t } = useI18n();
  const { data } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const destination = firstAllowedApplicationPath(data?.user);
  return (
    <div className="flex min-h-full items-center justify-center px-6 py-12">
      <section className="max-w-lg rounded-xl border border-border bg-card px-6 py-6 shadow-sm">
        <div className="text-xs font-semibold uppercase tracking-wide text-primary">
          {t("app.permission_denied_kicker")}
        </div>
        <h1 className="mt-3 text-2xl font-semibold text-foreground">
          {t("app.permission_denied_title")}
        </h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          {t("app.permission_denied_desc")}
        </p>
        {destination ? <Link
          to={destination}
          className="mt-5 inline-flex min-h-10 items-center rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {t("app.permission_denied_action")}
        </Link> : null}
      </section>
    </div>
  );
}

function SessionUnavailable({ onRetry }: { onRetry: () => void }) {
  const { lang } = useI18n();
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-6 py-12">
      <section role="alert" className="w-full max-w-lg rounded-xl border border-warning/35 bg-card p-6 shadow-sm">
        <AlertCircle className="h-6 w-6 text-warning" aria-hidden />
        <h1 className="mt-3 text-xl font-semibold text-foreground">
          {localize(lang, "Сервис временно недоступен", "Service temporarily unavailable")}
        </h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {localize(
            lang,
            "Сеанс не завершён. WebTerm не смог проверить его из-за ошибки соединения.",
            "Your session was not signed out. WebTerm could not verify it because of a connection error.",
          )}
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-5 inline-flex min-h-10 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <RefreshCw className="h-4 w-4" aria-hidden />
          {localize(lang, "Повторить проверку", "Retry session check")}
        </button>
      </section>
    </main>
  );
}

function FeatureGate({
  feature,
  children,
  staffOnly = false,
  aiRoutingOnly = false,
}: {
  feature: string | string[];
  children: ReactNode;
  /** Require an admin (is_staff) in addition to the feature. */
  staffOnly?: boolean;
  /** Require the explicit platform AI-settings capability. */
  aiRoutingOnly?: boolean;
}) {
  const location = useLocation();
  const { data, isLoading } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });

  if (isLoading) return <RouteLoader />;

  if (!data?.authenticated) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  if (staffOnly && !data.user?.is_staff) {
    return <PermissionDenied />;
  }

  if (aiRoutingOnly && !canManageAiRouting(data.user)) {
    return <PermissionDenied />;
  }

  const allowed = Array.isArray(feature)
    ? hasAnyFeatureAccess(data.user, feature)
    : feature === "studio"
      ? canAccessStudio(data.user)
      : hasFeatureAccess(data.user, feature);

  if (!allowed) {
    return <PermissionDenied />;
  }

  return <>{children}</>;
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AppMotionProvider>
      <UiStyleProvider>
      <I18nProvider>
        <TooltipProvider>
          <Toaster />
          <BrowserRouter basename={(import.meta.env.BASE_URL || "/").replace(/\/$/, "") || "/"}>
          <Suspense fallback={<RouteLoader />}>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route
                element={
                  <AuthGate>
                    <FirstRunReadinessGate>
                      <AppLayout />
                    </FirstRunReadinessGate>
                  </AuthGate>
                }
              >
                <Route path="/" element={<Index />} />
                <Route
                  path="/dashboard"
                  element={(
                    <FeatureGate feature="dashboard">
                      <DashboardRouter />
                    </FeatureGate>
                  )}
                />
                <Route path="/admin" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard/admin" element={<Navigate to="/dashboard" replace />} />
                <Route
                  path="/monitoring/insights"
                  element={(
                    <FeatureGate feature="dashboard" staffOnly>
                      <MonitoringInsightsPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/servers"
                  element={(
                    <FeatureGate feature="servers">
                      <Servers />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/automation/*"
                  element={(
                    <FeatureGate feature="automation">
                      <AutomationPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/servers/hub"
                  element={(
                    <FeatureGate feature="servers">
                      <TerminalPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/servers/:id/terminal"
                  element={(
                    <FeatureGate feature="servers">
                      <TerminalPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/agents"
                  element={(
                    <FeatureGate feature="agents">
                      <AgentsPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/agents/run/:runId"
                  element={(
                    <FeatureGate feature="agents">
                      <AgentRunPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/chat"
                  element={(
                    <FeatureGate feature="chat">
                      <ChatPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/studio"
                  element={(
                    <FeatureGate feature="studio">
                      <StudioPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/studio/drafts"
                  element={(
                    <FeatureGate feature="studio_pipelines">
                      <StudioDraftsPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/studio/pipeline/:id"
                  element={(
                    <FeatureGate feature="studio_pipelines">
                      <PipelineEditorPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/studio/pipeline/new"
                  element={(
                    <FeatureGate feature="studio_pipelines">
                      <PipelineEditorPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/studio/runs"
                  element={(
                    <FeatureGate feature="studio_runs">
                      <PipelineRunsPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/studio/agents"
                  element={(
                    <FeatureGate feature="studio_agents">
                      <AgentConfigPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/studio/skills"
                  element={(
                    <FeatureGate feature="studio_skills">
                      <StudioSkillsPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/studio/mcp"
                  element={(
                    <FeatureGate feature="studio_mcp">
                      <MCPHubPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/studio/notifications"
                  element={(
                    <FeatureGate feature="studio_notifications">
                      <NotificationsSettingsPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/kubernetes"
                  element={(
                    <FeatureGate feature="kubernetes">
                      <KubernetesPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/kubernetes/admin"
                  element={(
                    <FeatureGate feature="kubernetes">
                      <KubernetesAdminPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/kubernetes/clusters/:clusterId"
                  element={(
                    <FeatureGate feature="kubernetes">
                      <KubernetesClusterDetailPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/kubernetes/fleet"
                  element={(
                    <FeatureGate feature="kubernetes">
                      <KubernetesFleetPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/kubernetes/devtron"
                  element={(
                    <FeatureGate feature="kubernetes">
                      <KubernetesDevtronPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/mars"
                  element={(
                    <FeatureGate feature="mars">
                      <MarsPage />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/mars/runs/:runId"
                  element={(
                    <FeatureGate feature="mars">
                      <MarsRunPage />
                    </FeatureGate>
                  )}
                />
                {/* Settings with new layout */}
                <Route
                  path="/settings"
                  element={(
                    <FeatureGate feature={["settings", "ai_connections_personal", "ai_connections_admin"]}>
                      <SettingsLayout />
                    </FeatureGate>
                  )}
                >
                  <Route index element={<SettingsIndexRedirect />} />
                  <Route
                    path="appearance"
                    element={(
                      <FeatureGate feature="settings">
                        <SettingsAppearancePage />
                      </FeatureGate>
                    )}
                  />
                  <Route
                    path="readiness"
                    element={(
                      <FeatureGate feature="settings">
                        <SettingsReadinessPage />
                      </FeatureGate>
                    )}
                  />
                  <Route
                    path="limits"
                    element={(
                      <FeatureGate feature="settings">
                        <SettingsLimitsPage />
                      </FeatureGate>
                    )}
                  />
                  <Route
                    path="ai"
                    element={(
                      <FeatureGate feature="settings" aiRoutingOnly>
                        <SettingsAIPage />
                      </FeatureGate>
                    )}
                  />
                  <Route
                    path="ai-connections"
                    element={(
                      <FeatureGate feature={["ai_connections_personal", "ai_connections_admin"]} aiRoutingOnly>
                        <SettingsAIConnectionsPage />
                      </FeatureGate>
                    )}
                  />
                  <Route
                    path="access"
                    element={(
                      <FeatureGate feature="settings">
                        <SettingsAccessPage />
                      </FeatureGate>
                    )}
                  />
                  <Route
                    path="users"
                    element={(
                      <FeatureGate feature="settings">
                        <SettingsUsersPage />
                      </FeatureGate>
                    )}
                  />
                  <Route
                    path="groups"
                    element={(
                      <FeatureGate feature="settings">
                        <SettingsGroupsPage />
                      </FeatureGate>
                    )}
                  />
                  <Route
                    path="permissions"
                    element={(
                      <FeatureGate feature="settings">
                        <SettingsPermissionsPage />
                      </FeatureGate>
                    )}
                  />
                  <Route
                    path="sso"
                    element={(
                      <FeatureGate feature="settings">
                        <SettingsSSOPage />
                      </FeatureGate>
                    )}
                  />
                  <Route
                    path="memory"
                    element={(
                      <FeatureGate feature="settings">
                        <SettingsMemoryPage />
                      </FeatureGate>
                    )}
                  />
                  <Route
                    path="audit"
                    element={(
                      <FeatureGate feature="settings">
                        <SettingsAuditPage />
                      </FeatureGate>
                    )}
                  />
                  <Route
                    path="notifications"
                    element={(
                      <FeatureGate feature="settings">
                        <NotificationsSettingsPage showStudioNav={false} />
                      </FeatureGate>
                    )}
                  />
                  <Route
                    path="kubernetes"
                    element={(
                      <FeatureGate feature="kubernetes" staffOnly>
                        <SettingsKubernetesPage />
                      </FeatureGate>
                    )}
                  />
                  <Route
                    path="plugins"
                    element={(
                      <FeatureGate feature="plugins" staffOnly>
                        <SettingsPluginsPage />
                      </FeatureGate>
                    )}
                  />
                </Route>
                <Route
                  path="/plugins/:pluginId/:pageId"
                  element={(
                    <FeatureGate feature="plugins" staffOnly>
                      <PluginPageHost />
                    </FeatureGate>
                  )}
                />
                <Route
                  path="/marketplace"
                  element={(
                    <FeatureGate feature="plugins" staffOnly>
                      <Navigate to="/settings/plugins" replace />
                    </FeatureGate>
                  )}
                />
              </Route>
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
          </BrowserRouter>
        </TooltipProvider>
      </I18nProvider>
      </UiStyleProvider>
    </AppMotionProvider>
  </QueryClientProvider>
);

export default App;
