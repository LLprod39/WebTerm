import { useState } from "react";
import { AlertTriangle, Check, Clock3, GitBranch, History, Loader2, RotateCcw, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { PlaybookBundleExportButton } from "./PlaybookBundleExportButton";
import type { PlaybookWorkspaceVersioningController } from "./usePlaybookWorkspaceVersioning";

interface PlaybookRevisionPanelProps {
  lang: string;
  playbookId: number;
  workspace: PlaybookWorkspaceVersioningController;
}

export function PlaybookRevisionPanel({ lang, playbookId, workspace }: PlaybookRevisionPanelProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const [message, setMessage] = useState("");
  const status = {
    idle: tr("Черновик", "Draft"),
    loading: tr("Загрузка черновика…", "Loading draft…"),
    dirty: tr("Ожидает автосохранения", "Waiting to autosave"),
    saving: tr("Автосохранение…", "Autosaving…"),
    saved: tr("Черновик сохранён", "Draft saved"),
    conflict: tr("Конфликт версий", "Version conflict"),
    error: tr("Ошибка автосохранения", "Autosave failed"),
    readonly: tr("Только чтение", "Read only"),
  }[workspace.autosaveStatus];

  const createRevision = async () => {
    const created = await workspace.createRevision(message);
    if (created) setMessage("");
  };

  return (
    <section className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1" aria-labelledby="revision-panel-title">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-primary" />
            <h3 id="revision-panel-title" className="text-sm font-semibold text-foreground">
              {tr("Черновик и ревизии", "Draft and revisions")}
            </h3>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {tr(
              "Автосохранение обновляет рабочий черновик. Запуск использует только опубликованную ревизию.",
              "Autosave updates the working draft. Runs use only the published revision.",
            )}
          </p>
        </div>
        <div
          role="status"
          aria-live="polite"
          className={cn(
            "flex items-center gap-1.5 rounded-sm border px-2 py-1 text-xs",
            workspace.autosaveStatus === "conflict" || workspace.autosaveStatus === "error"
              ? "border-destructive/30 bg-destructive/5 text-destructive"
              : workspace.autosaveStatus === "dirty"
                ? "border-amber-500/30 bg-amber-500/5 text-amber-400"
                : "border-border bg-surface-0 text-muted-foreground",
          )}
        >
          {workspace.autosaveStatus === "saving" || workspace.autosaveStatus === "loading" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : workspace.autosaveStatus === "saved" ? (
            <Check className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <Clock3 className="h-3.5 w-3.5" />
          )}
          {status}
          {workspace.draft ? ` · v${workspace.draft.version}` : ""}
        </div>
      </div>

      {workspace.conflict ? (
        <div className="border-b border-destructive/20 bg-destructive/5 px-4 py-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-foreground">{tr("Черновик изменён в другом окне", "Draft changed elsewhere")}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {tr(
                  `Серверная версия v${workspace.conflict.serverDraft.version}. Выберите, какую версию продолжить.`,
                  `Server version v${workspace.conflict.serverDraft.version}. Choose which version to continue with.`,
                )}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={workspace.acceptServerDraft}>
                  {tr("Принять серверную", "Use server version")}
                </Button>
                <Button size="sm" onClick={() => void workspace.keepLocalDraft()}>
                  {tr("Сохранить мою поверх", "Keep my version")}
                </Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {workspace.autosaveError && !workspace.conflict ? (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-destructive/20 bg-destructive/5 px-4 py-2 text-xs text-destructive">
          <span>{workspace.autosaveError}</span>
          <Button
            size="sm"
            variant="outline"
            className="h-7"
            disabled={workspace.autosaveStatus === "saving"}
            onClick={() => void workspace.retryDraftSave()}
          >
            {tr("Повторить сохранение", "Retry save")}
          </Button>
        </div>
      ) : null}

      {workspace.capabilities.can_edit ? (
        <div className="grid gap-2 border-b border-border px-4 py-3 sm:grid-cols-[minmax(0,1fr)_auto]">
          <Input
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder={tr("Комментарий к ревизии", "Revision message")}
            aria-label={tr("Комментарий к новой ревизии", "New revision message")}
          />
          <Button
            variant="outline"
            className="gap-1.5"
            disabled={workspace.revisionBusy !== null || workspace.autosaveStatus === "conflict"}
            onClick={() => void createRevision()}
          >
            {workspace.revisionBusy === "create" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <GitBranch className="h-3.5 w-3.5" />}
            {tr("Создать ревизию", "Create revision")}
          </Button>
        </div>
      ) : null}

      <div className="divide-y divide-border">
        <div className="flex items-center justify-between px-4 py-2.5">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            <History className="h-3.5 w-3.5" />
            {tr("История", "History")}
          </div>
          {workspace.hasUnrevisionedChanges ? (
            <span className="text-xs text-amber-400">{tr("Есть изменения после последней ревизии", "Changes since last revision")}</span>
          ) : workspace.hasUnpublishedRevision ? (
            <span className="text-xs text-primary">{tr("Последняя ревизия не опубликована", "Latest revision is unpublished")}</span>
          ) : null}
        </div>
        {workspace.revisionsLoading ? (
          <div className="px-4 py-6 text-center text-sm text-muted-foreground">{tr("Загрузка истории…", "Loading history…")}</div>
        ) : workspace.revisions.length ? (
          workspace.revisions.map((revision) => {
            const published = revision.id === workspace.publishedRevisionId;
            return (
              <div key={revision.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left"
                  onClick={() => void workspace.openRevision(revision.id)}
                  aria-label={tr(`Открыть ревизию ${revision.revision_number}`, `Open revision ${revision.revision_number}`)}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-medium text-foreground">#{revision.revision_number}</span>
                    {published ? (
                      <span className="rounded-sm bg-emerald-500/10 px-1.5 py-0.5 text-2xs text-emerald-400">
                        {tr("Опубликована", "Published")}
                      </span>
                    ) : null}
                    <span className="truncate text-xs text-muted-foreground">{revision.message || revision.origin_type}</span>
                  </div>
                  <p className="mt-1 text-2xs text-muted-foreground">
                    {revision.author_username || tr("Система", "System")} · {new Date(revision.created_at).toLocaleString()}
                  </p>
                </button>
                {published ? (
                  <PlaybookBundleExportButton
                    playbookId={playbookId}
                    revisionId={revision.id}
                    revisionNumber={revision.revision_number}
                    canExport={workspace.capabilities.can_export}
                    lang={lang}
                  />
                ) : null}
                {workspace.capabilities.can_publish && !published ? (
                  <div className="flex gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 gap-1"
                      disabled={workspace.revisionBusy !== null}
                      onClick={() => void workspace.publishRevision(revision.id)}
                    >
                      <Upload className="h-3.5 w-3.5" />
                      {tr("Опубликовать", "Publish")}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-8 gap-1"
                      disabled={workspace.revisionBusy !== null}
                      onClick={() => void workspace.rollbackRevision(revision.id)}
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                      {tr("Rollback", "Rollback")}
                    </Button>
                  </div>
                ) : null}
              </div>
            );
          })
        ) : (
          <div className="px-4 py-6 text-center text-sm text-muted-foreground">{tr("Ревизий пока нет", "No revisions yet")}</div>
        )}
      </div>

      <Dialog open={Boolean(workspace.selectedRevision)} onOpenChange={(open) => !open && workspace.setSelectedRevision(null)}>
        <DialogContent className="max-w-3xl" closeLabel={tr("Закрыть", "Close")}>
          <DialogHeader>
            <DialogTitle>
              {tr("Ревизия", "Revision")} #{workspace.selectedRevision?.revision_number}
            </DialogTitle>
            <DialogDescription>{workspace.selectedRevision?.message || workspace.selectedRevision?.origin_type}</DialogDescription>
          </DialogHeader>
          <DialogBody className="max-h-[70vh] overflow-auto">
            <pre className="whitespace-pre-wrap rounded-sm border border-border bg-[#0d1117] p-4 font-mono text-xs text-foreground">
              {workspace.selectedRevision?.content_format === "ansible_yaml"
                ? workspace.selectedRevision.source_yaml
                : JSON.stringify(workspace.selectedRevision?.tasks || [], null, 2)}
            </pre>
          </DialogBody>
        </DialogContent>
      </Dialog>
    </section>
  );
}
