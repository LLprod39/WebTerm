import { DeleteDialog } from "@/components/system/ConfirmDialog";
import { GuidedBuilder } from "./GuidedBuilder";
import { PlaybookEditor } from "./PlaybookEditor";
import { RunResultsView } from "./RunResultsView";
import { RunWizard } from "./RunWizard";
import { detailToPlaybookEditor } from "./playbookEditorState";
import { PlaybooksCatalogPanel } from "./playbooks/PlaybooksCatalogPanel";
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
    saving,
    running,
    cancelling,
    activeRun,
    setActiveRun,
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
    groupsWithId,
  } = ctrl;

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
            setView({ mode: "edit", playbookId: pb.id });
            void queryClient.invalidateQueries({ queryKey: ["playbooks"] });
          }}
        />
      ) : null}

      {view.mode === "edit" ? (
        <PlaybookEditor
          lang={lang}
          state={editor}
          saving={saving}
          onChange={(patch) => setEditor((prev) => ({ ...prev, ...patch }))}
          onSave={() => void onSave()}
          onBack={() => setView({ mode: "catalog" })}
          onRun={() => {
            if (view.playbookId) setView({ mode: "run-wizard", playbookId: view.playbookId });
            else void ensureSavedThenWizard();
          }}
          title={view.playbookId ? tr("Редактирование", "Edit playbook") : tr("Новый playbook", "New playbook")}
          playbookId={view.playbookId}
          onCompatibilityApplied={(playbook) => setEditor(detailToPlaybookEditor(playbook))}
        />
      ) : null}

      {view.mode === "run-wizard" ? (
        <RunWizard
          lang={lang}
          playbookName={editor.name || "Playbook"}
          servers={servers}
          groups={groupsWithId}
          running={running}
          ansibleAvailable={ansibleAvailable}
          playbookId={view.playbookId}
          compatibility={editor.activeCompatibilityRevision?.report || editor.compatibility}
          onBack={() => setView({ mode: "edit", playbookId: view.playbookId })}
          onConfirm={(opts) => void onConfirmRun(opts)}
        />
      ) : null}

      {view.mode === "run-results" && activeRun ? (
        <RunResultsView
          lang={lang}
          run={activeRun}
          onBack={() => setView({ mode: "catalog" })}
          onCancel={() => void onCancelRun()}
          onRerunFailed={() => void onRerunFailed()}
          cancelling={cancelling}
        />
      ) : null}

      {view.mode === "run-results" && !activeRun ? (
        <div className="py-12 text-center text-sm text-muted-foreground">{tr("Загрузка run…", "Loading run…")}</div>
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
