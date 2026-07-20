import { useCallback, useEffect, useMemo, useState } from "react";
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
import { localize, useI18n } from "@/lib/i18n";
import {
  Plus,
  Search,
  Server,
  Settings,
  Layers,
  BookOpen,
} from "lucide-react";
import { useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { DeleteDialog } from "@/components/system/ConfirmDialog";
import { ContentPanel } from "@/components/system/ContentPanel";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PageShell, QueryStateBlock, SoftHeader, StatStrip, StatStripItem } from "@/components/ui/page-shell";
import { SkeletonList, SkeletonMetrics } from "@/components/ui/list-state";
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
import { isFreshLiveSample, statusFromLiveMetrics, useMonitoringLive } from "./servers/useMonitoringLive";
import { useServersListController } from "./servers/useServersListController";
import { useServerSharesController } from "./servers/useServerSharesController";
import { PlaybooksWorkspace } from "./automation/PlaybooksWorkspace";

export default function Servers() {
  const { t, lang } = useI18n();
  const location = useLocation();
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
  const initialTab = (location.state as { mainTab?: MainTab } | null)?.mainTab;
  const [mainTab, setMainTab] = useState<MainTab>(
    initialTab === "playbook" || initialTab === "groups" || initialTab === "rules" || initialTab === "servers"
      ? initialTab
      : "servers",
  );

  useEffect(() => {
    const tab = (location.state as { mainTab?: MainTab } | null)?.mainTab;
    if (tab === "playbook" || tab === "groups" || tab === "rules" || tab === "servers") {
      setMainTab(tab);
    }
  }, [location.state]);
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
    formValidation,
    handlePrivateKeyFile,
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
    // Cheap DB-only read (no SSH): keep the list fresh while the page is visible.
    staleTime: 25_000,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });
  const servers = useMemo(() => data?.servers ?? [], [data?.servers]);
  // Live monitoring is always on for the servers list: backend shares one SSH
  // collector per host:port across all viewers/users.
  const liveServerIds = useMemo(() => servers.map((server) => server.id), [servers]);
  const { metricsByServerId: liveMetrics } = useMonitoringLive(
    liveServerIds,
    mainTab === "servers" && liveServerIds.length > 0,
  );

  // Backup path: when live WS is down, SSH quick metrics refresh so numbers don't
  // stay frozen for hours (lite TCP refresh does NOT update CPU/RAM/disk).
  useEffect(() => {
    if (mainTab !== "servers" || liveServerIds.length === 0) return;
    let cancelled = false;
    const pullMetrics = () => {
      void refreshMonitoringFleet({ metrics: true }).then(() => {
        if (!cancelled) {
          void queryClient.invalidateQueries({ queryKey: ["monitoring", "status"] });
          void queryClient.invalidateQueries({ queryKey: ["monitoring-dashboard"] });
        }
      });
    };
    pullMetrics();
    const timer = window.setInterval(pullMetrics, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [mainTab, liveServerIds.length, queryClient]);

  const fleetHealthByServerId = useMemo(() => {
    const map = new Map<number, MonitoringStatusItem>();
    for (const item of monitoringStatus?.servers ?? []) {
      map.set(item.server_id, item);
    }
    // Live WebSocket samples override the snapshot when fresh.
    // Partial ticks (first sample often has cpu=null until two /proc reads) must NOT
    // blank RAM/disk/CPU that we already have from a recent DB snapshot — that caused
    // chips to pop in one-by-one ~1s after open.
    const nowMs = Date.now();
    for (const [serverId, live] of liveMetrics) {
      if (!isFreshLiveSample(live, nowMs)) continue;
      const base = map.get(serverId);
      const liveStatus = statusFromLiveMetrics(live);
      const serverMeta = servers.find((s) => s.id === serverId);
      // Only fill null live fields from a non-stale DB snapshot (avoid days-old 100% CPU).
      const baseMetricsFresh =
        Boolean(base) &&
        !base!.is_stale &&
        (base!.metrics_age_seconds == null || base!.metrics_age_seconds <= 300);
      const pickMetric = (liveVal: number | null | undefined, baseVal: number | null | undefined) =>
        liveVal ?? (baseMetricsFresh ? (baseVal ?? null) : null);
      map.set(serverId, {
        server_id: serverId,
        server_name: base?.server_name || serverMeta?.name || "",
        host: base?.host || serverMeta?.host || "",
        server_type: base?.server_type || serverMeta?.server_type || "",
        status: liveStatus,
        checked_at: base?.checked_at ?? null,
        age_seconds: 0,
        is_stale: false,
        response_time_ms: base?.response_time_ms ?? null,
        cpu_percent: pickMetric(live.cpu_percent, base?.cpu_percent),
        memory_percent: pickMetric(live.memory_percent, base?.memory_percent),
        disk_percent: pickMetric(live.disk_percent, base?.disk_percent),
        load_1m: pickMetric(live.load_1m, base?.load_1m),
        metrics_checked_at: new Date(nowMs).toISOString(),
        metrics_age_seconds: 0,
        is_lite: false,
      });
    }
    return map;
  }, [monitoringStatus, liveMetrics, servers]);
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
  const isAdmin = authData?.user?.is_staff ?? false;

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
    <PageShell width="7xl" className="space-y-4">
      <SoftHeader
        compact
        title={t("srv.title")}
        count={servers.length > 0 ? servers.length : undefined}
        subtitle={localize(lang, "Серверы, группы и runbook", "Servers, groups, and runbooks")}
        actions={
          <>
            <div className="relative w-full sm:w-auto">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder={t("srv.search")}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-9 w-full pl-9 text-sm sm:w-72"
              />
            </div>
            <Button className="gap-1.5" onClick={openCreate}>
              <Plus className="h-4 w-4" /> {t("srv.add")}
            </Button>
          </>
        }
      />

      {servers.length > 0 ? (
        <StatStrip>
          <StatStripItem
            label={localize(lang, "Всего", "Total")}
            value={servers.length}
            hint={localize(lang, "серверы", "servers")}
          />
          <StatStripItem
            label={localize(lang, "Онлайн", "Online")}
            value={onlineCount}
            tone={onlineCount > 0 ? "success" : "default"}
            hint={tr("srv.online_count", { count: onlineCount })}
          />
          <StatStripItem
            label={localize(lang, "Офлайн", "Offline")}
            value={offlineCount}
            tone={offlineCount > 0 ? "warning" : "default"}
            hint={localize(lang, "нет связи / unknown", "unreachable / unknown")}
          />
          <StatStripItem
            label={localize(lang, "Группы", "Groups")}
            value={groupCount}
            hint={
              sharedCount > 0
                ? tr("srv.shared_count", { count: sharedCount })
                : localize(lang, "управляемые", "manageable")
            }
          />
        </StatStrip>
      ) : null}

      <Tabs value={mainTab} onValueChange={(v) => setMainTab(v as MainTab)} className="space-y-3">
        <TabsList className="h-auto justify-start gap-1 rounded-sm border border-border bg-surface-0 p-0.5">
          <TabsTrigger value="servers" className="min-h-9 gap-2 px-3 text-sm">
            <Server className="h-4 w-4" /> {t("srv.list")}
          </TabsTrigger>
          <TabsTrigger value="groups" className="min-h-9 gap-2 px-3 text-sm">
            <Layers className="h-4 w-4" /> {t("srv.groups")}
          </TabsTrigger>
          <TabsTrigger value="rules" className="min-h-9 gap-2 px-3 text-sm">
            <Settings className="h-4 w-4" /> {t("srv.rules_tab")}
          </TabsTrigger>
          <TabsTrigger value="playbook" className="min-h-9 gap-2 px-3 text-sm">
            <BookOpen className="h-4 w-4" /> {t("pb.title")}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="servers" className="mt-0 space-y-3">
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

        <TabsContent value="groups" className="mt-0 space-y-3">
          <ContentPanel className="p-4 sm:p-5">
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
          </ContentPanel>
        </TabsContent>

        <TabsContent value="rules" className="mt-0 space-y-3">
          <ContentPanel className="p-4 sm:p-5">
            <ServerRulesTab
              controller={rulesController}
              manageableGroups={manageableGroups}
              t={t}
              tr={tr}
            />
          </ContentPanel>
        </TabsContent>

        <TabsContent value="playbook" className="mt-0 space-y-3">
          <ContentPanel className="p-4 sm:p-5">
            <PlaybooksWorkspace
              servers={servers}
              groups={groups}
              enabled={mainTab === "playbook"}
            />
          </ContentPanel>
        </TabsContent>
      </Tabs>

      <ServerFormDialog
        editingServer={editingServer}
        form={form}
        formValidation={formValidation}
        handlePrivateKeyFile={handlePrivateKeyFile}
        manageableGroups={manageableGroups}
        onSave={saveServer}
        onSaveAndTest={saveAndTestServer}
        onTestConnection={testConnection}
        open={dialogOpen}
        saving={saving}
        setDialogOpen={setDialogOpen}
        setForm={setForm}
        t={t}
        testingConnection={testingConnection}
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

      <DeleteDialog
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

      <DeleteDialog
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
