import { Loader2 } from "lucide-react";
import { ServerIcons } from "@/lib/app-icons";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import type { FrontendGroup, FrontendServer, ServerGroupRole } from "@/lib/api";

import { ServerAccessTab } from "./ServerAccessTab";
import { ServerContextTab } from "./ServerContextTab";
import { ServerExecuteTab } from "./ServerExecuteTab";
import { ServerKnowledgeTab } from "./ServerKnowledgeTab";
import { ServerSecurityTab } from "./ServerSecurityTab";
import type { AdvancedTab } from "./types";
import type { ServerCommandController } from "./useServerCommandController";
import type { ServerKnowledgeController } from "./useServerKnowledgeController";
import type { ServerRulesController } from "./useServerRulesController";
import type { ServerSecurityController } from "./useServerSecurityController";
import type { ServerSharesController } from "./useServerSharesController";

type ManageableGroup = FrontendGroup & { id: number; role: ServerGroupRole };
type Translate = (key: string) => string;
type TranslateWithVars = (key: string, vars?: Record<string, string | number>) => string;

interface ServerAdvancedDialogProps {
  advancedLoading: boolean;
  advancedOpen: boolean;
  advancedServer: FrontendServer | null;
  advancedTab: AdvancedTab;
  commandController: ServerCommandController;
  knowledgeController: ServerKnowledgeController;
  manageableGroups: ManageableGroup[];
  onOpenInheritedRules: () => void;
  openGroupRules: (groupId: number) => void;
  rulesController: ServerRulesController;
  securityController: ServerSecurityController;
  setAdvancedOpen: (open: boolean) => void;
  setAdvancedTab: (tab: AdvancedTab) => void;
  sharesController: ServerSharesController;
  t: Translate;
  tr: TranslateWithVars;
}

export function ServerAdvancedDialog({
  advancedLoading,
  advancedOpen,
  advancedServer,
  advancedTab,
  commandController,
  knowledgeController,
  manageableGroups,
  onOpenInheritedRules,
  openGroupRules,
  rulesController,
  securityController,
  setAdvancedOpen,
  setAdvancedTab,
  sharesController,
  t,
  tr,
}: ServerAdvancedDialogProps) {
  const { execCommand, execResult, onExecuteCommand, setExecCommand } = commandController;
  const {
    aiKnowledgeBulkDeleting,
    aiKnowledgeDeletingId,
    aiKnowledgeKindFilter,
    aiMemoryPurging,
    autoKnowledge,
    filteredAiKnowledge,
    filteredManualKnowledge,
    knowledgeBulkDeleting,
    knowledgeDeletingId,
    knowledgeSearch,
    manualKnowledge,
    normalizedKnowledgeSearch,
    onAiKnowledgeDelete,
    onDeleteFilteredAiKnowledge,
    onDeleteFilteredManualKnowledge,
    onKnowledgeDelete,
    onKnowledgeToggle,
    onPurgeAiMemory,
    openAiKnowledgeEditDialog,
    openKnowledgeCreateDialog,
    openKnowledgeEditDialog,
    setAiKnowledgeKindFilter,
    setKnowledgeSearch,
  } = knowledgeController;
  const {
    effectiveGroupForbidden,
    effectiveServerEnvironment,
    globalRequiredLines,
    groupMemberRole,
    groupMemberUser,
    groupRemoveUserId,
    onAddGroupMember,
    onRemoveGroupMember,
    onSaveServerContext,
    parsedServerNetworkConfig,
    serverRulesPreview,
    serverScopeDetails,
    serverScopeLoading,
    serverScopeNetworkJson,
    serverScopeRules,
    setGroupMemberRole,
    setGroupMemberUser,
    setGroupRemoveUserId,
    setServerScopeNetworkJson,
    setServerScopeRules,
  } = rulesController;
  const {
    hasMasterPassword,
    masterPassword,
    onClearMasterPassword,
    onRevealPassword,
    onSetMasterPassword,
    revealedPassword,
    setMasterPasswordText,
  } = securityController;
  const {
    createShare: onShareCreate,
    revokeShare: onShareRevoke,
    shareContext,
    shareExpiresAt,
    shares,
    shareUser,
    setShareContext,
    setShareExpiresAt,
    setShareUser,
  } = sharesController;
  const tabs: Array<{ key: AdvancedTab; icon: JSX.Element; label: string }> = [
    { key: "access", icon: <ServerIcons.access className="h-3.5 w-3.5" strokeWidth={1.5} />, label: t("srv.access") },
    { key: "knowledge", icon: <ServerIcons.knowledge className="h-3.5 w-3.5" strokeWidth={1.5} />, label: t("srv.knowledge") },
    { key: "context", icon: <ServerIcons.context className="h-3.5 w-3.5" strokeWidth={1.5} />, label: t("srv.server_rules_tab") },
    { key: "security", icon: <ServerIcons.security className="h-3.5 w-3.5" strokeWidth={1.5} />, label: t("srv.security") },
    { key: "execute", icon: <ServerIcons.execute className="h-3.5 w-3.5" strokeWidth={1.5} />, label: t("srv.execute") },
  ];

  return (
    <Dialog open={advancedOpen} onOpenChange={setAdvancedOpen}>
      <DialogContent className="flex h-[88vh] max-w-5xl flex-col p-0 sm:h-[85vh]">
        <div className="flex shrink-0 items-center gap-3 border-b border-border px-4 py-4 sm:px-6">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
            <ServerIcons.form className="h-4 w-4 text-primary" strokeWidth={1.5} />
          </div>
          <div className="min-w-0 flex-1">
            <DialogTitle className="text-sm font-semibold">{advancedServer?.name || t("srv.server")}</DialogTitle>
            <DialogDescription className="mt-0 text-xs font-mono">
              {advancedServer?.host}:{advancedServer?.port} · {advancedServer?.group_name}
            </DialogDescription>
          </div>
        </div>

        {advancedLoading ? (
          <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            {t("loading")}
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col md:flex-row">
            <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-border bg-secondary/20 p-2 md:block md:w-44 md:border-b-0 md:border-r md:py-2">
              {tabs.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setAdvancedTab(tab.key)}
                  className={`flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs font-medium transition-colors md:w-full md:rounded-none md:px-4 md:py-2.5 ${
                    advancedTab === tab.key
                      ? "bg-primary/10 text-primary md:border-r-2 md:border-primary"
                      : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                  }`}
                >
                  {tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="flex-1 overflow-y-auto p-4 sm:p-6">
              {advancedTab === "access" && (
                <ServerAccessTab
                  advancedServer={advancedServer}
                  groupMemberRole={groupMemberRole}
                  groupMemberUser={groupMemberUser}
                  groupRemoveUserId={groupRemoveUserId}
                  manageableGroups={manageableGroups}
                  onAddGroupMember={onAddGroupMember}
                  onRemoveGroupMember={onRemoveGroupMember}
                  onShareCreate={onShareCreate}
                  onShareRevoke={onShareRevoke}
                  openGroupRules={openGroupRules}
                  setGroupMemberRole={setGroupMemberRole}
                  setGroupMemberUser={setGroupMemberUser}
                  setGroupRemoveUserId={setGroupRemoveUserId}
                  setShareContext={setShareContext}
                  setShareExpiresAt={setShareExpiresAt}
                  setShareUser={setShareUser}
                  shareContext={shareContext}
                  shareExpiresAt={shareExpiresAt}
                  shares={shares}
                  shareUser={shareUser}
                  t={t}
                />
              )}

              {advancedTab === "knowledge" && (
                <ServerKnowledgeTab
                  aiKnowledgeBulkDeleting={aiKnowledgeBulkDeleting}
                  aiKnowledgeDeletingId={aiKnowledgeDeletingId}
                  aiKnowledgeKindFilter={aiKnowledgeKindFilter}
                  aiMemoryPurging={aiMemoryPurging}
                  autoKnowledge={autoKnowledge}
                  filteredAiKnowledge={filteredAiKnowledge}
                  filteredManualKnowledge={filteredManualKnowledge}
                  knowledgeBulkDeleting={knowledgeBulkDeleting}
                  knowledgeDeletingId={knowledgeDeletingId}
                  knowledgeSearch={knowledgeSearch}
                  manualKnowledge={manualKnowledge}
                  normalizedKnowledgeSearch={normalizedKnowledgeSearch}
                  onAiKnowledgeDelete={onAiKnowledgeDelete}
                  onDeleteFilteredAiKnowledge={onDeleteFilteredAiKnowledge}
                  onDeleteFilteredManualKnowledge={onDeleteFilteredManualKnowledge}
                  onKnowledgeDelete={onKnowledgeDelete}
                  onKnowledgeToggle={onKnowledgeToggle}
                  onPurgeAiMemory={onPurgeAiMemory}
                  openAiKnowledgeEditDialog={openAiKnowledgeEditDialog}
                  openKnowledgeCreateDialog={openKnowledgeCreateDialog}
                  openKnowledgeEditDialog={openKnowledgeEditDialog}
                  setAiKnowledgeKindFilter={setAiKnowledgeKindFilter}
                  setKnowledgeSearch={setKnowledgeSearch}
                  t={t}
                  tr={tr}
                />
              )}

              {advancedTab === "context" && (
                <ServerContextTab
                  advancedServer={advancedServer}
                  effectiveGroupForbidden={effectiveGroupForbidden}
                  effectiveServerEnvironment={effectiveServerEnvironment}
                  globalRequiredLines={globalRequiredLines}
                  onOpenInheritedRules={onOpenInheritedRules}
                  onSaveServerContext={onSaveServerContext}
                  parsedServerNetworkConfig={parsedServerNetworkConfig}
                  serverRulesPreview={serverRulesPreview}
                  serverScopeDetails={serverScopeDetails}
                  serverScopeLoading={serverScopeLoading}
                  serverScopeNetworkJson={serverScopeNetworkJson}
                  serverScopeRules={serverScopeRules}
                  setServerScopeNetworkJson={setServerScopeNetworkJson}
                  setServerScopeRules={setServerScopeRules}
                  t={t}
                />
              )}

              {advancedTab === "security" && (
                <ServerSecurityTab
                  hasMasterPassword={hasMasterPassword}
                  masterPassword={masterPassword}
                  onClearMasterPassword={onClearMasterPassword}
                  onRevealPassword={onRevealPassword}
                  onSetMasterPassword={onSetMasterPassword}
                  revealedPassword={revealedPassword}
                  setMasterPasswordText={setMasterPasswordText}
                  t={t}
                />
              )}

              {advancedTab === "execute" && (
                <ServerExecuteTab
                  execCommand={execCommand}
                  execResult={execResult}
                  onExecuteCommand={onExecuteCommand}
                  setExecCommand={setExecCommand}
                  t={t}
                />
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
