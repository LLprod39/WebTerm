import type { ChangeEvent, Dispatch, SetStateAction } from "react";
import {
  type FrontendGroup,
  type FrontendServer,
  type MonitoringStatusItem,
  type ServerGroupRole,
} from "@/lib/api";
import { localize } from "@/lib/i18n";
import {
  ListFilter,
  Plus,
  Search,
  Server,
  Settings,
  Layers,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { DeleteDialog } from "@/components/system/ConfirmDialog";
import { ContentPanel } from "@/components/system/ContentPanel";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageShell } from "@/components/ui/page-shell";
import { ServerAdvancedDialog } from "./ServerAdvancedDialog";
import { ServerFormDialog } from "./ServerFormDialog";
import { ServerGroupDialog } from "./ServerGroupDialog";
import { ServerGroupsTab } from "./ServerGroupsTab";
import { ServerKnowledgeDialogs } from "./ServerKnowledgeDialogs";
import { SSHHostKeyEnrollmentDialog } from "./SSHHostKeyEnrollmentDialog";
import { ServerRulesTab } from "./ServerRulesTab";
import { ServersListTab } from "./ServersListTab";
import type {
  AdvancedTab,
  MainTab,
  ServerForm,
  ServerGroupForm,
  SSHHostKeyEnrollmentTarget,
} from "./types";
import type { ServerValidationResult } from "./serverValidation";
import { formatServerCount } from "./formatters";
import type { ServerCommandController } from "./useServerCommandController";
import type { ServerKnowledgeController } from "./useServerKnowledgeController";
import type { ServerRulesController } from "./useServerRulesController";
import type { ServerSecurityController } from "./useServerSecurityController";
import type { ServerSharesController } from "./useServerSharesController";

type ManageableGroup = FrontendGroup & { id: number; role: ServerGroupRole };
type Translate = (key: string) => string;
type TranslateVars = (key: string, vars?: Record<string, string | number>) => string;

export interface ServersPageViewProps {
  t: Translate;
  tr: TranslateVars;
  lang: string;
  mainTab: MainTab;
  setMainTab: (tab: MainTab) => void;
  servers: FrontendServer[];
  manageableGroups: ManageableGroup[];
  groupCount: number;
  search: string;
  setSearch: (value: string) => void;
  groupFilter: string;
  groupOptions: Array<{ label: string; value: string }>;
  setGroupFilter: (value: string) => void;
  collapsed: Record<string, boolean>;
  filtered: FrontendServer[];
  grouped: Record<string, FrontendServer[]>;
  toggleGroup: (group: string) => void;
  fleetHealthByServerId: Map<number, MonitoringStatusItem>;
  openCreate: () => void;
  openEdit: (server: FrontendServer) => void | Promise<void>;
  requestDeleteServer: (server: FrontendServer) => void;
  dialogOpen: boolean;
  setDialogOpen: (open: boolean) => void;
  editingServer: FrontendServer | null;
  form: ServerForm;
  formValidation: ServerValidationResult;
  handlePrivateKeyFile: (event: ChangeEvent<HTMLInputElement>) => void;
  setForm: Dispatch<SetStateAction<ServerForm>>;
  saveServer: () => void;
  saveAndTestServer: () => void | Promise<void>;
  testConnection: (server: FrontendServer) => void | Promise<void>;
  saving: boolean;
  testingConnection: boolean;
  serverDeleteTarget: FrontendServer | null;
  clearServerDeleteTarget: () => void;
  confirmDeleteServer: () => void;
  hostKeyEnrollmentTarget: SSHHostKeyEnrollmentTarget | null;
  closeHostKeyEnrollment: () => void;
  confirmHostKeyEnrollment: (fingerprint: string) => void | Promise<void>;
  openCreateGroup: () => void;
  openGroupSettings: (group: FrontendGroup) => void;
  requestDeleteGroup: (group: FrontendGroup) => void;
  openGroupRules: (groupId: number) => void;
  groupDialogOpen: boolean;
  setGroupDialogOpen: (open: boolean) => void;
  editingGroup: FrontendGroup | null;
  groupForm: ServerGroupForm;
  setGroupForm: Dispatch<SetStateAction<ServerGroupForm>>;
  groupSaving: boolean;
  closeGroupDialog: () => void;
  saveGroup: () => void;
  groupDeleteTarget: FrontendGroup | null;
  clearGroupDeleteTarget: () => void;
  confirmDeleteGroup: () => void;
  advancedOpen: boolean;
  setAdvancedOpen: (open: boolean) => void;
  advancedServer: FrontendServer | null;
  advancedTab: AdvancedTab;
  setAdvancedTab: (tab: AdvancedTab) => void;
  advancedLoading: boolean;
  openAdvanced: (server: FrontendServer) => void | Promise<void>;
  openInheritedRules: () => void;
  commandController: ServerCommandController;
  knowledgeController: ServerKnowledgeController;
  rulesController: ServerRulesController;
  securityController: ServerSecurityController;
  sharesController: ServerSharesController;
}

/** Presentational layout for the Servers page (tabs, dialogs, stats). */
export function ServersPageView(props: ServersPageViewProps) {
  const {
    t, tr, lang, mainTab, setMainTab, servers, manageableGroups, groupCount,
    search, setSearch, groupFilter, groupOptions, setGroupFilter,
    collapsed, filtered, grouped, toggleGroup,
    fleetHealthByServerId, openCreate, openEdit, requestDeleteServer, dialogOpen, setDialogOpen,
    editingServer, form, formValidation, handlePrivateKeyFile, setForm, saveServer, saveAndTestServer,
    testConnection, saving, testingConnection, serverDeleteTarget, clearServerDeleteTarget,
    confirmDeleteServer, hostKeyEnrollmentTarget, closeHostKeyEnrollment, confirmHostKeyEnrollment,
    openCreateGroup, openGroupSettings, requestDeleteGroup, openGroupRules,
    groupDialogOpen, setGroupDialogOpen, editingGroup, groupForm, setGroupForm, groupSaving,
    closeGroupDialog, saveGroup, groupDeleteTarget, clearGroupDeleteTarget, confirmDeleteGroup,
    advancedOpen, setAdvancedOpen, advancedServer, advancedTab, setAdvancedTab, advancedLoading,
    openAdvanced, openInheritedRules, commandController, knowledgeController, rulesController,
    securityController, sharesController,
  } = props;

  const primaryAction = mainTab === "servers"
    ? { label: t("srv.add"), action: openCreate }
    : mainTab === "groups"
      ? { label: t("srv.add"), action: openCreate }
      : { label: localize(lang, "Редактировать правила", "Edit rules"), action: rulesController.selectGlobalRules };

  return (
    <PageShell width="full" className="max-w-[1500px] space-y-3 pb-8">
      <header className="rounded-xl border border-border bg-card px-6 py-5">
        <div className="flex min-h-16 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="font-display text-[26px] font-bold tracking-[-0.035em] text-foreground">
                {localize(lang, "Серверы", "Servers")}
              </h1>
              {servers.length > 0 ? (
                <span className="rounded-full bg-secondary px-2.5 py-1 font-mono text-xs tabular-nums text-muted-foreground">
                  {servers.length}
                </span>
              ) : null}
            </div>
            <p className="mt-1 max-w-2xl text-sm leading-5 text-muted-foreground">
              {localize(
                lang,
                "Подключения, состояние и правила доступа к вашей серверной инфраструктуре.",
                "Connections, health, and access rules for your server infrastructure.",
              )}
            </p>
          </div>
          <Button className="h-9 gap-2 rounded-lg px-3.5" onClick={primaryAction.action}>
            {mainTab === "rules" ? <Settings className="h-4 w-4" aria-hidden /> : <Plus className="h-4 w-4" aria-hidden />} {primaryAction.label}
          </Button>
        </div>
      </header>

      <Tabs value={mainTab} onValueChange={(v) => setMainTab(v as MainTab)} className="space-y-3">
        <div className="flex flex-col gap-2 border-b border-border px-1 lg:flex-row lg:items-center lg:justify-between">
          <TabsList className="h-10 w-full justify-start gap-5 rounded-none bg-transparent p-0 lg:w-auto">
            <TabsTrigger value="servers" className="h-10 gap-2 rounded-none border-b-2 border-transparent bg-transparent px-1 text-sm shadow-none data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:shadow-none">
              <Server className="h-4 w-4" aria-hidden /> {t("srv.list")}
            </TabsTrigger>
            <TabsTrigger value="groups" className="h-10 gap-2 rounded-none border-b-2 border-transparent bg-transparent px-1 text-sm shadow-none data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:shadow-none">
              <Layers className="h-4 w-4" aria-hidden /> {t("srv.groups")}
            </TabsTrigger>
            <TabsTrigger value="rules" className="h-10 gap-2 rounded-none border-b-2 border-transparent bg-transparent px-1 text-sm shadow-none data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:shadow-none">
              <Settings className="h-4 w-4" aria-hidden /> {t("srv.rules_tab")}
            </TabsTrigger>
          </TabsList>

          {mainTab === "servers" ? (
            <div className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row sm:items-center lg:justify-end">
              <span aria-live="polite" className="hidden whitespace-nowrap px-1 text-xs text-muted-foreground 2xl:inline">
                {filtered.length === servers.length
                  ? formatServerCount(servers.length, lang)
                  : localize(lang, `Показано ${filtered.length} из ${servers.length}`, `${filtered.length} of ${servers.length} shown`)}
              </span>
              <div className="relative min-w-0 flex-1 sm:max-w-xs">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
                <Input
                  aria-label={localize(lang, "Поиск по серверам", "Search servers")}
                  placeholder={localize(lang, "Имя, адрес, ОС или группа…", "Name, address, OS, or group…")}
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  className="h-9 rounded-lg bg-card pl-9 pr-9 text-sm"
                />
                {search ? (
                  <button
                    type="button"
                    onClick={() => setSearch("")}
                    className="absolute right-1.5 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                    aria-label={localize(lang, "Очистить поиск", "Clear search")}
                  >
                    <X className="h-3.5 w-3.5" aria-hidden />
                  </button>
                ) : null}
              </div>
              <Select value={groupFilter} onValueChange={setGroupFilter}>
                <SelectTrigger className="h-9 w-full rounded-lg bg-card text-sm sm:w-48" aria-label={localize(lang, "Фильтр по группе", "Filter by group")}>
                  <ListFilter className="mr-2 h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all_groups__">{localize(lang, "Все группы", "All groups")}</SelectItem>
                  {groupOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label || t("srv.no_group")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}
        </div>

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
            onClearFilters={() => {
              setSearch("");
              setGroupFilter("__all_groups__");
            }}
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
          <ServerRulesTab
            controller={rulesController}
            manageableGroups={manageableGroups}
            t={t}
            tr={tr}
          />
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

      <SSHHostKeyEnrollmentDialog
        busy={testingConnection}
        onClose={closeHostKeyEnrollment}
        onConfirm={confirmHostKeyEnrollment}
        open={Boolean(hostKeyEnrollmentTarget)}
        t={t}
        target={hostKeyEnrollmentTarget}
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
