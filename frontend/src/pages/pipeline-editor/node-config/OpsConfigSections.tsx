import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

import { FieldHint, NodeFormSection } from "../PanelPrimitives";
import { localize } from "../presentation";
import type { Lang, NodeData, ServerOption, SetNodeData } from "./types";

const LOG_SOURCES = ["journal", "service", "docker", "syslog", "messages", "auth", "nginx_error", "nginx_access", "apache_error", "apache_access"];
const SNAPSHOT_SECTIONS = ["overview", "services", "processes", "docker", "logs", "disk", "network", "packages"];
const LOG_SOURCE_LABELS: Record<string, string> = {
  service: "service journal",
  docker: "docker logs",
  auth: "auth.log",
  nginx_error: "nginx error",
  nginx_access: "nginx access",
  apache_error: "apache error",
  apache_access: "apache access",
};

const RU_OPTION_LABELS: Record<string, string> = {
  overview: "Обзор",
  services: "Службы",
  processes: "Процессы",
  docker: "Docker",
  logs: "Логи",
  disk: "Диски",
  network: "Сеть",
  packages: "Пакеты",
  read: "Прочитать",
  write: "Записать",
  list_updates: "Показать обновления",
  install: "Установить",
  update: "Обновить",
  remove: "Удалить",
  inspect: "Проверить",
  journal_vacuum: "Очистить journal",
  tmp_cleanup: "Очистить временные файлы",
  verify_latest: "Проверить последний backup",
  start: "Запустить",
  stop: "Остановить",
  restart: "Перезапустить",
  reload: "Перечитать конфигурацию",
  terminate: "Завершить",
  kill_force: "Завершить принудительно",
};

function optionLabel(lang: Lang, value: string) {
  return lang === "ru" ? RU_OPTION_LABELS[value] || value : value;
}

function OpsTargetFields({ type, data, servers, lang, onSet }: OpsBaseProps) {
  if (type === "ops/http_check" || type === "ops/alert_update") return null;

  return (
    <>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Целевой сервер", "Target server")}</Label>
        <Select value={String(data.server_id || "")} onValueChange={(value) => onSet("server_id", parseInt(value, 10))}>
          <SelectTrigger className="h-8 text-xs">
            <SelectValue placeholder={localize(lang, "Из контекста или выбрать...", "From context or select...")} />
          </SelectTrigger>
          <SelectContent>
            {servers.map((server) => (
              <SelectItem key={server.id} value={String(server.id)}>{server.name} ({server.host})</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Ключ server_id из контекста", "Context server_id key")}</Label>
        <Input
          value={(data.server_id_context_key as string) || "server_id"}
          onChange={(event) => onSet("server_id_context_key", event.target.value)}
          className="h-8 text-xs font-mono"
          placeholder="server_id"
        />
      </div>
    </>
  );
}

function SnapshotFields({ type, data, lang, onSet }: OpsBaseProps) {
  if (type !== "ops/server_snapshot") return null;

  return (
    <>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Разделы снимка", "Snapshot sections")}</Label>
        <div className="grid grid-cols-2 gap-2">
          {SNAPSHOT_SECTIONS.map((section) => {
            const selected = ((data.sections as string[]) || []).includes(section);
            return (
              <label key={section} className="flex items-center gap-2 rounded border border-border px-2 py-2 text-xs">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5"
                  checked={selected}
                  onChange={() => {
                    const current = ((data.sections as string[]) || []).filter(Boolean);
                    onSet("sections", selected ? current.filter((item) => item !== section) : [...current, section]);
                  }}
                />
                <span>{optionLabel(lang, section)}</span>
              </label>
            );
          })}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Источник логов", "Log source")}</Label>
          <Input value={(data.log_source as string) || "journal"} onChange={(event) => onSet("log_source", event.target.value)} className="h-8 text-xs" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Строк логов", "Log lines")}</Label>
          <Input type="number" value={(data.lines as number) || 80} onChange={(event) => onSet("lines", parseInt(event.target.value, 10) || 80)} className="h-8 text-xs" />
        </div>
      </div>
    </>
  );
}

function LogQueryFields({ type, data, lang, onSet }: OpsBaseProps) {
  if (type !== "ops/log_query") return null;

  return (
    <>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Источник логов", "Log source")}</Label>
        <Select value={(data.source as string) || "journal"} onValueChange={(value) => onSet("source", value)}>
          <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            {LOG_SOURCES.map((source) => <SelectItem key={source} value={source}>{LOG_SOURCE_LABELS[source] || source}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      {(data.source as string) === "service" ? (
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Служба systemd", "systemd unit")}</Label>
          <Input value={(data.service as string) || ""} onChange={(event) => onSet("service", event.target.value)} placeholder="nginx" className="h-8 text-xs font-mono" />
        </div>
      ) : null}
      {(data.source as string) === "docker" ? (
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Контейнер", "Container")}</Label>
          <Input value={(data.container as string) || ""} onChange={(event) => onSet("container", event.target.value)} placeholder="{container_name}" className="h-8 text-xs font-mono" />
        </div>
      ) : null}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Строк", "Lines")}</Label>
          <Input type="number" value={(data.lines as number) || 120} onChange={(event) => onSet("lines", parseInt(event.target.value, 10) || 120)} className="h-8 text-xs" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Фильтр текста", "Text filter")}</Label>
          <Input value={(data.filter_text as string) || ""} onChange={(event) => onSet("filter_text", event.target.value)} placeholder="error, timeout, failed" className="h-8 text-xs" />
        </div>
      </div>
    </>
  );
}

function FileActionFields({ type, data, lang, onSet }: OpsBaseProps) {
  if (type !== "ops/file_action") return null;

  return (
    <>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Действие", "Action")}</Label>
        <Select value={(data.action as string) || "read"} onValueChange={(value) => onSet("action", value)}>
          <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="read">{optionLabel(lang, "read")}</SelectItem>
            <SelectItem value="write">{optionLabel(lang, "write")}</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Путь", "Path")}</Label>
        <Input value={(data.path as string) || ""} onChange={(event) => onSet("path", event.target.value)} placeholder="/etc/nginx/nginx.conf" className="h-8 text-xs font-mono" />
      </div>
      {(data.action as string) === "write" ? (
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Содержимое", "Content")}</Label>
          <Textarea value={(data.content as string) || ""} onChange={(event) => onSet("content", event.target.value)} placeholder="{generated_config}" className="min-h-32 resize-y text-xs font-mono" />
          <FieldHint>{localize(lang, "Запись требует путь подтверждения; содержимое может использовать шаблоны.", "Write requires an approval path; content can use templates.")}</FieldHint>
        </div>
      ) : null}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Лимит, байт", "Max bytes")}</Label>
          <Input type="number" value={(data.max_bytes as number) || 131072} onChange={(event) => onSet("max_bytes", parseInt(event.target.value, 10) || 131072)} className="h-8 text-xs" />
        </div>
        {(data.action as string) === "write" ? (
          <label className="mt-6 flex items-center gap-2 text-xs text-muted-foreground">
            <input type="checkbox" className="h-4 w-4" checked={Boolean(data.allow_empty_content)} onChange={(event) => onSet("allow_empty_content", event.target.checked)} />
            <span>{localize(lang, "Разрешить пустой файл", "Allow empty file")}</span>
          </label>
        ) : null}
      </div>
    </>
  );
}

function PackageActionFields({ type, data, lang, onSet }: OpsBaseProps) {
  if (type !== "ops/package_action") return null;
  const action = (data.action as string) || "list_updates";

  return (
    <>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Действие", "Action")}</Label>
        <Select value={action} onValueChange={(value) => onSet("action", value)}>
          <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            {["list_updates", "install", "update", "remove"].map((item) => <SelectItem key={item} value={item}>{optionLabel(lang, item)}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      {action !== "list_updates" ? (
        <>
          <div className="space-y-1.5">
            <Label className="text-xs">{localize(lang, "Пакеты", "Packages")}</Label>
            <Input
              value={Array.isArray(data.packages) ? (data.packages as string[]).join(", ") : String(data.packages || "")}
              onChange={(event) => onSet("packages", event.target.value.split(",").map((item) => item.trim()).filter(Boolean))}
              placeholder="nginx, curl"
              className="h-8 text-xs font-mono"
            />
            <FieldHint>{localize(lang, "Укажите пакеты явно. Массовое обновление всей системы здесь запрещено.", "Explicit package list only; whole-system upgrade is not supported here.")}</FieldHint>
          </div>
          <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
            <span className="text-xs">{localize(lang, "Проверить пакеты после изменения", "Post-change package verification")}</span>
            <input type="checkbox" className="h-4 w-4" checked={data.verify !== false} onChange={(event) => onSet("verify", event.target.checked)} />
          </div>
        </>
      ) : null}
    </>
  );
}

function DiskCleanupFields({ type, data, lang, onSet }: OpsBaseProps) {
  if (type !== "ops/disk_cleanup") return null;
  const action = (data.action as string) || "inspect";

  return (
    <>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Действие", "Action")}</Label>
        <Select value={action} onValueChange={(value) => onSet("action", value)}>
          <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="inspect">{optionLabel(lang, "inspect")}</SelectItem>
            <SelectItem value="journal_vacuum">{optionLabel(lang, "journal_vacuum")}</SelectItem>
            <SelectItem value="tmp_cleanup">{optionLabel(lang, "tmp_cleanup")}</SelectItem>
          </SelectContent>
        </Select>
        <FieldHint>{localize(lang, "Очистка ограничена journalctl vacuum и старыми файлами /tmp, /var/tmp.", "Cleanup is limited to journalctl vacuum and old files under /tmp, /var/tmp.")}</FieldHint>
      </div>
      {action === "journal_vacuum" ? (
        <div className="grid grid-cols-2 gap-3">
          <NumberInput label={localize(lang, "Хранить, дней", "Vacuum time days")} value={(data.vacuum_time_days as number) || 14} onChange={(value) => onSet("vacuum_time_days", value || 14)} />
          <NumberInput label={localize(lang, "Лимит, МБ", "Vacuum size MB")} value={(data.vacuum_size_mb as number) || ""} placeholder="1024" onChange={(value) => onSet("vacuum_size_mb", Number.isFinite(value) ? value : undefined)} />
        </div>
      ) : null}
      {action === "tmp_cleanup" ? (
        <div className="grid grid-cols-2 gap-3">
          <NumberInput label={localize(lang, "Старше, дней", "Min age days")} value={(data.min_age_days as number) || 7} onChange={(value) => onSet("min_age_days", value || 7)} />
          <NumberInput label={localize(lang, "Не больше записей", "Max entries")} value={(data.max_entries as number) || 50} onChange={(value) => onSet("max_entries", value || 50)} />
        </div>
      ) : null}
      {action !== "inspect" ? (
        <div className="grid grid-cols-2 gap-3">
          <CheckboxCard label={localize(lang, "Только предпросмотр", "Dry run")} checked={data.dry_run === true} onChange={(checked) => onSet("dry_run", checked)} />
          <CheckboxCard label={localize(lang, "Проверить после", "Verify after")} checked={data.verify !== false} onChange={(checked) => onSet("verify", checked)} />
        </div>
      ) : null}
    </>
  );
}

function BackupFields({ type, data, lang, onSet }: OpsBaseProps) {
  if (type !== "ops/backup_restore_check") return null;

  return (
    <>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Действие", "Action")}</Label>
        <Select value={(data.action as string) || "inspect"} onValueChange={(value) => onSet("action", value)}>
          <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="inspect">{optionLabel(lang, "inspect")}</SelectItem>
            <SelectItem value="verify_latest">{optionLabel(lang, "verify_latest")}</SelectItem>
          </SelectContent>
        </Select>
        <FieldHint>{localize(lang, "Каталог резервных копий проверяется только для чтения. Восстановление не запускается.", "Read-only backup directory check; restore is not executed.")}</FieldHint>
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Путь к резервным копиям", "Backup path")}</Label>
        <Input value={(data.path as string) || ""} onChange={(event) => onSet("path", event.target.value)} placeholder="/var/backups" className="h-8 text-xs font-mono" />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <NumberInput label={localize(lang, "Глубина", "Max depth")} value={(data.max_depth as number) || 2} onChange={(value) => onSet("max_depth", value || 2)} />
        <NumberInput label={localize(lang, "Файлов", "Max files")} value={(data.max_files as number) || 20} onChange={(value) => onSet("max_files", value || 20)} />
        <NumberInput label={localize(lang, "Возраст, ч", "Max age hours")} value={(data.max_age_hours as number) || 24} onChange={(value) => onSet("max_age_hours", value || 24)} />
      </div>
    </>
  );
}

function SimpleActionFields({ type, data, lang, onSet }: OpsBaseProps) {
  if (!["ops/service_action", "ops/docker_action", "ops/process_action", "ops/http_check", "ops/alert_update"].includes(type)) return null;

  if (type === "ops/service_action") {
    return <UnitOrContainerFields label={localize(lang, "Служба systemd", "systemd unit")} value={(data.service as string) || ""} placeholder="nginx" action={(data.action as string) || "restart"} actions={["start", "stop", "restart", "reload"]} onValue={(value) => onSet("service", value)} onAction={(value) => onSet("action", value)} lang={lang} />;
  }
  if (type === "ops/docker_action") {
    return <UnitOrContainerFields label={localize(lang, "Контейнер", "Container")} value={(data.container as string) || ""} placeholder="{container_name}" action={(data.action as string) || "restart"} actions={["start", "stop", "restart"]} onValue={(value) => onSet("container", value)} onAction={(value) => onSet("action", value)} lang={lang} />;
  }
  if (type === "ops/process_action") {
    return <UnitOrContainerFields label="PID" value={String(data.pid || "")} placeholder="{pid}" action={(data.action as string) || "terminate"} actions={["terminate", "kill_force"]} onValue={(value) => onSet("pid", value)} onAction={(value) => onSet("action", value)} lang={lang} />;
  }
  if (type === "ops/http_check") {
    return <HttpCheckFields data={data} lang={lang} onSet={onSet} />;
  }
  return <AlertUpdateFields data={data} lang={lang} onSet={onSet} />;
}

function UnitOrContainerFields({ label, value, placeholder, action, actions, lang, onValue, onAction }: { label: string; value: string; placeholder: string; action: string; actions: string[]; lang: Lang; onValue: (value: string) => void; onAction: (value: string) => void }) {
  return (
    <>
      <div className="space-y-1.5">
        <Label className="text-xs">{label}</Label>
        <Input value={value} onChange={(event) => onValue(event.target.value)} placeholder={placeholder} className="h-8 text-xs font-mono" />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Действие", "Action")}</Label>
        <Select value={action} onValueChange={onAction}>
          <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>{actions.map((item) => <SelectItem key={item} value={item}>{optionLabel(lang, item)}</SelectItem>)}</SelectContent>
        </Select>
      </div>
    </>
  );
}

function HttpCheckFields({ data, lang, onSet }: { data: NodeData; lang: Lang; onSet: SetNodeData }) {
  return (
    <>
      <div className="space-y-1.5">
        <Label className="text-xs">URL</Label>
        <Input value={(data.url as string) || ""} onChange={(event) => onSet("url", event.target.value)} placeholder="https://service.example.com/health" className="h-8 text-xs font-mono" />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Метод", "Method")}</Label>
          <Select value={(data.method as string) || "GET"} onValueChange={(value) => onSet("method", value)}>
            <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="GET">GET</SelectItem><SelectItem value="HEAD">HEAD</SelectItem></SelectContent>
          </Select>
        </div>
        <NumberInput label={localize(lang, "Ожидание, с", "Timeout")} value={(data.timeout_seconds as number) || 15} onChange={(value) => onSet("timeout_seconds", value || 15)} />
        <NumberInput label={localize(lang, "Повторы", "Retries")} value={(data.retries as number) || 1} onChange={(value) => onSet("retries", value || 1)} />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Ожидаемые HTTP-статусы", "Expected HTTP statuses")}</Label>
        <Input value={((data.expected_status as number[]) || [200]).join(",")} onChange={(event) => onSet("expected_status", event.target.value.split(",").map((item) => parseInt(item.trim(), 10)).filter(Number.isFinite))} placeholder="200,204" className="h-8 text-xs font-mono" />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Текст в ответе", "Body contains")}</Label>
        <Input value={(data.body_contains as string) || ""} onChange={(event) => onSet("body_contains", event.target.value)} className="h-8 text-xs" />
      </div>
    </>
  );
}

function AlertUpdateFields({ data, lang, onSet }: { data: NodeData; lang: Lang; onSet: SetNodeData }) {
  return (
    <>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "ID инцидента", "Alert ID")}</Label>
        <Input value={String(data.alert_id || "")} onChange={(event) => onSet("alert_id", event.target.value)} placeholder="{alert_id}" className="h-8 text-xs font-mono" />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Ключ ID инцидента в контексте", "Context alert_id key")}</Label>
        <Input value={(data.alert_id_context_key as string) || "alert_id"} onChange={(event) => onSet("alert_id_context_key", event.target.value)} className="h-8 text-xs font-mono" />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Заметка", "Note")}</Label>
        <Textarea value={(data.note as string) || ""} onChange={(event) => onSet("note", event.target.value)} className="text-xs resize-none" rows={3} />
      </div>
    </>
  );
}

function NumberInput({ label, value, placeholder, onChange }: { label: string; value: number | string; placeholder?: string; onChange: (value: number) => void }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      <Input type="number" value={value} placeholder={placeholder} onChange={(event) => onChange(parseInt(event.target.value, 10))} className="h-8 text-xs" />
    </div>
  );
}

function CheckboxCard({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs text-muted-foreground">
      <input type="checkbox" className="h-4 w-4" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

type OpsBaseProps = {
  type: string;
  data: NodeData;
  servers: ServerOption[];
  lang: Lang;
  onSet: SetNodeData;
};

export function OpsConfigSections(props: OpsBaseProps) {
  const { type, data, lang, onSet } = props;
  if (!type.startsWith("ops/")) return null;
  const action = String(data.action || "");
  const mutatingWithGenericDryRun =
    (type === "ops/file_action" && action === "write") ||
    (type === "ops/package_action" && ["install", "update", "remove"].includes(action)) ||
    ["ops/service_action", "ops/docker_action", "ops/process_action", "ops/alert_update"].includes(type);

  return (
    <NodeFormSection
      title={localize(lang, "Операция", "OPS target")}
      description={localize(lang, "Системные действия проходят проверки безопасности и сохраняются в аудите.", "Structured operations reuse existing WebTerm Linux UI checks, audit, and safe parameters.")}
    >
      <OpsTargetFields {...props} />
      <SnapshotFields {...props} />
      <LogQueryFields {...props} />
      <FileActionFields {...props} />
      <PackageActionFields {...props} />
      <DiskCleanupFields {...props} />
      <BackupFields {...props} />
      <SimpleActionFields {...props} />
      {mutatingWithGenericDryRun ? (
        <CheckboxCard
          label={localize(lang, "Только предпросмотр (без изменений)", "Preview only (no changes)")}
          checked={data.dry_run === true}
          onChange={(checked) => onSet("dry_run", checked)}
        />
      ) : null}
      {type === "ops/service_action" || type === "ops/docker_action" ? (
        <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
          <span className="text-xs">{localize(lang, "Проверить после изменения", "Post-change verification")}</span>
          <input type="checkbox" className="h-4 w-4" checked={data.verify !== false} onChange={(event) => onSet("verify", event.target.checked)} />
        </div>
      ) : null}
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "При ошибке", "On Failure")}</Label>
        <Select value={(data.on_failure as string) || "continue"} onValueChange={(value) => onSet("on_failure", value)}>
          <SelectTrigger className="h-7 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="abort">{localize(lang, "Остановить сценарий", "Abort pipeline")}</SelectItem>
            <SelectItem value="continue">{localize(lang, "Продолжить", "Continue")}</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </NodeFormSection>
  );
}
