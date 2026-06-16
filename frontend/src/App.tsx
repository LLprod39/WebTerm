import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Suspense, lazy, type ReactNode } from "react";
import { I18nProvider, useI18n } from "./lib/i18n";
import AppLayout from "./components/AppLayout";
import { fetchAuthSession } from "./lib/api";
import { canAccessStudio, hasAnyFeatureAccess, hasFeatureAccess } from "./lib/featureAccess";

const queryClient = new QueryClient();
const Index = lazy(() => import("./pages/Index"));
const Login = lazy(() => import("./pages/Login"));
const Servers = lazy(() => import("./pages/Servers"));
const TerminalPage = lazy(() => import("./pages/TerminalPage"));
const DashboardRouter = lazy(() => import("./pages/DashboardRouter"));
const NotFound = lazy(() => import("./pages/NotFound"));
const SettingsUsersPage = lazy(() => import("./pages/SettingsUsersPage"));
const SettingsGroupsPage = lazy(() => import("./pages/SettingsGroupsPage"));
const SettingsPermissionsPage = lazy(() => import("./pages/SettingsPermissionsPage"));
// New Settings Pages with Layout
const SettingsLayout = lazy(() => import("./components/settings/SettingsLayout"));
const SettingsAIPage = lazy(() => import("./pages/settings/SettingsAIPage"));
const SettingsAccessPage = lazy(() => import("./pages/settings/SettingsAccessPage"));
const SettingsMemoryPage = lazy(() => import("./pages/settings/SettingsMemoryPage"));
const SettingsAuditPage = lazy(() => import("./pages/settings/SettingsAuditPage"));
const SettingsSSOPage = lazy(() => import("./pages/settings/SettingsSSOPage"));
const AgentsPage = lazy(() => import("./pages/AgentsPage"));
const AgentRunPage = lazy(() => import("./pages/AgentRunPage"));
const StudioPage = lazy(() => import("./pages/StudioPage"));
const StudioDraftsPage = lazy(() => import("./pages/StudioDraftsPage"));
const PipelineEditorPage = lazy(() => import("./pages/PipelineEditorPage"));
const PipelineRunsPage = lazy(() => import("./pages/PipelineRunsPage"));
const AgentConfigPage = lazy(() => import("./pages/AgentConfigPage"));
const StudioSkillsPage = lazy(() => import("./pages/StudioSkillsPage"));
const NotificationsSettingsPage = lazy(() => import("./pages/NotificationsSettingsPage"));
const MCPHubPage = lazy(() => import("./pages/MCPHubPage"));
const KubernetesPage = lazy(() => import("./pages/KubernetesPage"));
const MarsPage = lazy(() => import("./pages/MarsPage"));
const MarsRunPage = lazy(() => import("./pages/MarsRunPage"));

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
  const { data, isLoading } = useQuery({
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

  if (!data?.authenticated) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <>{children}</>;
}

function FeatureGate({
  feature,
  children,
}: {
  feature: string | string[];
  children: ReactNode;
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

  const allowed = Array.isArray(feature)
    ? hasAnyFeatureAccess(data.user, feature)
    : feature === "studio"
      ? canAccessStudio(data.user)
      : hasFeatureAccess(data.user, feature);

  if (!allowed) {
    return <Navigate to="/servers" replace />;
  }

  return <>{children}</>;
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <I18nProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <Suspense fallback={<RouteLoader />}>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route
                element={
                  <AuthGate>
                    <AppLayout />
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
                <Route path="/servers" element={<Servers />} />
                <Route path="/servers/hub" element={<TerminalPage />} />
                <Route path="/servers/:id/terminal" element={<TerminalPage />} />
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
                    <FeatureGate feature="settings">
                      <SettingsLayout />
                    </FeatureGate>
                  )}
                >
                  <Route index element={<Navigate to="/settings/ai" replace />} />
                  <Route path="ai" element={<SettingsAIPage />} />
                  <Route path="access" element={<SettingsAccessPage />} />
                  <Route path="users" element={<SettingsUsersPage />} />
                  <Route path="groups" element={<SettingsGroupsPage />} />
                  <Route path="permissions" element={<SettingsPermissionsPage />} />
                  <Route path="sso" element={<SettingsSSOPage />} />
                  <Route path="memory" element={<SettingsMemoryPage />} />
                  <Route path="audit" element={<SettingsAuditPage />} />
                </Route>
              </Route>
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </TooltipProvider>
    </I18nProvider>
  </QueryClientProvider>
);

export default App;
