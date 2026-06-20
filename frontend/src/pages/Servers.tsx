import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchAuthSession,
  fetchFrontendBootstrap,
  fetchMonitoringStatus,
  refreshMonitoringFleet,
  type MonitoringStatusItem,
  type FrontendGroup,
  type FrontendServer,
  type ServerGroupRole,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  Plus,
  Search,
  Server,
  Settings,
  Layers,
  BookOpen,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHero, PageShell, QueryStateBlock } from "@/components/ui/page-shell";
import { PlaybooksPanel, usePlaybooksPanel } from "./servers/PlaybooksPanel";
import { ServerAdvancedDialog } from "./servers/ServerAdvancedDialog";
import { ServerFormDialog } from "./servers/ServerFormDialog";
import { ServerGroupDialog } from "./servers/ServerGroupDialog";
import { ServerGroupsTab } from "./servers/ServerGroupsTab";
import { ServerKnowledgeDialogs } from "./servers/ServerKnowledgeDialogs";
import { ServerRulesTab } from "./servers/ServerRulesTab";
import { ServersListTab } from "./servers/ServersListTab";
import type {
  AdvancedTab,
  MainTab,
} from "./servers/types";
import { useServerCommandController } from "./servers/useServerCommandController";
import { useServerCrudController } from "./servers/useServerCrudController";
import { useServerGroupController } from "./servers/useServerGroupController";
import { useServerKnowledgeController } from "./servers/useServerKnowledgeController";
import { useServerRulesController } from "./servers/useServerRulesController";
import { useServerSecurityController } from "./servers/useServerSecurityController";
import { useServersListController } from "./servers/useServersListController";
import { useServerSharesController } from "./servers/useServerSharesController";

export default function Servers() {
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
  const [mainTab, setMainTab] = useState<MainTab>("servers");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [advancedServer, setAdvancedServer] = useState<FrontendServer | null>(null);
  const [advancedLoading, setAdvancedLoading] = useState(false);
  const closeAdvancedServerIfDeleted = useCallback((serverId: number) => {
    if (advancedServer?.id !== serverId) return;
    setAdvancedOpen(false);
    setAdvancedServer(null);
  }, [advancedServer?.id]);
  const {
    dialogOpen,
    editingServer,
    form,
    handlePrivateKeyFile,
    openCreate,
    openEdit,
    requestDeleteServer,
    saveServer,
    saving,
    serverDeleteTarget,
    setDialogOpen,
    setForm,
    sudoPasswordRequired,
    clearServerDeleteTarget,
    confirmDeleteServer,
  } = useServerCrudController({
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
  const { data: authData } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const { data: monitoringStatus } = useQuery({
    queryKey: ["monitoring", "status"],
    queryFn: fetchMonitoringStatus,
    staleTime: 60_000,
    refetchInterval: 90_000,
    refetchIntervalInBackground: true,
  });
  const fleetHealthByServerId = useMemo(() => {
    const map = new Map<number, MonitoringStatusItem>();
    for (const item of monitoringStatus?.servers ?? []) {
      map.set(item.server_id, item);
    }
    return map;
  }, [monitoringStatus]);
  const servers = useMemo(() => data?.servers ?? [], [data?.servers]);
  const serversList = useServersListController(servers);
  const { collapsed, filtered, grouped, onlineCount, search, setSearch, toggleGroup } = serversList;
  const playbooksPanel = usePlaybooksPanel({ servers, t, tr, lang });
  const groups = useMemo(() => data?.groups ?? [], [data?.groups]);
  const manageableGroups = useMemo(
    () =>
      groups.filter(
        (group): group is FrontendGroup & { id: number; role: ServerGroupRole } =>
          group.id !== null && Boolean(group.role),
      ),
    [groups],
  );
  const sharedCount = servers.filter((server) => server.is_shared).length;
  const groupCount = manageableGroups.length;
  const isAdmin = authData?.user?.is_staff ?? false;

  const fleetRefreshRequested = useRef(false);
  useEffect(() => {
    if (!monitoringStatus?.meta?.has_stale || fleetRefreshRequested.current) return;
    fleetRefreshRequested.current = true;
    void refreshMonitoringFleet().then(() => {
      void queryClient.invalidateQueries({ queryKey: ["monitoring", "status"] });
    });
  }, [monitoringStatus?.meta?.has_stale, queryClient]);

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
    return (
      <QueryStateBlock
        loading={isLoading}
        error={error || (!isLoading && !data ? new Error(t("srv.error")) : undefined)}
        errorText={t("srv.error")}
        className="p-6"
      >
        {null}
      </QueryStateBlock>
    );
  }

  return (
    <PageShell width="full" className="max-w-[1500px]">
      <PageHero
        kicker="Inventory"
        title={t("srv.title")}
        description={t("srv.groups_description")}
        actions={
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
            <div className="relative w-full sm:w-auto">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder={t("srv.search")}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-10 w-full border-border bg-background pl-9 text-sm sm:w-64"
              />
            </div>
            <Button size="sm" className="h-10 gap-1.5 text-sm" onClick={openCreate}>
              <Plus className="h-4 w-4" /> {t("srv.add")}
            </Button>
          </div>
        }
      />

      <Tabs value={mainTab} onValueChange={(v) => setMainTab(v as MainTab)} className="space-y-3">
        <TabsList className="h-auto w-full justify-start gap-1 overflow-x-auto p-1">
          <TabsTrigger value="servers" className="min-h-10 gap-2 px-3">
            <Server className="h-4 w-4" /> {t("srv.list")}
          </TabsTrigger>
          <TabsTrigger value="groups" className="min-h-10 gap-2 px-3">
            <Layers className="h-4 w-4" /> {t("srv.groups")}
          </TabsTrigger>
          <TabsTrigger value="rules" className="min-h-10 gap-2 px-3">
            <Settings className="h-4 w-4" /> {t("srv.rules_tab")}
          </TabsTrigger>
          <TabsTrigger value="playbook" className="min-h-10 gap-2 px-3">
            <BookOpen className="h-4 w-4" /> {t("pb.title")}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="servers" className="space-y-3">
          <ServersListTab
            grouped={grouped}
            filteredCount={filtered.length}
            totalServers={servers.length}
            collapsed={collapsed}
            fleetHealthByServerId={fleetHealthByServerId}
            t={t}
            tr={tr}
            lang={lang}
            onToggleGroup={toggleGroup}
            onOpenCreate={openCreate}
            onOpenAdvanced={openAdvanced}
            onOpenEdit={openEdit}
            onRequestDeleteServer={requestDeleteServer}
            onClearSearch={() => setSearch("")}
          />
        </TabsContent>

        <TabsContent value="groups" className="space-y-3">
          <ServerGroupsTab
            manageableGroups={manageableGroups}
            groupCount={groupCount}
            t={t}
            tr={tr}
            onOpenCreateGroup={openCreateGroup}
            onOpenGroupRules={openGroupRules}
            onOpenGroupSettings={openGroupSettings}
            onRequestDeleteGroup={requestDeleteGroup}
          />
        </TabsContent>

        <TabsContent value="rules" className="space-y-3">
          <ServerRulesTab
            controller={rulesController}
            manageableGroups={manageableGroups}
            t={t}
            tr={tr}
          />
        </TabsContent>

        <TabsContent value="playbook" className="space-y-3">
          <PlaybooksPanel {...playbooksPanel} />
        </TabsContent>
      </Tabs>

      <ServerFormDialog
        editingServer={editingServer}
        form={form}
        handlePrivateKeyFile={handlePrivateKeyFile}
        manageableGroups={manageableGroups}
        onSave={saveServer}
        open={dialogOpen}
        saving={saving}
        setDialogOpen={setDialogOpen}
        setForm={setForm}
        sudoPasswordRequired={sudoPasswordRequired}
        t={t}
      />

      <ServerGroupDialog
        open={groupDialogOpen}
        editingGroup={editingGroup}
        groupForm={groupForm}
        groupSaving={groupSaving}
        t={t}
        setGroupDialogOpen={setGroupDialogOpen}
        setGroupForm={setGroupForm}
        closeGroupDialog={closeGroupDialog}
        onSaveGroup={saveGroup}
        openGroupRules={openGroupRules}
      />

      <ServerAdvancedDialog
        advancedLoading={advancedLoading}
        advancedOpen={advancedOpen}
        advancedServer={advancedServer}
        advancedTab={advancedTab}
        commandController={commandController}
        knowledgeController={knowledgeController}
        manageableGroups={manageableGroups}
        onOpenInheritedRules={openInheritedRules}
        openGroupRules={openGroupRules}
        rulesController={rulesController}
        securityController={securityController}
        setAdvancedOpen={setAdvancedOpen}
        setAdvancedTab={setAdvancedTab}
        sharesController={sharesController}
        t={t}
        tr={tr}
      />

      <ServerKnowledgeDialogs
        controller={knowledgeController}
        t={t}
      />

      <ConfirmActionDialog
        open={Boolean(serverDeleteTarget)}
        onOpenChange={(open) => {
          if (!open) clearServerDeleteTarget();
        }}
        title={serverDeleteTarget ? tr("srv.delete_server_confirm", { name: serverDeleteTarget.name }) : t("srv.delete")}
        description={t("srv.delete_server_description")}
        confirmLabel={t("srv.delete")}
        cancelLabel={t("srv.cancel")}
        onConfirm={confirmDeleteServer}
        contentClassName="max-w-sm"
      />

      <ConfirmActionDialog
        open={Boolean(groupDeleteTarget)}
        onOpenChange={(open) => {
          if (!open) clearGroupDeleteTarget();
        }}
        title={groupDeleteTarget ? tr("srv.delete_group_confirm", { name: groupDeleteTarget.name }) : t("srv.delete")}
        description={t("srv.delete_group_description")}
        confirmLabel={t("srv.delete")}
        cancelLabel={t("srv.cancel")}
        onConfirm={confirmDeleteGroup}
        contentClassName="max-w-sm"
      />
    </PageShell>
  );
}
