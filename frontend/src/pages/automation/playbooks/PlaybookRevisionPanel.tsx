import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Check, Clock3, GitBranch, History, Loader2, RotateCcw, ShieldCheck, Upload } from "lucide-react";

import { getPlaybookRevision, type PlaybookRevision } from "@/api/playbooks";
import { ConfirmDialog } from "@/components/system/ConfirmDialog";
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
import { PlaybookGitLabRefreshButton } from "./PlaybookGitLabRefreshButton";
import type { PlaybookWorkspaceVersioningController } from "./usePlaybookWorkspaceVersioning";
import type { GitLabProjectSource } from "@/api/playbooks";

interface PlaybookRevisionPanelProps {
  lang: string;
  playbookId: number;
  workspace: PlaybookWorkspaceVersioningController;
  gitLabSource?: GitLabProjectSource | null;
  compatibilityReady: boolean;
  validating?: boolean;
  onValidate: () => void;
}

export function PlaybookRevisionPanel({ lang, playbookId, workspace, gitLabSource, compatibilityReady, validating = false, onValidate }: PlaybookRevisionPanelProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const [message, setMessage] = useState("");
  const [publishTarget, setPublishTarget] = useState<PlaybookRevision | null>(null);
  const [rollbackTarget, setRollbackTarget] = useState<PlaybookRevision | null>(null);
  const selectedRevision = workspace.selectedRevision;
  const baselineId = selectedRevision?.parent_id || (workspace.publishedRevisionId !== selectedRevision?.id ? workspace.publishedRevisionId : null);
  const baselineQuery = useQuery({
    queryKey: ["playbook-workspace", "revision", playbookId, baselineId],
    queryFn: () => getPlaybookRevision(playbookId, baselineId as number),
    enabled: Boolean(selectedRevision && baselineId),
    retry: false,
  });
  const selectedSource = revisionSource(selectedRevision);
  const baselineSource = revisionSource(baselineQuery.data?.revision || null);
  const diffLines = useMemo(() => buildLineDiff(baselineSource, selectedSource), [baselineSource, selectedSource]);
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
              {tr("Черновик и версии", "Draft and versions")}
            </h3>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {tr(
              "Изменения сохраняются в черновик. Для запуска используется только опубликованная версия.",
              "Changes are saved to the draft. Runs use only the published version.",
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {gitLabSource && workspace.capabilities.can_edit ? (
            <PlaybookGitLabRefreshButton lang={lang} playbookId={playbookId} source={gitLabSource} />
          ) : null}
          <div
            role="status"
            aria-live="polite"
            className={cn(
              "flex items-center gap-1.5 rounded-sm border px-2 py-1 text-xs",
              workspace.autosaveStatus === "conflict" || workspace.autosaveStatus === "error"
                ? "border-destructive/30 bg-destructive/5 text-destructive"
                : workspace.autosaveStatus === "dirty"
                  ? "border-warning/30 bg-warning/5 text-warning"
                  : "border-border bg-surface-0 text-muted-foreground",
            )}
          >
            {workspace.autosaveStatus === "saving" || workspace.autosaveStatus === "loading" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : workspace.autosaveStatus === "saved" ? (
              <Check className="h-3.5 w-3.5 text-success" />
            ) : (
              <Clock3 className="h-3.5 w-3.5" />
            )}
            {status}
            {workspace.draft ? ` · v${workspace.draft.version}` : ""}
          </div>
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

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-surface-0/35 px-4 py-3">
        <div className="flex items-center gap-2 text-xs">
          <ShieldCheck className={cn("h-4 w-4", compatibilityReady ? "text-success" : "text-warning")} />
          <span className={compatibilityReady ? "text-success" : "text-muted-foreground"}>
            {compatibilityReady ? tr("Текущий черновик проверен", "Current draft is validated") : tr("Текущий черновик нужно проверить", "Current draft needs validation")}
          </span>
        </div>
        {workspace.capabilities.can_validate ? <Button size="sm" variant="outline" className="h-8 gap-1.5" disabled={validating} onClick={onValidate}>{validating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}{tr("Проверить черновик", "Validate draft")}</Button> : null}
      </div>

      {workspace.capabilities.can_edit ? (
        <div className="grid gap-2 border-b border-border px-4 py-3 sm:grid-cols-[minmax(0,1fr)_auto]">
          <Input
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder={tr("Комментарий к версии", "Version note")}
            aria-label={tr("Комментарий к новой версии", "New version note")}
          />
          <Button
            variant="outline"
            className="gap-1.5"
            disabled={workspace.revisionBusy !== null || workspace.autosaveStatus === "conflict"}
            onClick={() => void createRevision()}
          >
            {workspace.revisionBusy === "create" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <GitBranch className="h-3.5 w-3.5" />}
            {tr("Создать версию", "Create version")}
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
            <span className="text-xs text-warning">{tr("Есть изменения после последней версии", "Changes since the last version")}</span>
          ) : workspace.hasUnpublishedRevision ? (
            <span className="text-xs text-primary">{tr("Последняя версия не опубликована", "Latest version is unpublished")}</span>
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
                      <span className="rounded-sm bg-success/10 px-1.5 py-0.5 text-2xs text-success">
                        {tr("Опубликована", "Published")}
                      </span>
                    ) : null}
                    {revision.compatibility?.ready ? <span className="rounded-sm bg-success/8 px-1.5 py-0.5 text-2xs text-success">{tr("Проверена", "Validated")}</span> : <span className="rounded-sm bg-warning/8 px-1.5 py-0.5 text-2xs text-warning">{tr("Не проверена", "Not validated")}</span>}
                    <span className="truncate text-xs text-muted-foreground">{revision.message || revision.origin_type}</span>
                  </div>
                  <p className="mt-1 text-2xs text-muted-foreground">
                    {revision.author_username || tr("Система", "System")} · {new Date(revision.created_at).toLocaleString()}
                  </p>
                </button>
                <PlaybookBundleExportButton
                  playbookId={playbookId}
                  revisionId={revision.id}
                  revisionNumber={revision.revision_number}
                  canExport={workspace.capabilities.can_export}
                  lang={lang}
                />
                {workspace.capabilities.can_publish && !published ? (
                  <div className="flex gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 gap-1"
                      disabled={workspace.revisionBusy !== null}
                      onClick={() => setPublishTarget(revision)}
                    >
                      <Upload className="h-3.5 w-3.5" />
                      {tr("Опубликовать", "Publish")}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-8 gap-1"
                      disabled={workspace.revisionBusy !== null}
                      onClick={() => setRollbackTarget(revision)}
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

      <Dialog open={Boolean(selectedRevision)} onOpenChange={(open) => !open && workspace.setSelectedRevision(null)}>
        <DialogContent className="max-w-3xl" closeLabel={tr("Закрыть", "Close")}>
          <DialogHeader>
            <DialogTitle>
              {tr("Ревизия", "Revision")} #{selectedRevision?.revision_number}
            </DialogTitle>
            <DialogDescription>{selectedRevision?.message || selectedRevision?.origin_type}</DialogDescription>
          </DialogHeader>
          <DialogBody className="max-h-[70vh] space-y-3 overflow-auto">
            <div className="grid gap-2 text-xs sm:grid-cols-3">
              <VersionFact label={tr("Хэш содержимого", "Content hash")} value={selectedRevision?.content_hash.slice(0, 12) || "—"} />
              <VersionFact label={tr("Базовая версия", "Compared with")} value={baselineQuery.data?.revision ? `#${baselineQuery.data.revision.revision_number}` : tr("Недоступна", "Unavailable")} />
              <VersionFact label={tr("Проверка", "Validation")} value={selectedRevision?.compatibility?.ready ? tr("Пройдена", "Passed") : tr("Не подтверждена", "Not confirmed")} />
            </div>
            <details open className="rounded-sm border border-border bg-terminal-bg">
              <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-foreground">{tr("Изменения относительно родительской/опубликованной версии", "Changes from parent/published revision")}</summary>
              {baselineQuery.isPending && baselineId ? <p className="border-t border-border p-4 text-xs text-muted-foreground">{tr("Загрузка сравнения…", "Loading comparison…")}</p> : baselineSource ? <RevisionDiff lines={diffLines} /> : <p className="border-t border-border p-4 text-xs text-muted-foreground">{tr("Исходник базовой версии недоступен; хэши показаны выше.", "The baseline source is unavailable; hashes are shown above.")}</p>}
            </details>
            <details className="rounded-sm border border-border bg-terminal-bg">
              <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-foreground">{tr("Полный исходник версии", "Full revision source")}</summary>
              <pre className="max-h-96 overflow-auto whitespace-pre-wrap border-t border-border p-4 font-mono text-xs text-foreground">{selectedSource}</pre>
            </details>
          </DialogBody>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(publishTarget)}
        onOpenChange={(open) => !open && setPublishTarget(null)}
        title={tr("Опубликовать эту версию?", "Publish this revision?")}
        description={publishTarget ? tr(`Версия #${publishTarget.revision_number} (${publishTarget.content_hash.slice(0, 12)}) станет основной для новых запусков. Профили сохранятся, история не изменится.`, `Revision #${publishTarget.revision_number} (${publishTarget.content_hash.slice(0, 12)}) becomes the default for new runs. Profiles remain intact and history is unchanged.`) : ""}
        confirmLabel={tr("Опубликовать", "Publish")}
        cancelLabel={tr("Отмена", "Cancel")}
        onConfirm={async () => { if (publishTarget) await workspace.publishRevision(publishTarget.id); setPublishTarget(null); }}
      />
      <ConfirmDialog
        open={Boolean(rollbackTarget)}
        onOpenChange={(open) => !open && setRollbackTarget(null)}
        title={tr("Создать версию из выбранной?", "Create a revision from this one?")}
        description={rollbackTarget ? tr(`Будет создана новая ревизия на основе #${rollbackTarget.revision_number}. Существующая история и опубликованная версия не переписываются.`, `A new revision will be created from #${rollbackTarget.revision_number}. Existing history and the published revision are never rewritten.`) : ""}
        confirmLabel={tr("Создать новую ревизию", "Create new revision")}
        cancelLabel={tr("Отмена", "Cancel")}
        tone="destructive"
        onConfirm={async () => { if (rollbackTarget) await workspace.rollbackRevision(rollbackTarget.id); setRollbackTarget(null); }}
      />
    </section>
  );
}

function revisionSource(revision: PlaybookRevision | null): string {
  if (!revision) return "";
  return revision.content_format === "ansible_yaml" ? revision.source_yaml || "" : JSON.stringify(revision.tasks || [], null, 2);
}

function VersionFact({ label, value }: { label: string; value: string }) {
  return <div className="rounded-sm border border-border bg-surface-0 p-2"><p className="text-2xs uppercase tracking-wider text-muted-foreground">{label}</p><p className="mt-1 truncate font-mono text-foreground">{value}</p></div>;
}

function RevisionDiff({ lines }: { lines: Array<{ kind: "same" | "add" | "remove"; text: string }> }) {
  return <div className="max-h-96 overflow-auto border-t border-border font-mono text-xs">{lines.map((line, index) => <div key={`${line.kind}-${index}`} className={cn("grid grid-cols-[1.5rem_minmax(0,1fr)] gap-2 px-3 py-0.5", line.kind === "add" && "bg-success/10 text-success", line.kind === "remove" && "bg-destructive/10 text-destructive", line.kind === "same" && "text-muted-foreground")}><span>{line.kind === "add" ? "+" : line.kind === "remove" ? "−" : " "}</span><span className="whitespace-pre-wrap break-words">{line.text || " "}</span></div>)}</div>;
}

function buildLineDiff(before: string, after: string): Array<{ kind: "same" | "add" | "remove"; text: string }> {
  const left = before.split("\n");
  const right = after.split("\n");
  let prefix = 0;
  while (prefix < left.length && prefix < right.length && left[prefix] === right[prefix]) prefix += 1;
  let suffix = 0;
  while (suffix < left.length - prefix && suffix < right.length - prefix && left[left.length - 1 - suffix] === right[right.length - 1 - suffix]) suffix += 1;
  return [
    ...left.slice(0, prefix).map((text) => ({ kind: "same" as const, text })),
    ...left.slice(prefix, left.length - suffix).map((text) => ({ kind: "remove" as const, text })),
    ...right.slice(prefix, right.length - suffix).map((text) => ({ kind: "add" as const, text })),
    ...left.slice(left.length - suffix).map((text) => ({ kind: "same" as const, text })),
  ];
}
