import type { Dispatch, SetStateAction } from "react";
import { ChevronDown, ChevronUp, Copy, Loader2, Play, Plus, Save, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { PipelineRiskSummary } from "@/components/pipeline/pipelineRiskSummary";
import { getRunDialogCopy } from "@/components/studio/PipelineEditorCopy";
import { useToast } from "@/hooks/use-toast";
import type { PipelineNode, PipelineTrigger } from "@/lib/api";

import { RunRiskSummaryPanel } from "./PanelPrimitives";
import { localize } from "./presentation";
import { formatStudioDateTime, getNodeDisplayLabel, toAbsoluteWebhookUrl } from "./pipelineGraphUtils";

export type PipelineRunDialogMode = "manual" | "webhook" | "schedule" | "monitoring";

type ManualTriggerOption = {
  node_id: string;
  label: string;
};

type PipelineRunDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: PipelineRunDialogMode;
  lang: "en" | "ru";
  manualTriggerOptions: ManualTriggerOption[];
  runEntryNodeId: string;
  onRunEntryNodeIdChange: (value: string) => void;
  runTriggerError: string | null;
  onRunTriggerErrorChange: (value: string | null) => void;
  runRiskSummary: PipelineRiskSummary;
  runtimeContextFields: string[];
  onApplyRuntimeContextFields: () => void;
  runTaskText: string;
  onRunTaskTextChange: (value: string) => void;
  runAdvancedOpen: boolean;
  onRunAdvancedOpenChange: Dispatch<SetStateAction<boolean>>;
  runRequester: string;
  onRunRequesterChange: (value: string) => void;
  runTicketId: string;
  onRunTicketIdChange: (value: string) => void;
  runContextText: string;
  onRunContextTextChange: (value: string) => void;
  runContextError: string | null;
  onRunContextErrorChange: (value: string | null) => void;
  activeWebhookTriggers: PipelineTrigger[];
  activeScheduleTriggers: PipelineTrigger[];
  activeMonitoringTriggers: PipelineTrigger[];
  scheduleTriggerNodes: PipelineNode[];
  monitoringTriggerNodes: PipelineNode[];
  isRunPending: boolean;
  isValidatePending: boolean;
  isSavePending: boolean;
  saveDisabled: boolean;
  onValidateRun: () => void;
  onRunSubmit: () => void;
  onSaveTrigger: () => void;
};

export function PipelineRunDialog({
  open,
  onOpenChange,
  mode,
  lang,
  manualTriggerOptions,
  runEntryNodeId,
  onRunEntryNodeIdChange,
  runTriggerError,
  onRunTriggerErrorChange,
  runRiskSummary,
  runtimeContextFields,
  onApplyRuntimeContextFields,
  runTaskText,
  onRunTaskTextChange,
  runAdvancedOpen,
  onRunAdvancedOpenChange,
  runRequester,
  onRunRequesterChange,
  runTicketId,
  onRunTicketIdChange,
  runContextText,
  onRunContextTextChange,
  runContextError,
  onRunContextErrorChange,
  activeWebhookTriggers,
  activeScheduleTriggers,
  activeMonitoringTriggers,
  scheduleTriggerNodes,
  monitoringTriggerNodes,
  isRunPending,
  isValidatePending,
  isSavePending,
  saveDisabled,
  onValidateRun,
  onRunSubmit,
  onSaveTrigger,
}: PipelineRunDialogProps) {
  const { toast } = useToast();
  const copy = getRunDialogCopy(mode, lang);
  const actionDisabled = isRunPending || isValidatePending || isSavePending;

  const handleCopyWebhookUrl = async (webhookUrl: string) => {
    try {
      await navigator.clipboard.writeText(toAbsoluteWebhookUrl(webhookUrl));
      toast({ description: localize(lang, "Webhook URL скопирован.", "Webhook URL copied.") });
    } catch (error) {
      const message = error instanceof Error
        ? error.message
        : localize(lang, "Не удалось скопировать webhook URL.", "Failed to copy webhook URL.");
      toast({ variant: "destructive", description: message });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] max-w-2xl overflow-hidden">
        <DialogHeader>
          <DialogTitle>{copy.title}</DialogTitle>
          <DialogDescription>{copy.description}</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          {mode === "manual" ? (
            <>
              <div className="space-y-2">
                <Label htmlFor="run-entry-trigger">{localize(lang, "Ручной триггер", "Manual trigger")}</Label>
                <Select
                  value={runEntryNodeId}
                  onValueChange={(value) => {
                    onRunEntryNodeIdChange(value);
                    if (runTriggerError) onRunTriggerErrorChange(null);
                  }}
                  disabled={manualTriggerOptions.length <= 1}
                >
                  <SelectTrigger id="run-entry-trigger">
                    <SelectValue
                      placeholder={
                        manualTriggerOptions.length === 0
                          ? localize(lang, "Нет активных ручных триггеров", "No active manual trigger nodes")
                          : manualTriggerOptions.length === 1
                            ? manualTriggerOptions[0].label
                            : localize(lang, "Выберите триггер", "Select a trigger")
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {manualTriggerOptions.map((trigger) => (
                      <SelectItem key={trigger.node_id} value={trigger.node_id}>
                        {trigger.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {manualTriggerOptions.length <= 1
                    ? localize(lang, "Если ручной триггер один, он будет выбран автоматически.", "When there is only one manual trigger, it is selected automatically.")
                    : localize(lang, "Этот триггер запустит только свою ветку графа.", "This trigger starts only its own branch of the graph.")}
                </p>
                {runTriggerError ? <p className="text-xs text-red-400">{runTriggerError}</p> : null}
              </div>

              <RunRiskSummaryPanel summary={runRiskSummary} lang={lang} />

              <div className="space-y-2">
                <Label htmlFor="run-task">{localize(lang, "Задача", "Task")}</Label>
                <Textarea
                  id="run-task"
                  value={runTaskText}
                  onChange={(event) => onRunTaskTextChange(event.target.value)}
                  placeholder={localize(lang, "Например: проверить staging, применить обновления и сообщить о блокерах", "Example: check staging, apply updates, and report blockers")}
                  rows={4}
                />
              </div>

              {runtimeContextFields.length ? (
                <div className="space-y-3 rounded-lg border border-primary/20 bg-primary/5 p-3">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="text-xs font-medium text-foreground">
                        {localize(lang, "Поля для этого шаблона", "Fields for this template")}
                      </p>
                      <p className="mt-1 text-xs leading-4 text-muted-foreground">
                        {localize(
                          lang,
                          "Эти переменные найдены в шагах pipeline. Добавьте их в JSON context и заполните реальные значения перед запуском.",
                          "These variables were found in pipeline steps. Add them to JSON context and fill real values before running.",
                        )}
                      </p>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="h-8 shrink-0 gap-1.5"
                      onClick={onApplyRuntimeContextFields}
                    >
                      <Plus className="h-3.5 w-3.5" />
                      {localize(lang, "В JSON", "Add to JSON")}
                    </Button>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {runtimeContextFields.map((field) => (
                      <button
                        key={field}
                        type="button"
                        className="rounded-md border border-border bg-background px-2 py-1 font-mono text-xs text-muted-foreground transition-colors hover:border-primary/30 hover:text-foreground"
                        onClick={onApplyRuntimeContextFields}
                      >
                        {`{${field}}`}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              <div className="rounded-md border border-border">
                <button
                  type="button"
                  className="flex w-full items-center justify-between px-3 py-2 text-left"
                  onClick={() => onRunAdvancedOpenChange((advancedOpen) => !advancedOpen)}
                >
                  <div>
                    <p className="text-xs font-medium">{localize(lang, "Расширенный контекст", "Advanced context")}</p>
                    <p className="text-xs text-muted-foreground">{localize(lang, "Необязательные метаданные инициатора и дополнительные JSON-поля.", "Optional requester metadata and extra JSON fields.")}</p>
                  </div>
                  {runAdvancedOpen ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
                </button>
                {runAdvancedOpen ? (
                  <div className="space-y-4 border-t border-border px-3 py-3">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="space-y-2">
                        <Label htmlFor="run-requester">{localize(lang, "Инициатор", "Requester")}</Label>
                        <Input
                          id="run-requester"
                          value={runRequester}
                          onChange={(event) => onRunRequesterChange(event.target.value)}
                          placeholder={localize(lang, "Service Desk, CI job, оператор", "Service Desk, CI job, operator")}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="run-ticket-id">{localize(lang, "Тикет или reference ID", "Ticket or reference ID")}</Label>
                        <Input
                          id="run-ticket-id"
                          value={runTicketId}
                          onChange={(event) => onRunTicketIdChange(event.target.value)}
                          placeholder="INC-1428"
                        />
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="run-context">{localize(lang, "Контекст запуска (JSON-объект)", "Run context (JSON object)")}</Label>
                      <Textarea
                        id="run-context"
                        value={runContextText}
                        onChange={(event) => {
                          onRunContextTextChange(event.target.value);
                          if (runContextError) onRunContextErrorChange(null);
                        }}
                        placeholder='{"env":"staging","priority":"high"}'
                        rows={8}
                        className="font-mono text-xs"
                      />
                      <p className="text-xs text-muted-foreground">
                        {localize(lang, "Эти поля объединяются с задачей перед стартом запуска.", "These fields are merged with the task text before the run starts.")}
                      </p>
                      {runContextError ? <p className="text-xs text-red-400">{runContextError}</p> : null}
                    </div>
                  </div>
                ) : null}
              </div>
            </>
          ) : mode === "webhook" ? (
            <div className="space-y-4">
              {activeWebhookTriggers.length ? (
                <div className="rounded-xl border border-sky-500/25 bg-sky-500/10 px-3 py-2 text-xs text-sky-200">
                  {localize(
                    lang,
                    "Триггер уже активирован и ждёт входящий POST-запрос. Новый запуск появится только когда webhook реально придёт.",
                    "This trigger is already armed and waiting for an incoming POST request. A new run will appear only when the webhook actually arrives.",
                  )}
                </div>
              ) : (
                <div className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                  {localize(
                    lang,
                    "Сначала сохраните граф, чтобы активировать webhook-триггер и получить URL.",
                    "Save the graph first to arm the webhook trigger and generate its URL.",
                  )}
                </div>
              )}
              {activeWebhookTriggers.length ? (
                activeWebhookTriggers.map((trigger) => (
                  <div key={trigger.id} className="space-y-2 rounded-xl border border-border bg-background/60 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-foreground">{trigger.name || localize(lang, "Webhook-триггер", "Webhook trigger")}</div>
                        <div className="text-xs text-muted-foreground">{localize(lang, "Нода", "Node")} `{trigger.node_id}`</div>
                      </div>
                      <Button size="sm" variant="outline" className="h-9" onClick={() => void handleCopyWebhookUrl(trigger.webhook_url)}>
                        <Copy className="mr-1.5 h-3.5 w-3.5" />
                        {localize(lang, "Скопировать URL", "Copy URL")}
                      </Button>
                    </div>
                    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs text-muted-foreground break-all">
                      {toAbsoluteWebhookUrl(trigger.webhook_url)}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {trigger.last_triggered_at
                        ? localize(lang, `Последний запуск: ${formatStudioDateTime(trigger.last_triggered_at)}`, `Last trigger: ${formatStudioDateTime(trigger.last_triggered_at)}`)
                        : localize(lang, "Ещё не вызывался.", "Has not been triggered yet.")}
                    </p>
                  </div>
                ))
              ) : (
                <div className="rounded-xl border border-dashed border-border px-3 py-3 text-xs text-muted-foreground">
                  {localize(
                    lang,
                    "Сначала сохраните pipeline, чтобы сгенерировать webhook URL для этой ноды-триггера.",
                    "Save the pipeline first to generate a webhook URL for this trigger node.",
                  )}
                </div>
              )}
            </div>
          ) : mode === "schedule" ? (
            <div className="space-y-4">
              <div className="rounded-xl border border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                {localize(
                  lang,
                  "Триггер расписания запускается планировщиком. Ручной запуск для него не нужен.",
                  "Schedule triggers are started by the scheduler. They do not need a manual Run.",
                )}
              </div>
              {(activeScheduleTriggers.length
                ? activeScheduleTriggers.map((trigger) => ({
                    id: String(trigger.id),
                    label: trigger.name || trigger.node_id,
                    cron: trigger.cron_expression || localize(lang, "не задан", "not set"),
                  }))
                : scheduleTriggerNodes.map((node) => ({
                    id: node.id,
                    label: getNodeDisplayLabel(node, lang),
                    cron:
                      typeof node.data?.cron_expression === "string" && node.data.cron_expression.trim()
                        ? node.data.cron_expression
                        : localize(lang, "не задан", "not set"),
                  }))).map((trigger) => (
                <div key={trigger.id} className="rounded-xl border border-border bg-background/60 p-3">
                  <div className="text-sm font-medium text-foreground">{trigger.label}</div>
                  <div className="mt-1 text-xs text-muted-foreground">{localize(lang, "Cron", "Cron")}: {trigger.cron}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                {localize(
                  lang,
                  "Триггер мониторинга активируется после сохранения и ждёт алерт мониторинга сервера. Запуск появится только при реальной проблеме.",
                  "The monitoring trigger is armed after save and waits for a server monitoring alert. A run appears only when a real issue is detected.",
                )}
              </div>
              {(activeMonitoringTriggers.length
                ? activeMonitoringTriggers.map((trigger) => ({
                    id: String(trigger.id),
                    label: trigger.name || trigger.node_id,
                    filters: trigger.monitoring_filters || {},
                    lastTriggeredAt: trigger.last_triggered_at,
                  }))
                : monitoringTriggerNodes.map((node) => ({
                    id: node.id,
                    label: getNodeDisplayLabel(node, lang),
                    filters: node.data?.monitoring_filters || {},
                    lastTriggeredAt: null,
                  }))).map((trigger) => (
                <div key={trigger.id} className="rounded-xl border border-border bg-background/60 p-3">
                  <div className="text-sm font-medium text-foreground">{trigger.label}</div>
                  <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                    <div>{localize(lang, "Серверы", "Servers")}: {Array.isArray((trigger.filters as Record<string, unknown>).server_ids) && ((trigger.filters as Record<string, unknown>).server_ids as unknown[]).length ? (((trigger.filters as Record<string, unknown>).server_ids as unknown[]).join(", ")) : localize(lang, "все", "any")}</div>
                    <div>{localize(lang, "Критичность", "Severity")}: {Array.isArray((trigger.filters as Record<string, unknown>).severities) && ((trigger.filters as Record<string, unknown>).severities as unknown[]).length ? (((trigger.filters as Record<string, unknown>).severities as unknown[]).join(", ")) : localize(lang, "любая", "any")}</div>
                    <div>{localize(lang, "Тип алерта", "Alert type")}: {Array.isArray((trigger.filters as Record<string, unknown>).alert_types) && ((trigger.filters as Record<string, unknown>).alert_types as unknown[]).length ? (((trigger.filters as Record<string, unknown>).alert_types as unknown[]).join(", ")) : localize(lang, "любой", "any")}</div>
                    <div>{localize(lang, "Контейнеры", "Containers")}: {Array.isArray((trigger.filters as Record<string, unknown>).container_names) && ((trigger.filters as Record<string, unknown>).container_names as unknown[]).length ? (((trigger.filters as Record<string, unknown>).container_names as unknown[]).join(", ")) : localize(lang, "все", "any")}</div>
                    {trigger.lastTriggeredAt ? <div>{localize(lang, `Последний запуск: ${formatStudioDateTime(trigger.lastTriggeredAt)}`, `Last trigger: ${formatStudioDateTime(trigger.lastTriggeredAt)}`)}</div> : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" className="h-10" onClick={() => onOpenChange(false)}>
            {mode === "manual" ? localize(lang, "Отмена", "Cancel") : localize(lang, "Закрыть", "Close")}
          </Button>
          {mode === "manual" ? (
            <>
              <Button
                variant="outline"
                className="h-10"
                onClick={onValidateRun}
                disabled={actionDisabled}
              >
                {isValidatePending || isSavePending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                {localize(lang, "Проверить", "Validate")}
              </Button>
              <Button
                className="h-10"
                onClick={onRunSubmit}
                disabled={actionDisabled}
              >
                {isRunPending || isSavePending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                {localize(lang, "Запустить", "Run")}
              </Button>
            </>
          ) : (
            <Button className="h-10" onClick={onSaveTrigger} disabled={saveDisabled}>
              {isSavePending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {localize(lang, "Сохранить trigger", "Save Trigger")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
