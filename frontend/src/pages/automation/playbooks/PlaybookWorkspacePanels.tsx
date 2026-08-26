import { useState, type ReactNode } from "react";
import { ArrowLeft, Check, Clock3, Loader2, Play, Save, ShieldCheck, Sparkles, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/system/ConfirmDialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { PlaybookBindingsPanel } from "./PlaybookBindingsPanel";
import { PlaybookGitLabRefreshButton } from "./PlaybookGitLabRefreshButton";
import { PlaybookRevisionPanel } from "./PlaybookRevisionPanel";
import { PlaybookSharingPanel } from "./PlaybookSharingPanel";
import type { PlaybookWorkspaceVersioningController } from "./usePlaybookWorkspaceVersioning";
import type { GitLabProjectSource } from "@/api/playbooks";
import type { FrontendGroup, FrontendServer } from "@/lib/api";

interface PlaybookWorkspacePanelsProps {
  lang: string;
  playbookId: number;
  workspace: PlaybookWorkspaceVersioningController;
  playbookName: string;
  canRun: boolean;
  compatibilityReady: boolean;
  validating?: boolean;
  adaptationAvailable?: boolean;
  onValidate: () => void;
  onOpenAdaptation?: () => void;
  onBack: () => void;
  onRun: () => void;
  gitLabSource?: GitLabProjectSource | null;
  servers: FrontendServer[];
  groups: Array<FrontendGroup & { id: number }>;
  hostSelectors: string[];
  children: ReactNode;
}

export function PlaybookWorkspacePanels({
  lang,
  playbookId,
  workspace,
  playbookName,
  canRun,
  compatibilityReady,
  validating = false,
  adaptationAvailable = false,
  onValidate,
  onOpenAdaptation,
  onBack,
  onRun,
  gitLabSource,
  servers,
  groups,
  hostSelectors,
  children,
}: PlaybookWorkspacePanelsProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const [publishConfirmOpen, setPublishConfirmOpen] = useState(false);
  const status = {
    idle: tr("Черновик", "Draft"),
    loading: tr("Загрузка…", "Loading…"),
    dirty: tr("Есть изменения", "Unsaved changes"),
    saving: tr("Сохраняем…", "Saving…"),
    saved: tr("Сохранено", "Saved"),
    conflict: tr("Конфликт", "Conflict"),
    error: tr("Ошибка сохранения", "Save failed"),
    readonly: tr("Только чтение", "Read only"),
  }[workspace.autosaveStatus];
  const statusDanger = workspace.autosaveStatus === "conflict" || workspace.autosaveStatus === "error";
  const saveNeeded = ["dirty", "saving", "error", "conflict"].includes(workspace.autosaveStatus);
  const publishNeeded = workspace.hasUnrevisionedChanges || workspace.hasUnpublishedRevision;
  const draftBaseRevision = workspace.revisions.find((revision) => revision.id === workspace.draft?.base_revision_id);
  const publishHash = (workspace.hasUnrevisionedChanges ? workspace.draft?.content_hash : draftBaseRevision?.content_hash || workspace.draft?.content_hash) || "";
  const publishTarget = workspace.hasUnrevisionedChanges
    ? tr("новая версия из текущего черновика", "a new revision from the current draft")
    : draftBaseRevision
      ? tr(`версия #${draftBaseRevision.revision_number}`, `revision #${draftBaseRevision.revision_number}`)
      : tr("текущая неопубликованная версия", "the current unpublished revision");
  const publishCurrent = async () => {
    let revisionId = workspace.draft?.base_revision_id && workspace.draft.base_revision_id !== workspace.publishedRevisionId
      ? workspace.draft.base_revision_id
      : null;
    if (workspace.hasUnrevisionedChanges) {
      const created = await workspace.createRevision(tr("Публикация из рабочей области", "Published from workspace"));
      revisionId = created?.id || null;
    }
    if (revisionId) await workspace.publishRevision(revisionId);
  };
  const primaryAction = saveNeeded && workspace.capabilities.can_edit
    ? {
        label: workspace.autosaveStatus === "error" ? tr("Повторить сохранение", "Retry save") : tr("Сохранить", "Save"),
        icon: Save,
        busy: workspace.autosaveStatus === "saving",
        disabled: workspace.autosaveStatus === "saving" || workspace.autosaveStatus === "conflict",
        run: () => void workspace.saveDraftNow(),
      }
    : !compatibilityReady && workspace.capabilities.can_validate
      ? { label: tr("Проверить", "Validate"), icon: ShieldCheck, busy: validating, disabled: validating, run: onValidate }
      : publishNeeded && workspace.capabilities.can_publish
        ? { label: tr("Опубликовать", "Publish"), icon: Upload, busy: workspace.revisionBusy === "create" || workspace.revisionBusy === "publish", disabled: workspace.revisionBusy !== null, run: () => setPublishConfirmOpen(true) }
        : workspace.capabilities.can_run
          ? { label: tr("Запустить", "Run"), icon: Play, busy: false, disabled: !canRun, run: onRun }
          : null;
  const PrimaryIcon = primaryAction?.icon || Play;

  return (
    <section className="mx-auto w-full max-w-[1180px] space-y-4">
      <Tabs defaultValue="content">
        <div className="sticky top-[45px] z-20 overflow-hidden rounded-lg border border-border bg-background/95 shadow-elev-2 backdrop-blur supports-[backdrop-filter]:bg-background/85">
          <div className="flex flex-wrap items-center gap-3 px-3 py-3">
            <Button size="icon" variant="ghost" className="h-8 w-8 shrink-0" onClick={onBack} aria-label={tr("Назад к Ansible", "Back to Ansible")}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div className="min-w-0 flex-1">
              <h1 className="truncate font-display text-lg font-semibold text-foreground">{playbookName}</h1>
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5" role="status" aria-live="polite">
                <LifecycleChip label={tr("Оригинал", "Original")} active />
                <LifecycleChip label={tr("Черновик", "Draft")} active={Boolean(workspace.draft)} detail={workspace.draft ? `v${workspace.draft.version}` : undefined} warning={saveNeeded} />
                <LifecycleChip label={tr("Проверено", "Validated")} active={compatibilityReady} />
                <LifecycleChip label={tr("Опубликовано", "Published")} active={Boolean(workspace.publishedRevisionId)} detail={workspace.publishedRevisionId ? `#${workspace.revisions.find((revision) => revision.id === workspace.publishedRevisionId)?.revision_number || ""}` : undefined} />
                <span className={cn("ml-1 inline-flex items-center gap-1 text-2xs", statusDanger ? "text-destructive" : "text-muted-foreground")}>
                  {workspace.autosaveStatus === "saving" || workspace.autosaveStatus === "loading" ? <Loader2 className="h-3 w-3 animate-spin" /> : workspace.autosaveStatus === "saved" ? <Check className="h-3 w-3 text-success" /> : <Clock3 className="h-3 w-3" />}
                  {status}
                </span>
              </div>
            </div>
            <div className="ml-auto flex w-full shrink-0 items-center justify-end gap-2 sm:w-auto">
              {onOpenAdaptation ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 gap-1.5"
                  disabled={!adaptationAvailable}
                  onClick={onOpenAdaptation}
                  aria-controls="playbook-ai-adaptation"
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  {tr("ИИ-адаптация", "AI adaptation")}
                </Button>
              ) : null}
              {primaryAction ? (
                <Button size="sm" className="h-8 gap-1.5" disabled={primaryAction.disabled} onClick={primaryAction.run}>
                  {primaryAction.busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PrimaryIcon className="h-3.5 w-3.5" />}
                  {primaryAction.label}
                </Button>
              ) : null}
            </div>
          </div>
          <TabsList className="h-auto w-full justify-start overflow-x-auto rounded-none border-t border-border/70 bg-transparent px-2 py-1" aria-label={tr("Разделы проекта", "Project sections")}>
            <TabsTrigger value="content">{tr("Содержимое", "Content")}</TabsTrigger>
            <TabsTrigger value="run-settings">{tr("Настройки запуска", "Run settings")}</TabsTrigger>
            <TabsTrigger value="versions">{tr("Версии", "Versions")}</TabsTrigger>
            <TabsTrigger value="access">{tr("Доступ", "Access")}</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="content" className="space-y-2 pt-2">
          {gitLabSource && workspace.capabilities.can_edit ? (
            <div className="flex items-center justify-between gap-3 rounded-sm border border-border bg-surface-0 px-3 py-2">
              <p className="text-xs text-muted-foreground">
                {tr("Источник подключён к GitLab. Обновление сначала покажет снимок и изменения.", "This source is connected to GitLab. Refresh first shows the snapshot and changes.")}
              </p>
              <PlaybookGitLabRefreshButton lang={lang} playbookId={playbookId} source={gitLabSource} />
            </div>
          ) : null}
          {children}
        </TabsContent>
        <TabsContent value="run-settings" className="pt-2"><PlaybookBindingsPanel lang={lang} workspace={workspace} servers={servers} groups={groups} hostSelectors={hostSelectors} /></TabsContent>
        <TabsContent value="versions" className="pt-2"><PlaybookRevisionPanel lang={lang} playbookId={playbookId} workspace={workspace} gitLabSource={gitLabSource} compatibilityReady={compatibilityReady} validating={validating} onValidate={onValidate} /></TabsContent>
        <TabsContent value="access" className="pt-2"><PlaybookSharingPanel lang={lang} playbookId={playbookId} workspace={workspace} /></TabsContent>
      </Tabs>
      <ConfirmDialog
        open={publishConfirmOpen}
        onOpenChange={setPublishConfirmOpen}
        title={tr("Опубликовать текущую рабочую копию?", "Publish the current working copy?")}
        description={tr(
          `Будет опубликована ${publishTarget}${publishHash ? ` · hash ${publishHash.slice(0, 12)}` : ""}. Она станет основной для новых запусков. Профили запуска сохранятся; история не переписывается.`,
          `This publishes ${publishTarget}${publishHash ? ` · hash ${publishHash.slice(0, 12)}` : ""}. It becomes the default for new runs. Run profiles remain intact and history is not rewritten.`,
        )}
        confirmLabel={tr("Опубликовать", "Publish")}
        cancelLabel={tr("Отмена", "Cancel")}
        onConfirm={async () => { await publishCurrent(); setPublishConfirmOpen(false); }}
      />
    </section>
  );
}

function LifecycleChip({ label, active, detail, warning = false }: { label: string; active: boolean; detail?: string; warning?: boolean }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-2xs",
      warning
        ? "border-warning/30 bg-warning/8 text-warning"
        : active
          ? "border-success/25 bg-success/8 text-foreground"
          : "border-border bg-surface-0 text-muted-foreground/65",
    )}>
      {active && !warning ? <Check className="h-2.5 w-2.5 text-success" /> : null}{label}{detail ? ` ${detail}` : ""}
    </span>
  );
}
