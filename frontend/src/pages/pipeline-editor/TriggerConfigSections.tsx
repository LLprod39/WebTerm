import { CheckCircle2, Clock, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { PipelineTrigger } from "@/lib/api";
import { cn } from "@/lib/utils";

import { AdvancedDisclosure, FieldHint, NodeFormSection } from "./PanelPrimitives";
import {
  CRON_PRESETS,
  dailyTimeToCron,
  describeCronExpression,
  getCronPresetId,
  getDailyTimeFromCron,
  getMinuteIntervalFromCron,
} from "./cronUtils";
import { parseJsonObjectText } from "./jsonSchemaUtils";
import { formatStudioDateTime } from "./pipelineGraphUtils";
import { localize } from "./presentation";

type Lang = "en" | "ru";
type NodeData = Record<string, unknown>;
type SetNodeData = (key: string, value: unknown) => void;
type SetNodePatch = (patch: Record<string, unknown>) => void;
type ServerOption = { id: number; name: string; host: string };

function isTriggerType(type: string) {
  return type === "trigger/manual" || type === "trigger/webhook" || type === "trigger/schedule" || type === "trigger/monitoring";
}

export function TriggerBasicFields({
  type,
  data,
  lang,
  onSet,
}: {
  type: string;
  data: NodeData;
  lang: Lang;
  onSet: SetNodeData;
}) {
  if (!isTriggerType(type)) return null;

  return (
    <>
      <div className="rounded-lg border border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
        {localize(
          lang,
          "Настройки триггера сохраняются вместе с пайплайном. Каждый триггер запускает только свою ветку графа.",
          "Trigger settings are saved with the pipeline. Each trigger launches only its own graph branch.",
        )}
      </div>
      <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
        <div>
          <p className="text-xs font-medium">{localize(lang, "Триггер включён", "Trigger enabled")}</p>
          <p className="text-xs text-muted-foreground">
            {localize(lang, "Можно выключить запуск, не удаляя ноду", "Disable the start without deleting the node")}
          </p>
        </div>
        <Switch checked={(data.is_active as boolean) ?? true} onCheckedChange={(checked) => onSet("is_active", checked)} />
      </div>
    </>
  );
}

function ManualTriggerConfig({ pipelineId, lang }: { pipelineId: number | null; lang: Lang }) {
  return (
    <div className="rounded-lg border border-border bg-muted/20 px-3 py-2 space-y-1">
      <p className="text-xs font-medium">{localize(lang, "Ручной запуск", "Manual start")}</p>
      <p className="text-xs text-muted-foreground">
        {localize(lang, "Запускается из кнопки ", "Start this pipeline from the Studio ")}
        <strong>{localize(lang, "Запуск", "Run")}</strong>
        {pipelineId
          ? localize(lang, ` или через POST /api/studio/pipelines/${pipelineId}/run/.`, ` dialog or POST /api/studio/pipelines/${pipelineId}/run/.`)
          : "."}
      </p>
      <p className="text-xs text-muted-foreground">
        {localize(
          lang,
          "Если в графе несколько ручных триггеров, оператор выбирает, с какой ноды начать run.",
          "If the graph has multiple manual triggers, the operator chooses which trigger node starts the run.",
        )}
      </p>
    </div>
  );
}

function WebhookTriggerConfig({
  pipelineId,
  trigger,
  triggerWebhookUrl,
  webhookMapText,
  lang,
  onSet,
  onWebhookMapTextChange,
}: {
  pipelineId: number | null;
  trigger?: PipelineTrigger | null;
  triggerWebhookUrl: string;
  webhookMapText: string;
  lang: Lang;
  onSet: SetNodeData;
  onWebhookMapTextChange: (value: string) => void;
}) {
  const webhookState = parseJsonObjectText(webhookMapText);

  return (
    <NodeFormSection title={localize(lang, "Вход / условие", "Input / condition")}>
      <div className="space-y-1.5">
        <Label className="text-xs">Webhook URL</Label>
        <div className="text-xs text-muted-foreground bg-muted/30 rounded px-2 py-1.5 break-all">
          {pipelineId && triggerWebhookUrl
            ? triggerWebhookUrl
            : localize(lang, "Сохраните pipeline один раз, чтобы получить Webhook URL", "Save the pipeline once to generate the webhook URL")}
        </div>
      </div>
      <AdvancedDisclosure title={localize(lang, "Дополнительно", "Advanced")}>
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Маппинг payload (JSON)", "Payload mapping (JSON)")}</Label>
          <Textarea
            value={webhookMapText}
            onChange={(event) => {
              const value = event.target.value;
              onWebhookMapTextChange(value);
              const parsed = parseJsonObjectText(value);
              if (!parsed.error) onSet("webhook_payload_map", parsed.value || {});
            }}
            placeholder={'{\n  "branch": "ref",\n  "commit": "head_commit.id"\n}'}
            className="text-xs font-mono resize-none"
            rows={6}
          />
          <FieldHint>
            {localize(lang, "Сопоставьте поля входящего payload с переменными pipeline, например", "Map incoming payload fields into pipeline variables, for example")}{" "}
            <code>head_commit.id</code>.
          </FieldHint>
          {webhookState.error && <p className="text-xs text-red-400">{webhookState.error}</p>}
        </div>
      </AdvancedDisclosure>
      {trigger && (
        <FieldHint>
          {localize(lang, "Последний Webhook run:", "Last webhook run:")} {formatStudioDateTime(trigger.last_triggered_at)}
        </FieldHint>
      )}
    </NodeFormSection>
  );
}

function ScheduleTriggerConfig({
  data,
  trigger,
  lang,
  onSet,
}: {
  data: NodeData;
  trigger?: PipelineTrigger | null;
  lang: Lang;
  onSet: SetNodeData;
}) {
  const cronExpression = String(data.cron_expression || trigger?.cron_expression || "");
  const presetId = getCronPresetId(cronExpression);
  const dailyTime = getDailyTimeFromCron(cronExpression);
  const minuteInterval = getMinuteIntervalFromCron(cronExpression);

  return (
    <NodeFormSection
      title={localize(lang, "Расписание запуска", "Run schedule")}
      description={localize(
        lang,
        "Выберите понятный режим запуска. Cron доступен ниже только для нестандартных расписаний.",
        "Choose a readable schedule. Cron is below for advanced custom schedules.",
      )}
    >
      <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2">
        <div className="flex items-start gap-2">
          <Clock className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
          <div className="min-w-0">
            <div className="text-sm font-semibold text-foreground">{describeCronExpression(cronExpression, lang)}</div>
            <div className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {localize(lang, "Сохраните пайплайн, чтобы scheduler начал использовать это расписание.", "Save the pipeline so the scheduler starts using this schedule.")}
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <Label className="text-xs">{localize(lang, "Как часто запускать", "How often to run")}</Label>
        <div className="grid grid-cols-1 gap-2">
          {CRON_PRESETS.map((preset) => {
            const active = presetId === preset.id;
            return (
              <button
                key={preset.value}
                type="button"
                className={cn(
                  "rounded-lg border px-3 py-2 text-left transition-colors",
                  active
                    ? "border-primary/50 bg-primary/15 text-foreground"
                    : "border-border/70 bg-background/35 text-muted-foreground hover:border-primary/30 hover:bg-secondary/25",
                )}
                onClick={() => onSet("cron_expression", preset.value)}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-foreground">{localize(lang, preset.labelRu, preset.labelEn)}</span>
                  {active ? <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-primary" /> : null}
                </span>
                <span className="mt-1 block text-xs leading-relaxed">{localize(lang, preset.descriptionRu, preset.descriptionEn)}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Интервал в минутах", "Minute interval")}</Label>
          <div className="flex items-center gap-2">
            <Input
              type="number"
              min={1}
              max={59}
              value={minuteInterval}
              onChange={(event) => {
                const minutes = Math.max(1, Math.min(59, Number(event.target.value) || 5));
                onSet("cron_expression", `*/${minutes} * * * *`);
              }}
              className="h-8 text-xs"
            />
            <span className="text-xs text-muted-foreground">{localize(lang, "мин", "min")}</span>
          </div>
          <FieldHint>{localize(lang, "Для частых проверок. Например 5, 10 или 15 минут.", "For frequent checks, e.g. 5, 10, or 15 minutes.")}</FieldHint>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Ежедневно в", "Daily at")}</Label>
          <Input
            type="time"
            value={dailyTime}
            onChange={(event) => onSet("cron_expression", dailyTimeToCron(event.target.value || "04:00"))}
            className="h-8 text-xs"
          />
          <FieldHint>{localize(lang, "Удобно для ежедневных отчетов в Telegram.", "Useful for daily Telegram reports.")}</FieldHint>
        </div>
      </div>

      <AdvancedDisclosure title={localize(lang, "Advanced: cron выражение", "Advanced: cron expression")}>
        <div className="space-y-1.5">
          <Label className="text-xs">Cron</Label>
          <Input
            value={cronExpression}
            onChange={(event) => onSet("cron_expression", event.target.value)}
            placeholder="*/5 * * * *"
            className="h-8 text-xs font-mono"
          />
          <FieldHint>
            {localize(lang, "Формат из 5 полей:", "5-field format:")} <code>minute hour day month weekday</code>.{" "}
            {localize(lang, "Пример:", "Example:")} <code>0 4 * * *</code> = {localize(lang, "каждый день в 04:00", "daily at 04:00")}.
          </FieldHint>
        </div>
      </AdvancedDisclosure>

      {trigger && (
        <FieldHint>
          {localize(lang, "Последний запуск по расписанию:", "Last scheduled run:")} {formatStudioDateTime(trigger.last_triggered_at)}
        </FieldHint>
      )}
    </NodeFormSection>
  );
}

function MonitoringTriggerConfig({
  data,
  trigger,
  servers,
  lang,
  onSetMonitoringFilters,
}: {
  data: NodeData;
  trigger?: PipelineTrigger | null;
  servers: ServerOption[];
  lang: Lang;
  onSetMonitoringFilters: SetNodePatch;
}) {
  return (
    <NodeFormSection
      title={localize(lang, "Вход / условие", "Input / condition")}
      description={localize(lang, "Фильтры alert-ов, по которым мониторинг запустит эту ветку.", "Alert filters that start this branch from monitoring.")}
    >
      <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
        {localize(
          lang,
          "Monitoring-триггер ждёт alert от сервера и не запускается из диалога Run. Сохраните pipeline, чтобы он начал ждать подходящее событие.",
          "Monitoring trigger waits for a server alert and does not start from the Run dialog. Save the pipeline to arm it.",
        )}
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Целевые серверы", "Target servers")}</Label>
        <div className="space-y-1">
          {((data.server_ids as number[]) || []).map((sid) => {
            const server = servers.find((item) => item.id === sid);
            return (
              <div key={sid} className="flex items-center justify-between rounded bg-muted/30 px-2 py-1 text-xs">
                <span>{server ? `${server.name} (${server.host})` : `Server #${sid}`}</span>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-5 w-5"
                  onClick={() => onSetMonitoringFilters({ server_ids: ((data.server_ids as number[]) || []).filter((id) => id !== sid) })}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            );
          })}
          <Select
            onValueChange={(value) => {
              const ids = ((data.server_ids as number[]) || []);
              const nextId = parseInt(value, 10);
              if (!ids.includes(nextId)) onSetMonitoringFilters({ server_ids: [...ids, nextId] });
            }}
          >
            <SelectTrigger className="h-8 text-xs">
              <SelectValue placeholder={localize(lang, "Добавить сервер...", "Add server...")} />
            </SelectTrigger>
            <SelectContent>
              {servers.map((server) => (
                <SelectItem key={server.id} value={String(server.id)}>
                  {server.name} ({server.host})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FieldHint>{localize(lang, "Оставьте пустым, чтобы реагировать на alert-ы со всех доступных серверов.", "Leave empty to react to alerts from any accessible server.")}</FieldHint>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Severity-фильтры", "Severity filters")}</Label>
        <div className="grid grid-cols-1 gap-2">
          {["info", "warning", "critical"].map((value) => {
            const selected = ((data.severities as string[]) || []).includes(value);
            return (
              <label key={value} className="flex items-center gap-2 rounded border border-border px-2 py-2 text-xs">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5"
                  checked={selected}
                  onChange={() => {
                    const current = ((data.severities as string[]) || []).filter(Boolean);
                    onSetMonitoringFilters({
                      severities: selected ? current.filter((item) => item !== value) : [...current, value],
                    });
                  }}
                />
                <span>{value}</span>
              </label>
            );
          })}
        </div>
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Типы alert-ов", "Alert types")}</Label>
        <div className="grid grid-cols-1 gap-2">
          {["service", "unreachable", "cpu", "memory", "disk", "log_error"].map((value) => {
            const selected = ((data.alert_types as string[]) || []).includes(value);
            return (
              <label key={value} className="flex items-center gap-2 rounded border border-border px-2 py-2 text-xs">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5"
                  checked={selected}
                  onChange={() => {
                    const current = ((data.alert_types as string[]) || []).filter(Boolean);
                    onSetMonitoringFilters({
                      alert_types: selected ? current.filter((item) => item !== value) : [...current, value],
                    });
                  }}
                />
                <span>{value}</span>
              </label>
            );
          })}
        </div>
      </div>
      <AdvancedDisclosure title={localize(lang, "Дополнительно", "Advanced")}>
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Имена Docker-контейнеров", "Docker container names")}</Label>
          <Textarea
            value={((data.container_names as string[]) || []).join("\n")}
            onChange={(event) =>
              onSetMonitoringFilters({
                container_names: event.target.value
                  .split(/\r?\n/)
                  .map((value) => value.trim())
                  .filter(Boolean),
              })
            }
            placeholder={"mini-prod-mcp-demo"}
            className="text-xs font-mono resize-none"
            rows={3}
          />
          <FieldHint>{localize(lang, "Опционально. Одно имя контейнера на строку.", "Optional. One container name per line.")}</FieldHint>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Поиск по тексту", "Text match")}</Label>
          <Input
            value={(data.match_text as string) || ""}
            onChange={(event) => onSetMonitoringFilters({ match_text: event.target.value })}
            placeholder={localize(lang, "Опциональная подстрока в title/message/metadata", "Optional substring to match in title/message/metadata")}
            className="h-8 text-xs"
          />
        </div>
      </AdvancedDisclosure>
      {trigger ? (
        <FieldHint>
          {localize(lang, "Последний запуск мониторингом:", "Last monitoring-triggered run:")} {formatStudioDateTime(trigger.last_triggered_at)}
        </FieldHint>
      ) : null}
    </NodeFormSection>
  );
}

export function TriggerSpecificConfigSections({
  type,
  data,
  pipelineId,
  trigger,
  triggerWebhookUrl,
  webhookMapText,
  servers,
  lang,
  onSet,
  onSetMonitoringFilters,
  onWebhookMapTextChange,
}: {
  type: string;
  data: NodeData;
  pipelineId: number | null;
  trigger?: PipelineTrigger | null;
  triggerWebhookUrl: string;
  webhookMapText: string;
  servers: ServerOption[];
  lang: Lang;
  onSet: SetNodeData;
  onSetMonitoringFilters: SetNodePatch;
  onWebhookMapTextChange: (value: string) => void;
}) {
  if (type === "trigger/manual") {
    return <ManualTriggerConfig pipelineId={pipelineId} lang={lang} />;
  }

  if (type === "trigger/webhook") {
    return (
      <WebhookTriggerConfig
        pipelineId={pipelineId}
        trigger={trigger}
        triggerWebhookUrl={triggerWebhookUrl}
        webhookMapText={webhookMapText}
        lang={lang}
        onSet={onSet}
        onWebhookMapTextChange={onWebhookMapTextChange}
      />
    );
  }

  if (type === "trigger/schedule") {
    return <ScheduleTriggerConfig data={data} trigger={trigger} lang={lang} onSet={onSet} />;
  }

  if (type === "trigger/monitoring") {
    return (
      <MonitoringTriggerConfig
        data={data}
        trigger={trigger}
        servers={servers}
        lang={lang}
        onSetMonitoringFilters={onSetMonitoringFilters}
      />
    );
  }

  return null;
}
