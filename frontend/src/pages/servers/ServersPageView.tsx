import type { ChangeEvent, Dispatch, SetStateAction } from "react";
import {
  type FrontendGroup,
  type FrontendServer,
  type MonitoringStatusItem,
  type ServerGroupRole,
} from "@/lib/api";
import { localize } from "@/lib/i18n";
import {
  Plus,
  Search,
  Server,
  Settings,
  Layers,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { DeleteDialog } from "@/components/system/ConfirmDialog";
import { ContentPanel } from "@/components/system/ContentPanel";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageShell, SoftHeader, StatStrip, StatStripItem } from "@/components/ui/page-shell";
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
  sharedCount: number;
  onlineCount: number;
  offlineCount: number;
  search: string;
  setSearch: (value: string) => void;
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
    t, tr, lang, mainTab, setMainTab, servers, manageableGroups, groupCount, sharedCount,
    onlineCount, offlineCount, search, setSearch, collapsed, filtered, grouped, toggleGroup,
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

  return (
    <PageShell width="7xl" className="space-y-4">
      <SoftHeader
        compact
        title={t("srv.title")}
        count={servers.length > 0 ? servers.length : undefined}
        subtitle={localize(lang, "Серверы, группы и правила", "Servers, groups, and rules")}
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
