import { DeleteDialog } from "@/components/system/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { GuidedBuilder } from "./GuidedBuilder";
import { PlaybookEditor } from "./PlaybookEditor";
import { RunResultsView } from "./RunResultsView";
import { RunWizard } from "./RunWizard";
import { detailToPlaybookEditor } from "./playbookEditorState";
import { PlaybooksCatalogPanel } from "./playbooks/PlaybooksCatalogPanel";
import { PlaybookWorkspacePanels } from "./playbooks/PlaybookWorkspacePanels";
import type { PlaybooksWorkspaceProps } from "./playbooks/types";
import { usePlaybooksWorkspace } from "./playbooks/usePlaybooksWorkspace";

export type { PlaybooksWorkspaceProps } from "./playbooks/types";

export function PlaybooksWorkspace(props: PlaybooksWorkspaceProps) {
  const ctrl = usePlaybooksWorkspace(props);
  const {
    lang,
    tr,
    queryClient,
    fileInputRef,
    view,
    setView,
    search,
    setSearch,
    categoryFilter,
    setCategoryFilter,
    editor,
    setEditor,
    openedPlaybook,
    setOpenedPlaybook,
    updateEditor,
    editorDirty,
    saving,
    saveError,
    running,
    cancelling,
    activeRun,
    setActiveRun,
    runLoadError,
    retryRunLoad,
    deleteTarget,
    setDeleteTarget,
    showHistory,
    setShowHistory,
    servers,
    playbooksQuery,
    playbooks,
    templates,
    recentRuns,
    ansible,
    ansibleAvailable,
    openNew,
    openEdit,
    leaveEditor,
    onSave,
    onDelete,
    onDuplicate,
    onImportFile,
    onInstallTemplate,
    startRunWizard,
    ensureSavedThenWizard,
    onConfirmRun,
    onCancelRun,
    onRerunFailed,
    onCompatibilityApplied,
    groupsWithId,
    workspace,
  } = ctrl;
  const routePlaybookId =
    view.mode === "edit" || view.mode === "run-wizard" ? view.playbookId : null;
  const playbookSurfaceLoading = Boolean(
    routePlaybookId && openedPlaybook?.id !== routePlaybookId,
  );

  return (
    <div className="space-y-3">
      <input
        ref={fileInputRef}
        type="file"
        accept=".yml,.yaml,.json"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void onImportFile(file);
          e.target.value = "";
        }}
      />

      {view.mode === "catalog" ? (
        <PlaybooksCatalogPanel
          lang={lang}
          tr={tr}
          playbooks={playbooks}
          templates={templates}
          recentRuns={recentRuns}
          playbooksLoading={playbooksQuery.isLoading}
          playbooksError={
            playbooksQuery.error instanceof Error
              ? playbooksQuery.error.message
              : playbooksQuery.error
                ? String(playbooksQuery.error)
                : ""
          }
          onRetryPlaybooks={() => void playbooksQuery.refetch()}
          search={search}
          setSearch={setSearch}
          categoryFilter={categoryFilter}
          setCategoryFilter={setCategoryFilter}
          showHistory={showHistory}
          setShowHistory={setShowHistory}
          ansible={ansible}
          ansibleAvailable={ansibleAvailable}
          onRefreshRuns={() => {
            void queryClient.invalidateQueries({ queryKey: ["playbook-runs"] });
          }}
          onImportClick={() => fileInputRef.current?.click()}
          onImportFile={(file) => void onImportFile(file)}
          onOpenNew={openNew}
          onOpenGuided={() => setView({ mode: "guided" })}
          onInstallTemplate={(tmpl) => void onInstallTemplate(tmpl)}
          onOpenEdit={(id) => void openEdit(id)}
          onStartRun={(id) => void startRunWizard(id)}
          onDuplicate={(id) => void onDuplicate(id)}
          onDelete={(pb) => setDeleteTarget(pb)}
          onOpenRun={(run) => {
            setActiveRun(run);
            setView({ mode: "run-results", runId: run.id });
          }}
        />
      ) : null}

      {view.mode === "guided" ? (
        <GuidedBuilder
          lang={lang}
          onBack={() => setView({ mode: "catalog" })}
          onCreated={(pb) => {
            setEditor(detailToPlaybookEditor(pb));
            setOpenedPlaybook(pb);
            setView({ mode: "edit", playbookId: pb.id });
            void queryClient.invalidateQueries({ queryKey: ["playbooks"] });
          }}
        />
      ) : null}

      {playbookSurfaceLoading ? (
        <div className="py-12 text-center text-sm text-muted-foreground" role="status">
          {tr("Загрузка playbook…", "Loading playbook…")}
        </div>
      ) : null}

      {view.mode === "edit" && !playbookSurfaceLoading ? (
        <PlaybookEditor
          lang={lang}
          state={editor}
          saving={saving}
          dirty={editorDirty}
          saveError={saveError}
          readOnly={Boolean(view.playbookId) && (!workspace.capabilityReady || !workspace.canEditContent)}
          metadataReadOnly={Boolean(view.playbookId) && !workspace.capabilities.is_owner}
          canRun={!view.playbookId || (workspace.capabilityReady && workspace.capabilities.can_run)}
          canValidate={!view.playbookId || workspace.capabilities.can_validate}
          canAdapt={!view.playbookId || workspace.capabilities.is_owner}
          publishedRevisionNumber={
            workspace.revisions.find((revision) => revision.id === workspace.publishedRevisionId)?.revision_number ?? null
          }
          hasUnpublishedRevision={workspace.hasUnpublishedRevision}
          onChange={updateEditor}
          onSave={() => void onSave()}
          onBack={leaveEditor}
          onRun={() => {
            if (view.playbookId) setView({ mode: "run-wizard", playbookId: view.playbookId });
            else void ensureSavedThenWizard();
          }}
          title={view.playbookId ? tr("Редактирование", "Edit playbook") : tr("Новый playbook", "New playbook")}
          playbookId={view.playbookId}
          onCompatibilityApplied={onCompatibilityApplied}
        />
      ) : null}

      {view.mode === "edit" && view.playbookId && !playbookSurfaceLoading ? (
        <PlaybookWorkspacePanels lang={lang} playbookId={view.playbookId} workspace={workspace} />
      ) : null}

      {view.mode === "run-wizard" && !playbookSurfaceLoading ? (
        <RunWizard
          lang={lang}
          playbookName={editor.name || "Playbook"}
          servers={servers}
          groups={groupsWithId}
          running={running}
          ansibleAvailable={ansibleAvailable}
          playbookId={view.playbookId}
          compatibility={editor.activeCompatibilityRevision?.report || editor.compatibility}
          revisions={workspace.revisions}
          publishedRevisionId={workspace.publishedRevisionId}
          revisionsLoading={workspace.revisionsLoading}
          bindingProfiles={workspace.bindings}
          capabilities={workspace.capabilities}
          workerReady={Boolean(ansible?.worker_ready)}
          onBack={() => setView({ mode: "edit", playbookId: view.playbookId })}
          onConfirm={(opts) => void onConfirmRun(opts)}
        />
      ) : null}

      {view.mode === "run-results" && activeRun?.id === view.runId ? (
        <div className="space-y-3">
          {runLoadError ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-sm border border-destructive/30 bg-destructive/5 px-3 py-2" role="alert">
              <p className="text-xs text-destructive">
                {tr("Обновление статуса остановлено:", "Status refresh stopped:")} {runLoadError}
              </p>
              <Button size="sm" variant="outline" onClick={retryRunLoad}>
                {tr("Повторить", "Retry")}
              </Button>
            </div>
          ) : null}
          <RunResultsView
            lang={lang}
            run={activeRun}
            onBack={() => setView({ mode: "catalog" })}
            onCancel={() => void onCancelRun()}
            onRerunFailed={() => void onRerunFailed()}
            cancelling={cancelling}
          />
        </div>
      ) : null}

      {view.mode === "run-results" && activeRun?.id !== view.runId && runLoadError ? (
        <div className="rounded-sm border border-destructive/30 bg-destructive/5 px-4 py-8 text-center" role="alert">
          <p className="text-sm font-medium text-destructive">
            {tr("Не удалось загрузить запуск", "Failed to load run")}
          </p>
          <p className="mx-auto mt-1 max-w-xl text-xs text-muted-foreground">{runLoadError}</p>
          <div className="mt-4 flex justify-center gap-2">
            <Button size="sm" variant="outline" onClick={() => setView({ mode: "catalog" })}>
              {tr("В каталог", "Back to catalog")}
            </Button>
            <Button size="sm" onClick={retryRunLoad}>
              {tr("Повторить", "Retry")}
            </Button>
          </div>
        </div>
      ) : null}

      {view.mode === "run-results" && activeRun?.id !== view.runId && !runLoadError ? (
        <div className="py-12 text-center text-sm text-muted-foreground" role="status">
          {tr("Загрузка run…", "Loading run…")}
        </div>
      ) : null}

      <DeleteDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title={tr("Удалить playbook?", "Delete playbook?")}
        description={
          deleteTarget
            ? tr(`«${deleteTarget.name}» будет удалён.`, `"${deleteTarget.name}" will be deleted.`)
            : ""
        }
        confirmLabel={tr("Удалить", "Delete")}
        cancelLabel={tr("Отмена", "Cancel")}
        onConfirm={() => void onDelete()}
      />
    </div>
  );
}

export default PlaybooksWorkspace;
