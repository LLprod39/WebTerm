import { useState } from "react";

import { analyzePlaybookCompatibility } from "@/api/playbooks";
import { DeleteDialog } from "@/components/system/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { notify } from "@/lib/notify";
import { GuidedBuilder } from "./GuidedBuilder";
import { PlaybookEditor } from "./PlaybookEditor";
import { RunResultsView } from "./RunResultsView";
import { RunWizard } from "./RunWizard";
import { detailToPlaybookEditor } from "./playbookEditorState";
import { PlaybooksCatalogPanel } from "./playbooks/PlaybooksCatalogPanel";
import { PlaybookWorkspacePanels } from "./playbooks/PlaybookWorkspacePanels";
import { PlaybookBundleImportDialog } from "./playbooks/PlaybookBundleImportDialog";
import type { PlaybooksWorkspaceProps } from "./playbooks/types";
import { usePlaybooksWorkspace } from "./playbooks/usePlaybooksWorkspace";

export type { PlaybooksWorkspaceProps } from "./playbooks/types";

export function PlaybooksWorkspace(props: PlaybooksWorkspaceProps) {
  const ctrl = usePlaybooksWorkspace(props);
  const {
    lang,
    tr,
    queryClient,
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
    retryContext,
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
    recentRuns,
    ansible,
    ansibleAvailable,
    openNew,
    openEdit,
    leaveEditor,
    onSave,
    onDelete,
    onDuplicate,
    startRunWizard,
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
  const [projectImportOpen, setProjectImportOpen] = useState(false);
  const [projectImportMode, setProjectImportMode] = useState<"yaml" | "archive" | "gitlab">("yaml");
  const [workspaceValidating, setWorkspaceValidating] = useState(false);

  const openImport = (mode: "yaml" | "archive" | "gitlab" = "yaml") => {
    setProjectImportMode(mode);
    setProjectImportOpen(true);
  };
  const validateWorkspace = async () => {
    if (view.mode !== "edit" || !view.playbookId) return;
    setWorkspaceValidating(true);
    try {
      const response = await analyzePlaybookCompatibility(view.playbookId, { source_yaml: editor.sourceYaml });
      updateEditor({ compatibility: response.report });
      await queryClient.invalidateQueries({ queryKey: ["playbooks"] });
      notify.success({ title: tr("Проверка завершена", "Validation complete") });
    } catch (caught) {
      notify.error({ title: tr("Проверка не удалась", "Validation failed"), description: String(caught) });
    } finally {
      setWorkspaceValidating(false);
    }
  };
  const openAdaptation = () => {
    const target = document.getElementById("playbook-ai-adaptation");
    if (!target) return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    target.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
    window.requestAnimationFrame(() => {
      target.querySelector<HTMLElement>("button:not([disabled]), textarea:not([disabled])")?.focus({ preventScroll: true });
    });
  };

  return (
    <div className="space-y-3">
      {view.mode === "catalog" ? (
        <PlaybooksCatalogPanel
          lang={lang}
          tr={tr}
          playbooks={playbooks}
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
          onOpenNew={openNew}
          onOpenImport={() => openImport("yaml")}
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
          {tr("Загрузка проекта…", "Loading project…")}
        </div>
      ) : null}

      {view.mode === "edit" && !playbookSurfaceLoading && !view.playbookId ? (
        <PlaybookEditor
          lang={lang}
          state={editor}
          saving={saving}
          dirty={editorDirty}
          saveError={saveError}
          readOnly={Boolean(view.playbookId) && (!workspace.capabilityReady || !workspace.canEditContent)}
          metadataReadOnly={Boolean(view.playbookId) && !workspace.capabilities.can_edit}
          canRun={!view.playbookId || (workspace.capabilityReady && workspace.capabilities.can_run)}
          canValidate={!view.playbookId || workspace.capabilities.can_validate}
          canAdapt={!view.playbookId || workspace.capabilities.can_edit}
          onChange={updateEditor}
          onSave={() => void onSave()}
          onBack={leaveEditor}
          onRun={() => {
            if (view.playbookId) setView({ mode: "run-wizard", playbookId: view.playbookId });
          }}
          playbookId={view.playbookId}
          onCompatibilityApplied={onCompatibilityApplied}
          onImportYaml={() => openImport("yaml")}
          onImportProject={() => openImport("archive")}
        />
      ) : null}

      {view.mode === "edit" && view.playbookId && !playbookSurfaceLoading ? (
        <PlaybookWorkspacePanels
          lang={lang}
          playbookId={view.playbookId}
          workspace={workspace}
          playbookName={editor.name || tr("Проект Ansible", "Ansible project")}
          canRun={workspace.capabilityReady && workspace.capabilities.can_run && !editorDirty && !saving}
          compatibilityReady={Boolean(editor.activeCompatibilityRevision?.status === "validated" || editor.compatibility?.ready)}
          validating={workspaceValidating}
          adaptationAvailable={Boolean(editor.sourceYaml.trim()) && workspace.capabilities.can_validate && workspace.capabilities.can_edit}
          onValidate={() => void validateWorkspace()}
          onOpenAdaptation={openAdaptation}
          gitLabSource={openedPlaybook?.source?.type === "gitlab"
            ? { type: "gitlab", host: openedPlaybook.source.host || "GitLab", project: openedPlaybook.source.project || "project", ref: openedPlaybook.source.ref, path: openedPlaybook.source.path }
            : null}
          servers={servers}
          groups={groupsWithId}
          hostSelectors={editor.activeCompatibilityRevision?.report?.host_selectors || editor.compatibility?.host_selectors || []}
          onBack={leaveEditor}
          onRun={() => setView({ mode: "run-wizard", playbookId: view.playbookId })}
        >
          <PlaybookEditor
            embedded
            lang={lang}
            state={editor}
            saving={saving}
            dirty={editorDirty}
            saveError={saveError}
            readOnly={!workspace.capabilityReady || !workspace.canEditContent}
            metadataReadOnly={!workspace.capabilities.can_edit}
            canRun={workspace.capabilityReady && workspace.capabilities.can_run}
            canValidate={workspace.capabilities.can_validate}
            canAdapt={workspace.capabilities.can_edit}
            onChange={updateEditor}
            onSave={() => void onSave()}
            onBack={leaveEditor}
            onRun={() => setView({ mode: "run-wizard", playbookId: view.playbookId })}
            playbookId={view.playbookId}
            onCompatibilityApplied={onCompatibilityApplied}
            onImportYaml={() => openImport("yaml")}
            onImportProject={() => openImport("archive")}
          />
        </PlaybookWorkspacePanels>
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
          bindingsLoading={workspace.bindingsLoading}
          capabilities={workspace.capabilities}
          retryContext={retryContext}
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
          {tr("Загрузка запуска…", "Loading run…")}
        </div>
      ) : null}

      <DeleteDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title={tr("Удалить проект?", "Delete project?")}
        description={
          deleteTarget
            ? tr(`«${deleteTarget.name}» будет удалён.`, `"${deleteTarget.name}" will be deleted.`)
            : ""
        }
        confirmLabel={tr("Удалить", "Delete")}
        cancelLabel={tr("Отмена", "Cancel")}
        onConfirm={() => void onDelete()}
      />

      <PlaybookBundleImportDialog
        open={projectImportOpen}
        onOpenChange={setProjectImportOpen}
        lang={lang}
        initialMode={projectImportMode}
        onOpenPlaybook={(playbookId) => void openEdit(playbookId)}
      />
    </div>
  );
}

export default PlaybooksWorkspace;
