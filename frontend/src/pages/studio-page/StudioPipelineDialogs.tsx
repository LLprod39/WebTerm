import { Copy, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { localize } from "@/lib/i18n";
import { toAbsoluteWebhookUrl, type TriggerInfoTarget } from "@/components/studio/StudioPipelineTriggers";
import type { PipelineDetail, PipelineListItem } from "@/lib/api";

type ManualTriggerOption = {
  nodeId: string;
  label: string;
};

type ManualTriggerDialogProps = {
  lang: string;
  open: boolean;
  target: PipelineDetail | null;
  entryNodeId: string;
  error: string;
  options: ManualTriggerOption[];
  running: boolean;
  onClose: () => void;
  onEntryNodeChange: (nodeId: string) => void;
  onOpenEditor: (pipelineId: number) => void;
  onRun: (pipelineId: number, entryNodeId: string) => void;
  onError: (message: string) => void;
};

export function ManualTriggerDialog({
  lang,
  open,
  target,
  entryNodeId,
  error,
  options,
  running,
  onClose,
  onEntryNodeChange,
  onOpenEditor,
  onRun,
  onError,
}: ManualTriggerDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{localize(lang, "Выберите ручной вход", "Choose manual trigger")}</DialogTitle>
          <DialogDescription>
            {target
              ? localize(lang, `В пайплайне "${target.name}" несколько ручных входов. Выберите ветку для запуска.`, `Pipeline "${target.name}" has multiple manual entry nodes. Choose which branch to launch.`)
              : ""}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <label className="space-y-2 text-sm">
            <span className="text-muted-foreground">{localize(lang, "Ручной вход", "Manual trigger")}</span>
            <select
              value={entryNodeId}
              onChange={(event) => onEntryNodeChange(event.target.value)}
              className="flex h-10 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground"
            >
              {options.map((option) => (
                <option key={option.nodeId} value={option.nodeId}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          {error ? <p className="text-xs text-destructive">{error}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" className="h-10" onClick={() => target && onOpenEditor(target.id)}>
            {localize(lang, "Открыть редактор", "Open editor")}
          </Button>
          <Button variant="outline" className="h-10" onClick={onClose}>
            {localize(lang, "Отмена", "Cancel")}
          </Button>
          <Button
            className="h-10"
            onClick={() => {
              if (!target) return;
              if (!entryNodeId) {
                onError(localize(lang, "Выберите ручной вход для запуска.", "Choose a manual trigger to start the run."));
                return;
              }
              onRun(target.id, entryNodeId);
            }}
            disabled={running}
          >
            {running && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            {localize(lang, "Запустить", "Run")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type TriggerInfoDialogProps = {
  lang: string;
  target: TriggerInfoTarget | null;
  onClose: () => void;
  onOpenEditor: (pipelineId: number) => void;
};

export function TriggerInfoDialog({ lang, target, onClose, onOpenEditor }: TriggerInfoDialogProps) {
  const { toast } = useToast();

  async function handleCopyWebhookUrl(webhookUrl: string) {
    try {
      await navigator.clipboard.writeText(toAbsoluteWebhookUrl(webhookUrl));
      toast({ description: localize(lang, "Webhook URL скопирован.", "Webhook URL copied.") });
    } catch (error) {
      const message = error instanceof Error ? error.message : localize(lang, "Не удалось скопировать webhook URL.", "Failed to copy webhook URL.");
      toast({ variant: "destructive", description: message });
    }
  }

  return (
    <Dialog open={Boolean(target)} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {target?.webhookTriggers.length
              ? localize(lang, "Webhook-триггер", "Webhook trigger")
              : target?.scheduleTriggers.length
                ? localize(lang, "Запуск по расписанию", "Scheduled trigger")
                : localize(lang, "Monitoring-триггер", "Monitoring trigger")}
          </DialogTitle>
          <DialogDescription>
            {target?.webhookTriggers.length
              ? localize(lang, `Пайплайн "${target.pipeline.name}" запускается входящими webhook-запросами. Нажимать "Запустить" не нужно.`, `Pipeline "${target.pipeline.name}" is started by incoming webhook requests. You do not need to press Run first.`)
              : target?.scheduleTriggers.length
                ? localize(lang, `Пайплайн "${target.pipeline.name}" запускается по расписанию. Ручной запуск здесь не нужен.`, `Pipeline "${target.pipeline.name}" is started by its schedule. There is nothing to launch manually.`)
                : target
                  ? localize(lang, `Пайплайн "${target.pipeline.name}" запускается alert-событиями мониторинга. Сохраните граф, и monitoring создаст запуск при совпадении условий.`, `Pipeline "${target.pipeline.name}" is started by server monitoring alerts. Save the graph and let monitoring create runs when a matching issue is detected.`)
                  : ""}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {target?.webhookTriggers.length ? (
            <div className="rounded-xl border border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
              {localize(lang, "Достаточно сохранить граф. Каждый POST на URL ниже создаст новый запуск пайплайна.", "Save is enough to arm the trigger. Every POST request to the webhook URL below creates a new pipeline run.")}
            </div>
          ) : null}

          {target?.webhookTriggers.map((trigger) => (
            <div key={trigger.id} className="space-y-2 rounded-xl border border-border bg-background/60 p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-foreground">{trigger.name || localize(lang, "Webhook-триггер", "Webhook trigger")}</div>
                  <div className="text-[11px] text-muted-foreground">Node `{trigger.node_id}`</div>
                </div>
                <Button size="sm" variant="outline" className="h-9" onClick={() => void handleCopyWebhookUrl(trigger.webhook_url)}>
                  <Copy className="mr-1.5 h-3.5 w-3.5" />
                  {localize(lang, "Копировать URL", "Copy URL")}
                </Button>
              </div>
              <div className="break-all rounded-lg border border-border bg-card px-3 py-2 text-xs text-muted-foreground">
                {toAbsoluteWebhookUrl(trigger.webhook_url)}
              </div>
            </div>
          ))}

          {target?.scheduleTriggers.map((trigger) => (
            <div key={trigger.id} className="space-y-1 rounded-xl border border-border bg-background/60 p-3">
              <div className="text-sm font-medium text-foreground">{trigger.name || localize(lang, "Schedule-триггер", "Schedule trigger")}</div>
              <div className="text-[11px] text-muted-foreground">Node `{trigger.node_id}`</div>
              <div className="text-xs text-muted-foreground">Cron: {trigger.cron_expression || localize(lang, "не задан", "not set")}</div>
            </div>
          ))}

          {target?.monitoringTriggers.length ? (
            <div className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
              {localize(lang, "Monitoring-триггеры активируются после сохранения. Новый запуск появится только когда мониторинг откроет подходящий alert.", "Monitoring triggers are armed after save. A new run appears only when server monitoring opens a matching alert.")}
            </div>
          ) : null}

          {target?.monitoringTriggers.map((trigger) => {
            const filters = trigger.monitoring_filters && typeof trigger.monitoring_filters === "object"
              ? (trigger.monitoring_filters as Record<string, unknown>)
              : {};
            const serverIds = Array.isArray(filters.server_ids) ? filters.server_ids.join(", ") : "any";
            const severities = Array.isArray(filters.severities) ? filters.severities.join(", ") : "any";
            const alertTypes = Array.isArray(filters.alert_types) ? filters.alert_types.join(", ") : "any";
            const containers = Array.isArray(filters.container_names) ? filters.container_names.join(", ") : "any";
            return (
              <div key={trigger.id} className="space-y-1 rounded-xl border border-border bg-background/60 p-3">
                <div className="text-sm font-medium text-foreground">{trigger.name || localize(lang, "Monitoring-триггер", "Monitoring trigger")}</div>
                <div className="text-[11px] text-muted-foreground">Node `{trigger.node_id}`</div>
                <div className="text-xs text-muted-foreground">{localize(lang, "Серверы", "Servers")}: {serverIds}</div>
                <div className="text-xs text-muted-foreground">{localize(lang, "Важность", "Severity")}: {severities}</div>
                <div className="text-xs text-muted-foreground">{localize(lang, "Тип alert", "Alert type")}: {alertTypes}</div>
                <div className="text-xs text-muted-foreground">{localize(lang, "Контейнеры", "Containers")}: {containers}</div>
              </div>
            );
          })}
        </div>
        <DialogFooter>
          <Button variant="outline" className="h-10" onClick={() => target && onOpenEditor(target.pipeline.id)}>
            {localize(lang, "Открыть редактор", "Open editor")}
          </Button>
          <Button variant="outline" className="h-10" onClick={onClose}>
            {localize(lang, "Закрыть", "Close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type DeletePipelineDialogProps = {
  lang: string;
  target: PipelineListItem | null;
  deleting: boolean;
  onClose: () => void;
  onConfirm: (pipelineId: number) => void;
};

export function DeletePipelineDialog({
  lang,
  target,
  deleting,
  onClose,
  onConfirm,
}: DeletePipelineDialogProps) {
  return (
    <Dialog open={Boolean(target)} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{localize(lang, "Удалить пайплайн", "Delete pipeline")}</DialogTitle>
          <DialogDescription>
            {target ? localize(lang, `Удалить "${target.name}"? Действие нельзя отменить.`, `Delete "${target.name}"? This cannot be undone.`) : ""}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" className="h-10" onClick={onClose}>
            {localize(lang, "Отмена", "Cancel")}
          </Button>
          <Button
            variant="destructive"
            className="h-10"
            onClick={() => target && onConfirm(target.id)}
            disabled={deleting}
          >
            {deleting && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            {localize(lang, "Удалить", "Delete")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
