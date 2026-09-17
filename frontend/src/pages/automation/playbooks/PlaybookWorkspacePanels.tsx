import { useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Check,
  Clock3,
  History,
  Loader2,
  MoreHorizontal,
  Play,
  Save,
  ShieldCheck,
  Sparkles,
  Wrench,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { notify } from "@/lib/notify";
import { PlaybookBindingsPanel } from "./PlaybookBindingsPanel";
import { PlaybookGitLabRefreshButton } from "./PlaybookGitLabRefreshButton";
import { PlaybookRevisionPanel } from "./PlaybookRevisionPanel";
import { PlaybookSharingPanel } from "./PlaybookSharingPanel";
import { ensurePlaybookPublishedForRun } from "./ensurePlaybookPublishedForRun";
import { revisionsKey } from "./playbookWorkspaceVersioningState";
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

type WorkspaceTab = "content" | "run-settings" | "versions" | "access";

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
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<WorkspaceTab>("content");
  const [runPreparing, setRunPreparing] = useState(false);
  const status = {
    idle: tr("Сохранено", "Saved"),
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

  const readinessLabel = compatibilityReady
    ? tr("Готов", "Ready")
    : tr("Нужна правка", "Needs fix");

  const startRunSilently = async () => {
    if (!canRun || runPreparing) return;
    setRunPreparing(true);
    try {
      if (saveNeeded && workspace.capabilities.can_edit) {
        const draft = await workspace.saveDraftNow();
        if (!draft) throw new Error(tr("Не удалось сохранить", "Save failed"));
      }
      if (workspace.capabilities.can_publish || workspace.capabilities.can_edit) {
        await ensurePlaybookPublishedForRun(playbookId);
        await queryClient.invalidateQueries({ queryKey: revisionsKey(playbookId) });
        await queryClient.refetchQueries({ queryKey: revisionsKey(playbookId) });
        await queryClient.invalidateQueries({ queryKey: ["playbooks"] });
      }
      onRun();
    } catch (error) {
      notify.error({
        title: tr("Не удалось подготовить запуск", "Could not prepare the run"),
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setRunPreparing(false);
    }
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
      ? {
          label: onOpenAdaptation && adaptationAvailable
            ? tr("Исправить с ИИ", "Fix with AI")
            : tr("Проверить", "Validate"),
          icon: onOpenAdaptation && adaptationAvailable ? Sparkles : Wrench,
          busy: validating,
          disabled: validating,
          run: onOpenAdaptation && adaptationAvailable ? onOpenAdaptation : onValidate,
        }
      : workspace.capabilities.can_run
        ? {
            label: tr("Запустить", "Run"),
            icon: Play,
            busy: runPreparing || workspace.revisionBusy === "create" || workspace.revisionBusy === "publish",
            disabled: !canRun || runPreparing || workspace.revisionBusy !== null,
            run: () => void startRunSilently(),
          }
        : null;
  const PrimaryIcon = primaryAction?.icon || Play;

  return (
    <section className="mx-auto w-full max-w-[1180px] space-y-4">
      <Tabs value={tab} onValueChange={(value) => setTab(value as WorkspaceTab)}>
        <div className="sticky top-[45px] z-20 overflow-hidden rounded-lg border border-border bg-background/95 shadow-elev-2 ">
          <div className="flex flex-wrap items-center gap-3 px-3 py-3">
            <Button size="icon" variant="ghost" className="h-8 w-8 shrink-0" onClick={onBack} aria-label={tr("Назад к Ansible", "Back to Ansible")}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div className="min-w-0 flex-1">
              <h1 className="truncate font-display text-lg font-semibold text-foreground">{playbookName}</h1>
              <div className="mt-1.5 flex flex-wrap items-center gap-2" role="status" aria-live="polite">
                <span
                  className={cn(
                    "inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-2xs",
                    compatibilityReady
                      ? "border-success/25 bg-success/8 text-foreground"
                      : "border-warning/30 bg-warning/8 text-warning",
                  )}
                >
                  {compatibilityReady ? <Check className="h-2.5 w-2.5 text-success" /> : <ShieldCheck className="h-2.5 w-2.5" />}
                  {readinessLabel}
                </span>
                <span className={cn("inline-flex items-center gap-1 text-2xs", statusDanger ? "text-destructive" : "text-muted-foreground")}>
                  {workspace.autosaveStatus === "saving" || workspace.autosaveStatus === "loading" ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : workspace.autosaveStatus === "saved" || workspace.autosaveStatus === "idle" ? (
                    <Check className="h-3 w-3 text-success" />
                  ) : (
                    <Clock3 className="h-3 w-3" />
                  )}
                  {status}
                </span>
              </div>
            </div>
            <div className="ml-auto flex w-full shrink-0 items-center justify-end gap-2 sm:w-auto">
              {onOpenAdaptation && compatibilityReady ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 gap-1.5"
                  disabled={!adaptationAvailable}
                  onClick={onOpenAdaptation}
                  aria-controls="playbook-ai-adaptation"
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  {tr("ИИ", "AI")}
                </Button>
              ) : null}
              {primaryAction ? (
                <Button size="sm" className="h-8 gap-1.5" disabled={primaryAction.disabled} onClick={primaryAction.run}>
                  {primaryAction.busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PrimaryIcon className="h-3.5 w-3.5" />}
                  {primaryAction.label}
                </Button>
              ) : null}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button size="icon" variant="ghost" className="h-8 w-8" aria-label={tr("Ещё", "More")}>
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuItem onSelect={() => setTab("versions")}>
                    <History className="h-4 w-4" />
                    {tr("История", "History")}
                  </DropdownMenuItem>
                  {!compatibilityReady && workspace.capabilities.can_validate ? (
                    <DropdownMenuItem onSelect={onValidate} disabled={validating}>
                      <ShieldCheck className="h-4 w-4" />
                      {tr("Проверить YAML", "Validate YAML")}
                    </DropdownMenuItem>
                  ) : null}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
          <TabsList className="h-auto w-full justify-start overflow-x-auto rounded-none border-t border-border/70 bg-transparent px-2 py-1" aria-label={tr("Разделы проекта", "Project sections")}>
            <TabsTrigger value="content">{tr("Скрипт", "Script")}</TabsTrigger>
            <TabsTrigger value="run-settings">{tr("Параметры", "Settings")}</TabsTrigger>
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
        <TabsContent value="run-settings" className="pt-2">
          <PlaybookBindingsPanel lang={lang} workspace={workspace} servers={servers} groups={groups} hostSelectors={hostSelectors} />
        </TabsContent>
        <TabsContent value="versions" className="pt-2">
          <PlaybookRevisionPanel
            lang={lang}
            playbookId={playbookId}
            workspace={workspace}
            gitLabSource={gitLabSource}
            compatibilityReady={compatibilityReady}
            validating={validating}
            onValidate={onValidate}
          />
        </TabsContent>
        <TabsContent value="access" className="pt-2">
          <PlaybookSharingPanel lang={lang} playbookId={playbookId} workspace={workspace} />
        </TabsContent>
      </Tabs>
    </section>
  );
}
