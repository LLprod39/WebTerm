import { ArrowLeft, Bell, CheckCircle2, Clock, Info, Link2, Loader2, MoreHorizontal, Play, Plus, Save, ShieldCheck, Wand2, XCircle, Zap } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ProviderBindingSelect } from "@/components/settings/ProviderBindingSelect";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { PipelineActivityState } from "@/components/pipeline/pipelineActivity";
import type { PipelineLastRun, PipelineRun, ProviderBinding } from "@/lib/api";

import { getPipelineActivityCopy, localize } from "./presentation";

export function PipelineEditorToolbar({
  assistantOpen,
  hasHydratedPipeline,
  hasLocalChanges,
  lang,
  pipelineId,
  pipelineName,
  providerBinding,
  resolvedLastRun,
  runDisabled,
  runPending,
  saveDisabled,
  savePending,
  onBack,
  onOpenAssistant,
  onOpenLastRun,
  onOpenPalette,
  onOpenRunDialog,
  onPipelineNameChange,
  onProviderBindingChange,
  onSave,
  onValidateGraph,
}: {
  assistantOpen: boolean;
  hasHydratedPipeline: boolean;
  hasLocalChanges: boolean;
  lang: "en" | "ru";
  pipelineId: number | null;
  pipelineName: string;
  providerBinding: ProviderBinding | null;
  resolvedLastRun: PipelineLastRun | null;
  runDisabled: boolean;
  runPending: boolean;
  saveDisabled: boolean;
  savePending: boolean;
  onBack: () => void;
  onOpenAssistant: () => void;
  onOpenLastRun: (runId: number) => void;
  onOpenPalette: () => void;
  onOpenRunDialog: () => void;
  onPipelineNameChange: (value: string) => void;
  onProviderBindingChange: (value: ProviderBinding | null) => void;
  onSave: () => void;
  onValidateGraph: () => void;
}) {
  return (
    <div className="z-10 flex flex-col gap-3 border-b border-border bg-card px-3 py-3 lg:flex-row lg:items-center lg:px-4">
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <Button size="icon" variant="ghost" className="h-9 w-9 shrink-0" onClick={onBack} aria-label={localize(lang, "Вернуться в Studio", "Back to Studio")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <Input
            value={pipelineName}
            onChange={(e) => onPipelineNameChange(e.target.value)}
            className="h-8 min-w-0 border-0 bg-transparent px-0 text-base font-semibold shadow-none focus-visible:ring-0 sm:max-w-xl"
            placeholder={localize(lang, "Название pipeline…", "Pipeline name…")}
          />
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <Badge
              variant={hasLocalChanges ? "outline" : "secondary"}
              className={hasLocalChanges ? "border-amber-500/30 bg-amber-500/10 text-amber-100" : "text-xs"}
            >
              {hasLocalChanges ? localize(lang, "Есть изменения", "Unsaved changes") : localize(lang, "Сохранено", "Saved")}
            </Badge>
            {resolvedLastRun ? (
              <button
                type="button"
                onClick={() => onOpenLastRun(resolvedLastRun.id)}
                className="inline-flex min-h-7 items-center gap-1.5 rounded-md border border-border/70 bg-background/35 px-2 py-1 text-xs text-muted-foreground transition-colors hover:border-border hover:bg-background/50 hover:text-foreground"
              >
                {resolvedLastRun.status === "running" ? <Loader2 className="h-3 w-3 animate-spin" /> : <Clock className="h-3 w-3" />}
                {localize(lang, "Последний запуск", "Last run")} #{resolvedLastRun.id}: {resolvedLastRun.status}
              </button>
            ) : null}
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 lg:ml-auto lg:justify-end">
        <ProviderBindingSelect
          value={providerBinding}
          onChange={onProviderBindingChange}
          mode="unattended"
          lang={lang}
          className="h-9 min-w-48 max-w-64"
        />
        <Button
          size="sm"
          variant="outline"
          onClick={onValidateGraph}
          disabled={runDisabled}
          className="h-9 gap-1.5"
        >
          <ShieldCheck className="h-3.5 w-3.5" />
          {localize(lang, "Проверить", "Validate")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onOpenPalette}
          className="h-9 gap-1.5 lg:hidden"
        >
          <Plus className="h-3 w-3" />
          {localize(lang, "Ноды", "Nodes")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onSave}
          disabled={savePending || (Boolean(pipelineId) && !hasHydratedPipeline) || saveDisabled}
          className="h-9 gap-1.5"
        >
          {savePending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
          {localize(lang, "Сохранить", "Save")}
        </Button>
        <Button
          size="sm"
          onClick={onOpenRunDialog}
          disabled={runDisabled}
          className="h-9 gap-1.5"
        >
          {runPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
          {localize(lang, "Запустить", "Run")}
        </Button>
        <Button
          size="sm"
          variant={assistantOpen ? "secondary" : "outline"}
          onClick={onOpenAssistant}
          className="h-9 gap-1.5"
        >
          <Wand2 className="h-3.5 w-3.5" />
          {localize(lang, "AI", "AI")}
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="icon" variant="ghost" className="h-9 w-9 rounded-md text-muted-foreground" aria-label={localize(lang, "Ещё действия", "More actions")}>
              <MoreHorizontal className="h-3.5 w-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            {resolvedLastRun && (
              <DropdownMenuItem onClick={() => onOpenLastRun(resolvedLastRun.id)}>
                <CheckCircle2 className="mr-2 h-3.5 w-3.5" />
                {localize(lang, "Открыть последний запуск", "Open last run")}
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}

export function PipelineActivityBar({
  activityState,
  graphRunId,
  graphRunLive,
  hasHydratedPipeline,
  highlightedNode,
  highlightedNodeLabel,
  lang,
  pipelineId,
}: {
  activityState: PipelineActivityState;
  graphRunId: number | null;
  graphRunLive: PipelineRun | null;
  hasHydratedPipeline: boolean;
  highlightedNode: { id: string } | null;
  highlightedNodeLabel: string;
  lang: "en" | "ru";
  pipelineId: number | null;
}) {
  const activityCopy = getPipelineActivityCopy(activityState, lang);
  const activityToneClass =
    activityState.tone === "primary"
      ? "border-primary/25 bg-primary/10 text-primary"
      : activityState.tone === "success"
        ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-300"
        : activityState.tone === "info"
          ? "border-sky-500/25 bg-sky-500/10 text-sky-300"
          : "border-amber-500/25 bg-amber-500/10 text-amber-300";
  const ActivityIcon =
    activityState.icon === "running"
      ? Loader2
      : activityState.icon === "pending"
        ? Clock
        : activityState.icon === "manual"
          ? Play
          : activityState.icon === "webhook"
            ? Link2
            : activityState.icon === "schedule"
              ? Clock
              : activityState.icon === "monitoring"
                ? Bell
                : activityState.icon === "warning"
                  ? XCircle
                  : Zap;

  return (
    <div className="flex flex-col items-start gap-2 border-b border-border/80 bg-card/60 px-4 py-2.5 text-xs sm:flex-row sm:items-center lg:gap-3">
      <div className={`flex items-center gap-2 rounded-full border px-2.5 py-1.5 ${activityToneClass}`}>
        <ActivityIcon
          className={`h-3.5 w-3.5 ${activityState.icon === "running" ? "animate-spin" : ""}`}
        />
        <span className="font-medium">{activityCopy.label}</span>
      </div>
      <p className="min-w-0 flex-1 leading-5 text-muted-foreground/90 sm:truncate">{activityCopy.detail}</p>
      {graphRunId && highlightedNode ? (
        <div className="inline-flex items-center gap-2 rounded-full border border-sky-500/25 bg-sky-500/10 px-2.5 py-1 text-sky-200">
          {isLiveRunStatus(graphRunLive?.status) ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Info className="h-3.5 w-3.5" />}
          <span>
            {localize(lang, "Текущий шаг", "Current step")}: {highlightedNodeLabel}
          </span>
        </div>
      ) : null}
      {pipelineId && !hasHydratedPipeline ? (
        <div className="ml-auto inline-flex items-center gap-2 rounded-full border border-amber-500/25 bg-amber-500/10 px-2.5 py-1 text-amber-200">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          <span>{localize(lang, "Обновляем свежую версию графа…", "Refreshing the latest graph…")}</span>
        </div>
      ) : null}
    </div>
  );
}

function isLiveRunStatus(status?: string | null) {
  return status === "pending" || status === "running" || status === "waiting";
}
