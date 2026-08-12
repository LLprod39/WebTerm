import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchAuthSession,
  fetchFrontendBootstrap,
  type FrontendGroup,
  type FrontendServer,
  type ServerGroupRole,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { hasFeatureAccess } from "@/lib/featureAccess";
import { Navigate, useLocation } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PageShell, QueryStateBlock } from "@/components/ui/page-shell";
import { SkeletonList, SkeletonMetrics } from "@/components/ui/list-state";
import { ServersPageView } from "./servers/ServersPageView";
import type { AdvancedTab, MainTab } from "./servers/types";
import { useServerCommandController } from "./servers/useServerCommandController";
import { useServerCrudController } from "./servers/useServerCrudController";
import { useServerGroupController } from "./servers/useServerGroupController";
import { useServerKnowledgeController } from "./servers/useServerKnowledgeController";
import { useServerRulesController } from "./servers/useServerRulesController";
import { useServerSecurityController } from "./servers/useServerSecurityController";
import { useServersFleetHealth } from "./servers/useServersFleetHealth";
import { useServersListController } from "./servers/useServersListController";
import { useServerSharesController } from "./servers/useServerSharesController";

export default function Servers() {
  const location = useLocation();
  const requestedTab = (location.state as { mainTab?: string } | null)?.mainTab;

  if (requestedTab === "playbook") {
    return <Navigate to="/automation" replace />;
  }

  const supportedTab: MainTab | undefined =
    requestedTab === "groups" || requestedTab === "rules" || requestedTab === "servers"
      ? requestedTab
      : undefined;

  return <ServersWorkspace requestedTab={supportedTab} />;
}

function ServersWorkspace({ requestedTab }: { requestedTab?: MainTab }) {
  const { t, lang } = useI18n();
  const tr = useCallback((key: string, vars?: Record<string, string | number>) => {
    let text = t(key);
    if (!vars) return text;

    for (const [name, value] of Object.entries(vars)) {
      text = text.split(`{${name}}`).join(String(value));
    }

    return text;
  }, [t]);
  const queryClient = useQueryClient();
  const reload = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["frontend", "bootstrap"] });
    await queryClient.invalidateQueries({ queryKey: ["settings", "activity"] });
  }, [queryClient]);
  const [advancedTab, setAdvancedTab] = useState<AdvancedTab>("access");
  const [mainTab, setMainTab] = useState<MainTab>(requestedTab ?? "servers");

  useEffect(() => {
    if (requestedTab) {
      setMainTab(requestedTab);
    }
  }, [requestedTab]);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [advancedServer, setAdvancedServer] = useState<FrontendServer | null>(null);
  const [advancedLoading, setAdvancedLoading] = useState(false);
  const closeAdvancedServerIfDeleted = useCallback((serverId: number) => {
    if (advancedServer?.id !== serverId) return;
    setAdvancedOpen(false);
    setAdvancedServer(null);
  }, [advancedServer?.id]);
  const { data: authData } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const canConfigureElevatedAccess = authData?.user?.access_profile === "pilot_operator"
    && hasFeatureAccess(authData.user, "automation");
  const {
    canConfigureElevatedAccess: serverAccessCanBeConfigured,
    closeHostKeyEnrollment,
    confirmHostKeyEnrollment,
    dialogOpen,
    editingServer,
    form,
    formValidation,
    handlePrivateKeyFile,
    hostKeyEnrollmentTarget,
    openCreate,
    openEdit,
    requestDeleteServer,
    saveAndTestServer,
    saveServer,
    saving,
    serverDeleteTarget,
    setDialogOpen,
    setForm,
    clearServerDeleteTarget,
    confirmDeleteServer,
    testConnection,
    testingConnection,
  } = useServerCrudController({
    canConfigureElevatedAccess,
    onServerDeleted: closeAdvancedServerIfDeleted,
    reload,
    t,
    tr,
  });
  const {
    clearGroupDeleteTarget,
    closeGroupDialog,
    confirmDeleteGroup,
    editingGroup,
    groupDeleteTarget,
    groupDialogOpen,
    groupForm,
    groupSaving,
    openCreateGroup,
    openGroupSettings,
    requestDeleteGroup,
    saveGroup,
    setGroupDialogOpen,
    setGroupForm,
  } = useServerGroupController({ reload });
  const sharesController = useServerSharesController(advancedServer);
  const knowledgeController = useServerKnowledgeController(advancedServer, t, tr);
  const securityController = useServerSecurityController(advancedServer, t);
  const commandController = useServerCommandController(advancedServer, t, tr);
  const { data, isLoading, error } = useQuery({
    queryKey: ["frontend", "bootstrap"],
    queryFn: fetchFrontendBootstrap,
    staleTime: 20_000,
  });
  const servers = useMemo(() => data?.servers ?? [], [data?.servers]);
  const { fleetHealthByServerId } = useServersFleetHealth(servers, mainTab);

  const serverListUserKey = authData?.user?.id != null ? `id:${authData.user.id}` : undefined;
  const serversList = useServersListController(servers, serverListUserKey);
  const { collapsed, filtered, grouped, onlineCount, search, setSearch, toggleGroup } = serversList;
  const groups = useMemo(() => (Array.isArray(data?.groups) ? data.groups : []), [data?.groups]);
  const manageableGroups = useMemo(
    () =>
      (groups ?? []).filter(
        (group): group is FrontendGroup & { id: number; role: ServerGroupRole } =>
          group.id !== null && Boolean(group.role),
      ),
    [groups],
  );
  const sharedCount = (servers ?? []).filter((server) => server.is_shared).length;
  const groupCount = manageableGroups.length;
  const offlineCount = Math.max(0, servers.length - onlineCount);

  const rulesController = useServerRulesController({
    activeServer: advancedServer,
    manageableGroups,
    mainTab,
    reload,
    t,
    tr,
  });

  const openGroupRules = (groupId: number) => {
    closeGroupDialog();
    rulesController.selectGroupRules(groupId);
    setMainTab("rules");
  };

  const openAdvanced = async (server: FrontendServer) => {
    setAdvancedServer(server);
    setAdvancedOpen(true);
    setAdvancedLoading(true);
    setAdvancedTab("access");
    commandController.resetResult();
    securityController.resetForAdvancedOpen();
    knowledgeController.resetForAdvancedOpen();
    try {
      await Promise.all([
        sharesController.loadForServer(server.id).catch(() => []),
        knowledgeController.loadForServer(server.id).catch(() => null),
        rulesController.loadForAdvancedServer(server).catch(() => null),
        securityController.loadMasterPasswordStatus(),
      ]);
    } finally {
      setAdvancedLoading(false);
    }
  };

  const openInheritedRules = useCallback(() => {
    if (advancedServer?.group_id && manageableGroups.some((group) => group.id === advancedServer.group_id)) {
      rulesController.selectGroupRules(advancedServer.group_id);
    } else {
      rulesController.selectGlobalRules();
    }
    setMainTab("rules");
    setAdvancedOpen(false);
  }, [advancedServer?.group_id, manageableGroups, rulesController]);

  if (isLoading || error || !data) {
    if (isLoading) {
      return (
        <PageShell className="space-y-4">
          <SkeletonMetrics count={4} />
          <SkeletonList rows={6} />
        </PageShell>
      );
    }
    return (
      <QueryStateBlock
        loading={false}
        error={error || (!data ? new Error(t("srv.error")) : undefined)}
        errorText={t("srv.error")}
        className="p-6"
      >
        {null}
      </QueryStateBlock>
    );
  }

  return (
    <ServersPageView
      t={t}
      tr={tr}
      lang={lang}
      mainTab={mainTab}
      setMainTab={setMainTab}
      servers={servers}
      manageableGroups={manageableGroups}
      groupCount={groupCount}
      sharedCount={sharedCount}
      onlineCount={onlineCount}
      offlineCount={offlineCount}
      search={search}
      setSearch={setSearch}
      collapsed={collapsed}
      filtered={filtered}
      grouped={grouped}
      toggleGroup={toggleGroup}
      fleetHealthByServerId={fleetHealthByServerId}
      openCreate={openCreate}
      openEdit={openEdit}
      requestDeleteServer={requestDeleteServer}
      dialogOpen={dialogOpen}
      setDialogOpen={setDialogOpen}
      editingServer={editingServer}
      form={form}
      formValidation={formValidation}
      handlePrivateKeyFile={handlePrivateKeyFile}
      setForm={setForm}
      saveServer={saveServer}
      saveAndTestServer={saveAndTestServer}
      testConnection={testConnection}
      saving={saving}
      testingConnection={testingConnection}
      canConfigureElevatedAccess={serverAccessCanBeConfigured}
      serverDeleteTarget={serverDeleteTarget}
      clearServerDeleteTarget={clearServerDeleteTarget}
      confirmDeleteServer={confirmDeleteServer}
      hostKeyEnrollmentTarget={hostKeyEnrollmentTarget}
      closeHostKeyEnrollment={closeHostKeyEnrollment}
      confirmHostKeyEnrollment={confirmHostKeyEnrollment}
      openCreateGroup={openCreateGroup}
      openGroupSettings={openGroupSettings}
      requestDeleteGroup={requestDeleteGroup}
      openGroupRules={openGroupRules}
      groupDialogOpen={groupDialogOpen}
      setGroupDialogOpen={setGroupDialogOpen}
      editingGroup={editingGroup}
      groupForm={groupForm}
      setGroupForm={setGroupForm}
      groupSaving={groupSaving}
      closeGroupDialog={closeGroupDialog}
      saveGroup={saveGroup}
      groupDeleteTarget={groupDeleteTarget}
      clearGroupDeleteTarget={clearGroupDeleteTarget}
      confirmDeleteGroup={confirmDeleteGroup}
      advancedOpen={advancedOpen}
      setAdvancedOpen={setAdvancedOpen}
      advancedServer={advancedServer}
      advancedTab={advancedTab}
      setAdvancedTab={setAdvancedTab}
      advancedLoading={advancedLoading}
      openAdvanced={openAdvanced}
      openInheritedRules={openInheritedRules}
      commandController={commandController}
      knowledgeController={knowledgeController}
      rulesController={rulesController}
      securityController={securityController}
      sharesController={sharesController}
    />
  );
}
