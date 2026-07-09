import { CheckCircle2, Clock3, Database, FileText, Loader2, Workflow, XCircle } from "lucide-react";

import type { AssistantAction, AssistantChatMessage, AssistantChatSession, AssistantChatTurnResponse } from "@/api";
import { Badge } from "@/components/ui/badge";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";


type PlainObject = Record<string, unknown>;

export const QUICK_PROMPTS = {
  ru: [
    "Покажи агентов",
    "Покажи пайплайны",
    "Покажи доступные MCP servers",
    "Собери черновик пайплайна для ежедневной проверки сервера",
  ],
  en: [
    "Show agents",
    "Show pipelines",
    "Show available MCP servers",
    "Draft a pipeline for daily server checks",
  ],
};

export function formatDateTime(value: string, lang: "ru" | "en") {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(lang === "ru" ? "ru-RU" : "en-US", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function actionStatusLabel(status: AssistantAction["status"], lang: "ru" | "en") {
  switch (status) {
    case "completed":
      return localize(lang, "Готово", "Done");
    case "failed":
      return localize(lang, "Ошибка", "Failed");
    case "cancelled":
      return localize(lang, "Отменено", "Cancelled");
    case "running":
      return localize(lang, "Выполняется", "Running");
    case "requires_confirmation":
      return localize(lang, "Нужно подтверждение", "Needs confirmation");
    default:
      return localize(lang, "Подготовлено", "Prepared");
  }
}

export function actionRiskLabel(risk: AssistantAction["risk"], lang: "ru" | "en") {
  switch (risk) {
    case "read":
      return localize(lang, "read-only", "read-only");
    case "internal_write":
      return localize(lang, "изменение", "write");
    case "external":
      return localize(lang, "внешнее", "external");
    case "mutating":
      return localize(lang, "runtime", "runtime");
    case "dangerous":
      return localize(lang, "опасное", "dangerous");
    default:
      return risk;
  }
}

export function statusTone(status: AssistantAction["status"]) {
  if (status === "completed") return "border-emerald-500/35 bg-emerald-500/10 text-emerald-300";
  if (status === "failed" || status === "cancelled") return "border-destructive/35 bg-destructive/10 text-destructive";
  if (status === "running") return "border-primary/35 bg-primary/10 text-primary";
  if (status === "requires_confirmation") return "border-amber-500/35 bg-amber-500/10 text-amber-300";
  return "border-border bg-secondary/55 text-muted-foreground";
}

export function actionTone(action: AssistantAction) {
  if (action.status === "failed" || action.status === "cancelled") return "border-destructive/35";
  if (action.risk === "dangerous") return "border-amber-500/35";
  return "border-border/80";
}

export function ActionIcon({ action }: { action: AssistantAction }) {
  if (action.status === "completed") return <CheckCircle2 className="h-4 w-4 text-emerald-400" />;
  if (action.status === "failed" || action.status === "cancelled") return <XCircle className="h-4 w-4 text-destructive" />;
  if (action.status === "running") return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
  if (action.requires_confirmation) return <ShieldCheck className="h-4 w-4 text-amber-400" />;
  return <Clock3 className="h-4 w-4 text-muted-foreground" />;
}

function isPlainObject(value: unknown): value is PlainObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function asRecordArray(value: unknown): PlainObject[] {
  return Array.isArray(value) ? value.filter(isPlainObject) : [];
}

function stringifyShort(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(stringifyShort).join(", ") || "[]";
  if (isPlainObject(value)) return JSON.stringify(value);
  return String(value);
}

function pickResultList(result: PlainObject): { key: string; items: PlainObject[] } | null {
  const listKeys = ["agents", "pipelines", "runs", "skills", "mcp_servers", "results", "items"];
  for (const key of listKeys) {
    const items = asRecordArray(result[key]);
    if (items.length || Array.isArray(result[key])) return { key, items };
  }
  return null;
}

function pickPrimaryObject(result: PlainObject): { key: string; value: PlainObject } | null {
  const objectKeys = ["agent", "pipeline", "run", "draft", "server", "validation", "summary", "dry_run", "risk"];
  for (const key of objectKeys) {
    const value = result[key];
    if (isPlainObject(value)) return { key, value };
  }
  return null;
}

function humanizeKey(key: string, lang: "ru" | "en") {
  const ru: Record<string, string> = {
    agents: "Агенты",
    pipelines: "Пайплайны",
    runs: "Запуски",
    skills: "Skills",
    mcp_servers: "MCP servers",
    results: "Результаты",
    items: "Элементы",
    input: "Параметры",
    result: "Результат",
    raw: "JSON",
    pipeline_name: "Название",
    user_message: "Запрос",
    q: "Фильтр",
    count: "Количество",
    status: "Статус",
    mode: "Режим",
    id: "ID",
  };
  const en: Record<string, string> = {
    agents: "Agents",
    pipelines: "Pipelines",
    runs: "Runs",
    skills: "Skills",
    mcp_servers: "MCP servers",
    results: "Results",
    items: "Items",
    input: "Input",
    result: "Result",
    raw: "JSON",
    pipeline_name: "Name",
    user_message: "Request",
    q: "Filter",
    count: "Count",
    status: "Status",
    mode: "Mode",
    id: "ID",
  };
  return (lang === "ru" ? ru : en)[key] || key.replaceAll("_", " ");
}

function objectTitle(item: PlainObject, index: number) {
  return stringifyShort(
    item.name ?? item.title ?? item.slug ?? item.label ?? item.id ?? item.run_id ?? item.pipeline_id ?? index + 1,
  );
}

function objectDescription(item: PlainObject) {
  return stringifyShort(
    item.description ?? item.goal ?? item.service ?? item.command ?? item.url ?? item.host ?? item.message ?? item.status,
  );
}

function objectMeta(item: PlainObject) {
  return [
    item.id ? `#${stringifyShort(item.id)}` : "",
    stringifyShort(item.mode ?? item.status ?? item.state ?? item.type ?? item.category ?? ""),
    stringifyShort(item.safety_level ?? item.risk ?? item.transport ?? ""),
  ].filter((value) => value && value !== "—");
}

function compactFields(value: PlainObject) {
  return Object.entries(value)
    .filter(([key, field]) => key !== "target_url" && field !== null && field !== undefined && field !== "")
    .filter(([, field]) => typeof field !== "object")
    .slice(0, 8);
}

function RawJsonPreview({ label, value }: { label: string; value: PlainObject }) {
  const text = useMemo(() => {
    const raw = JSON.stringify(value || {}, null, 2);
    return raw.length > 2600 ? `${raw.slice(0, 2600)}\n...` : raw;
  }, [value]);

  if (!value || Object.keys(value).length === 0) return null;

  return (
    <details className="rounded-lg border border-border/70 bg-background/45 px-3 py-2">
      <summary className="cursor-pointer text-xs font-medium text-muted-foreground">{label}</summary>
      <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-2xs leading-5 text-muted-foreground">
        {text}
      </pre>
    </details>
  );
}

function KeyValueStrip({ value, lang }: { value: PlainObject; lang: "ru" | "en" }) {
  const fields = compactFields(value);
  if (!fields.length) return null;

  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {fields.map(([key, field]) => (
        <div key={key} className="min-w-0 rounded-lg border border-border/65 bg-background/45 px-3 py-2">
          <div className="truncate text-2xs font-medium text-muted-foreground">{humanizeKey(key, lang)}</div>
          <div className="mt-1 truncate text-xs font-semibold text-foreground">{stringifyShort(field)}</div>
        </div>
      ))}
    </div>
  );
}

function ResultList({
  title,
  items,
  empty,
}: {
  title: string;
  items: PlainObject[];
  empty: string;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-border/70 bg-background/45">
      <div className="flex items-center justify-between border-b border-border/60 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2 text-xs font-semibold text-foreground">
          <Database className="h-3.5 w-3.5 shrink-0 text-primary" />
          <span className="truncate">{title}</span>
        </div>
        <span className="text-2xs text-muted-foreground">{items.length}</span>
      </div>
      {items.length ? (
        <div className="divide-y divide-border/55">
          {items.slice(0, 8).map((item, index) => {
            const title = objectTitle(item, index);
            const description = objectDescription(item);
            const meta = objectMeta(item);
            return (
              <div key={`${title}-${index}`} className="grid gap-1 px-3 py-2.5 sm:grid-cols-[minmax(160px,0.8fr)_minmax(220px,1fr)] sm:gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-foreground">{title}</div>
                  {meta.length ? (
                    <div className="mt-1 flex min-w-0 flex-wrap gap-1.5">
                      {meta.slice(0, 3).map((item) => (
                        <span key={item} className="rounded-md border border-border/60 bg-secondary/50 px-1.5 py-0.5 text-2xs text-muted-foreground">
                          {item}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
                <div className="min-w-0 text-xs leading-5 text-muted-foreground">
                  <span className="line-clamp-2 break-words">{description}</span>
                </div>
              </div>
            );
          })}
          {items.length > 8 ? (
            <div className="px-3 py-2 text-xs text-muted-foreground">+{items.length - 8}</div>
          ) : null}
        </div>
      ) : (
        <div className="px-3 py-6 text-center text-sm text-muted-foreground">{empty}</div>
      )}
    </div>
  );
}

export function ActionResultPreview({ action }: { action: AssistantAction }) {
  const { lang } = useI18n();
  const result = action.result || {};
  const list = pickResultList(result);
  const primary = pickPrimaryObject(result);
  const total = typeof result.count === "number" ? result.count : list?.items.length;

  if (!Object.keys(result).length) return null;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">{localize(lang, "Результат", "Result")}</span>
        {typeof total === "number" ? (
          <span className="rounded-md border border-border/60 bg-secondary/45 px-2 py-0.5">
            {localize(lang, "записей", "records")}: {total}
          </span>
        ) : null}
      </div>
      {list ? (
        <ResultList
          title={humanizeKey(list.key, lang)}
          items={list.items}
          empty={localize(lang, "Ничего не найдено", "No items found")}
        />
      ) : null}
      {primary && !list ? (
        <div className="space-y-2 rounded-lg border border-border/70 bg-background/45 p-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
            <FileText className="h-3.5 w-3.5 text-primary" />
            {humanizeKey(primary.key, lang)}
          </div>
          <KeyValueStrip value={primary.value} lang={lang} />
        </div>
      ) : null}
      {!list && !primary ? <KeyValueStrip value={result} lang={lang} /> : null}
      <RawJsonPreview label={humanizeKey("raw", lang)} value={result} />
    </div>
  );
}

export function ActionInputPreview({ action }: { action: AssistantAction }) {
  const { lang } = useI18n();
  if (!action.input || !Object.keys(action.input).length) return null;
  const fields = compactFields(action.input);
  if (!fields.length) return null;
  return (
    <div className="space-y-2">
      <div className="text-xs font-medium text-muted-foreground">{humanizeKey("input", lang)}</div>
      <KeyValueStrip value={action.input} lang={lang} />
      <RawJsonPreview label={humanizeKey("raw", lang)} value={action.input} />
    </div>
  );
}

export function mergeTurnIntoChat(previous: AssistantChatSession | undefined, turn: AssistantChatTurnResponse): AssistantChatSession {
  const assistantMessage: AssistantChatMessage = {
    ...turn.assistant_message,
    metadata: {
      ...(turn.assistant_message.metadata || {}),
      actions: turn.actions,
    },
  };
  const merged = [...(previous?.messages || []), turn.user_message, assistantMessage];
  const byId = new Map<number, AssistantChatMessage>();
  for (const message of merged) byId.set(message.id, message);
  return {
    ...turn.chat,
    messages: Array.from(byId.values()).sort((a, b) => a.id - b.id),
  };
}

export function replaceActionInChat(previous: AssistantChatSession | undefined, action: AssistantAction): AssistantChatSession | undefined {
  if (!previous?.messages) return previous;
  return {
    ...previous,
    messages: previous.messages.map((message) => {
      if (message.id !== action.message_id) return message;
      const existing = message.metadata.actions || [];
      const replaced = existing.some((item) => item.id === action.id)
        ? existing.map((item) => (item.id === action.id ? action : item))
        : [...existing, action];
      return {
        ...message,
        metadata: {
          ...message.metadata,
          actions: replaced,
        },
      };
    }),
  };
}

