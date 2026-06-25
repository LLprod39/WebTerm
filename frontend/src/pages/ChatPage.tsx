import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clock3,
  Database,
  ExternalLink,
  FileText,
  Loader2,
  MessageSquare,
  Plus,
  Send,
  ShieldCheck,
  User,
  Workflow,
  XCircle,
} from "lucide-react";

import {
  cancelAssistantAction,
  confirmAssistantAction,
  fetchAssistantChat,
  fetchAssistantChats,
  sendAssistantChatMessage,
  startAssistantChat,
  type AssistantAction,
  type AssistantChatMessage,
  type AssistantChatSession,
  type AssistantChatTurnResponse,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type PlainObject = Record<string, unknown>;

const QUICK_PROMPTS = {
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

function formatDateTime(value: string, lang: "ru" | "en") {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(lang === "ru" ? "ru-RU" : "en-US", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function actionStatusLabel(status: AssistantAction["status"], lang: "ru" | "en") {
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

function actionRiskLabel(risk: AssistantAction["risk"], lang: "ru" | "en") {
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

function statusTone(status: AssistantAction["status"]) {
  if (status === "completed") return "border-emerald-500/35 bg-emerald-500/10 text-emerald-300";
  if (status === "failed" || status === "cancelled") return "border-destructive/35 bg-destructive/10 text-destructive";
  if (status === "running") return "border-primary/35 bg-primary/10 text-primary";
  if (status === "requires_confirmation") return "border-amber-500/35 bg-amber-500/10 text-amber-300";
  return "border-border bg-secondary/55 text-muted-foreground";
}

function actionTone(action: AssistantAction) {
  if (action.status === "failed" || action.status === "cancelled") return "border-destructive/35";
  if (action.risk === "dangerous") return "border-amber-500/35";
  return "border-border/80";
}

function ActionIcon({ action }: { action: AssistantAction }) {
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
      <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-muted-foreground">
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
          <div className="truncate text-[11px] font-medium text-muted-foreground">{humanizeKey(key, lang)}</div>
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
        <span className="text-[11px] text-muted-foreground">{items.length}</span>
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
                        <span key={item} className="rounded-md border border-border/60 bg-secondary/50 px-1.5 py-0.5 text-[10px] text-muted-foreground">
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

function ActionResultPreview({ action }: { action: AssistantAction }) {
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

function ActionInputPreview({ action }: { action: AssistantAction }) {
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

function mergeTurnIntoChat(previous: AssistantChatSession | undefined, turn: AssistantChatTurnResponse): AssistantChatSession {
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

function replaceActionInChat(previous: AssistantChatSession | undefined, action: AssistantAction): AssistantChatSession | undefined {
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

function ActionCard({
  action,
  isWorking,
  onConfirm,
  onCancel,
}: {
  action: AssistantAction;
  isWorking: boolean;
  onConfirm: (actionId: number) => void;
  onCancel: (actionId: number) => void;
}) {
  const { lang } = useI18n();
  const canConfirm = action.status === "requires_confirmation";
  const canCancel = action.status === "requires_confirmation" || action.status === "proposed";

  return (
    <div className={cn("rounded-lg border bg-card/55 shadow-sm", actionTone(action))}>
      <div className="flex min-w-0 items-start gap-3 px-3 py-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-background/65">
          <ActionIcon action={action} />
        </div>
        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <h3 className="truncate text-sm font-semibold text-foreground">{action.title || action.action_type}</h3>
                <span className="truncate rounded-md border border-border/60 bg-background/45 px-2 py-0.5 font-mono text-[10px] text-muted-foreground">
                  {action.action_type}
                </span>
              </div>
              {action.description ? (
                <p className="mt-1 text-sm leading-5 text-muted-foreground">{action.description}</p>
              ) : null}
            </div>
            <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
              <Badge variant="outline" className={cn("rounded-md px-2 py-0.5", statusTone(action.status))}>
                {actionStatusLabel(action.status, lang)}
              </Badge>
              <Badge variant="secondary" className="rounded-md px-2 py-0.5">
                {actionRiskLabel(action.risk, lang)}
              </Badge>
            </div>
          </div>

          {canConfirm ? (
            <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
              {localize(lang, "Перед выполнением нужно подтверждение оператора.", "Operator confirmation is required before execution.")}
            </div>
          ) : null}

          <ActionInputPreview action={action} />

          {action.status === "completed" ? <ActionResultPreview action={action} /> : null}

          {action.error ? (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="min-w-0 break-words">{action.error}</span>
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            {canConfirm ? (
              <Button size="sm" onClick={() => onConfirm(action.id)} disabled={isWorking}>
                {isWorking ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                {localize(lang, "Подтвердить", "Confirm")}
              </Button>
            ) : null}
            {canCancel ? (
              <Button size="sm" variant="outline" onClick={() => onCancel(action.id)} disabled={isWorking}>
                <XCircle className="h-4 w-4" />
                {localize(lang, "Отменить", "Cancel")}
              </Button>
            ) : null}
            {action.target_url && action.status === "completed" ? (
              <Button size="sm" variant="secondary" asChild>
                <Link to={action.target_url}>
                  <ExternalLink className="h-4 w-4" />
                  {localize(lang, "Открыть", "Open")}
                </Link>
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  actionWorkingId,
  onConfirmAction,
  onCancelAction,
}: {
  message: AssistantChatMessage;
  actionWorkingId: number | null;
  onConfirmAction: (actionId: number) => void;
  onCancelAction: (actionId: number) => void;
}) {
  const { lang } = useI18n();
  const isUser = message.role === "user";
  const actions = message.metadata.actions || [];
  const Icon = isUser ? User : Bot;

  if (isUser) {
    return (
      <div className="flex justify-end gap-3">
        <div className="min-w-0 max-w-[min(720px,88%)]">
          <div className="rounded-lg bg-primary px-4 py-3 text-sm font-medium leading-6 text-primary-foreground shadow-sm">
            <div className="whitespace-pre-wrap break-words">{message.content}</div>
          </div>
          <div className="mt-1 text-right text-[11px] text-muted-foreground">{formatDateTime(message.created_at, lang)}</div>
        </div>
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border/75 bg-card/80 text-muted-foreground">
          <Icon className="h-4 w-4" />
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-[2rem_minmax(0,1fr)] gap-3">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <span className="font-semibold text-foreground">WebTermAI</span>
          <span>{formatDateTime(message.created_at, lang)}</span>
          {actions.length ? (
            <span className="rounded-md border border-border/60 bg-secondary/45 px-1.5 py-0.5">
              {actions.length} {localize(lang, "действ.", "actions")}
            </span>
          ) : null}
        </div>
        {message.content ? (
          <div className="max-w-[min(920px,100%)] rounded-lg border border-border/80 bg-card/75 px-4 py-3 text-sm leading-6 text-foreground shadow-sm">
            <div className="whitespace-pre-wrap break-words">{message.content}</div>
          </div>
        ) : null}
        {actions.length ? (
          <div className="max-w-[min(920px,100%)] space-y-2">
            {actions.map((action) => (
              <ActionCard
                key={action.id}
                action={action}
                isWorking={actionWorkingId === action.id}
                onConfirm={onConfirmAction}
                onCancel={onCancelAction}
              />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const { lang } = useI18n();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [draft, setDraft] = useState("");
  const [actionWorkingId, setActionWorkingId] = useState<number | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const activeChatId = Number(searchParams.get("chat") || 0) || null;

  const chatsQuery = useQuery({
    queryKey: ["assistant", "chats"],
    queryFn: fetchAssistantChats,
    staleTime: 20_000,
  });

  const activeChatQuery = useQuery({
    queryKey: ["assistant", "chat", activeChatId],
    queryFn: () => fetchAssistantChat(activeChatId as number),
    enabled: Boolean(activeChatId),
    staleTime: 10_000,
  });

  const chats = chatsQuery.data?.chats || [];
  const activeChat = activeChatQuery.data;
  const messages = activeChat?.messages || [];

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, activeChatId]);

  const sendMutation = useMutation({
    mutationFn: (message: string) => (
      activeChatId ? sendAssistantChatMessage(activeChatId, message) : startAssistantChat(message)
    ),
    onSuccess: (turn) => {
      queryClient.setQueryData<AssistantChatSession>(
        ["assistant", "chat", turn.chat.id],
        (previous) => mergeTurnIntoChat(previous, turn),
      );
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
      setSearchParams({ chat: String(turn.chat.id) });
      setDraft("");
    },
    onError: (error) => {
      toast({
        title: localize(lang, "Чат не ответил", "Chat failed"),
        description: error instanceof Error ? error.message : String(error),
        variant: "destructive",
      });
    },
  });

  const actionMutation = useMutation({
    mutationFn: ({ actionId, intent }: { actionId: number; intent: "confirm" | "cancel" }) => (
      intent === "confirm" ? confirmAssistantAction(actionId) : cancelAssistantAction(actionId)
    ),
    onMutate: ({ actionId }) => {
      setActionWorkingId(actionId);
    },
    onSuccess: (action) => {
      queryClient.setQueryData<AssistantChatSession | undefined>(
        ["assistant", "chat", action.chat_id],
        (previous) => replaceActionInChat(previous, action),
      );
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chat", action.chat_id] });
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
    },
    onError: (error) => {
      toast({
        title: localize(lang, "Действие не выполнено", "Action failed"),
        description: error instanceof Error ? error.message : String(error),
        variant: "destructive",
      });
    },
    onSettled: () => {
      setActionWorkingId(null);
    },
  });

  const isBusy = sendMutation.isPending;
  const selectedTitle = activeChat?.title || localize(lang, "Новый чат", "New chat");
  const prompts = QUICK_PROMPTS[lang];

  const submitMessage = () => {
    const text = draft.trim();
    if (!text || isBusy) return;
    sendMutation.mutate(text);
  };

  return (
    <div className="flex h-[calc(100vh-4rem)] min-h-[620px] bg-background md:h-screen">
      <aside className="hidden w-72 shrink-0 border-r border-border/70 bg-card/45 lg:flex lg:flex-col">
        <div className="flex h-16 items-center justify-between border-b border-border/70 px-4">
          <div className="min-w-0">
            <h1 className="truncate text-sm font-semibold text-foreground">{localize(lang, "Чат", "Chat")}</h1>
            <p className="truncate text-xs text-muted-foreground">WebTermAI</p>
          </div>
          <Button
            size="icon"
            variant="outline"
            onClick={() => setSearchParams({})}
            aria-label={localize(lang, "Новый чат", "New chat")}
            title={localize(lang, "Новый чат", "New chat")}
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {chatsQuery.isLoading ? (
            <div className="flex items-center gap-2 px-3 py-3 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {localize(lang, "Загрузка", "Loading")}
            </div>
          ) : null}
          {!chatsQuery.isLoading && !chats.length ? (
            <div className="rounded-lg border border-dashed border-border/70 px-3 py-6 text-center text-sm text-muted-foreground">
              {localize(lang, "История пуста", "No history")}
            </div>
          ) : null}
          {chats.map((chat) => {
            const selected = chat.id === activeChatId;
            return (
              <button
                key={chat.id}
                type="button"
                onClick={() => setSearchParams({ chat: String(chat.id) })}
                className={cn(
                  "mb-1 grid w-full min-w-0 grid-cols-[1rem_minmax(0,1fr)] gap-2 rounded-lg px-3 py-2.5 text-left transition-colors",
                  selected
                    ? "bg-secondary/70 text-foreground shadow-[inset_0_0_0_1px_hsl(var(--border))]"
                    : "text-muted-foreground hover:bg-secondary/45 hover:text-foreground",
                )}
              >
                <MessageSquare className="mt-0.5 h-4 w-4 shrink-0" />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">{chat.title}</span>
                  <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                    {formatDateTime(chat.updated_at, lang)}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-border/70 bg-card/55 px-4 backdrop-blur">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-foreground">{selectedTitle}</h2>
            <p className="truncate text-xs text-muted-foreground">
              {localize(lang, "Ассистент платформы", "Platform assistant")}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="hidden rounded-md border-primary/25 bg-primary/10 text-primary sm:inline-flex">
              <Workflow className="mr-1 h-3 w-3" />
              {localize(lang, "Действия", "Actions")}
            </Badge>
            <Button size="sm" variant="outline" className="lg:hidden" onClick={() => setSearchParams({})}>
              <Plus className="h-4 w-4" />
              {localize(lang, "Новый", "New")}
            </Button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-5">
            {!messages.length && !activeChatQuery.isLoading ? (
              <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 pt-[12vh]">
                <div className="flex items-start gap-3 rounded-lg border border-border/80 bg-card/70 p-4 shadow-sm">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
                    <Bot className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <h2 className="text-base font-semibold text-foreground">
                      {localize(lang, "Новый рабочий чат", "New working chat")}
                    </h2>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {prompts.map((prompt) => (
                        <button
                          key={prompt}
                          type="button"
                          onClick={() => setDraft(prompt)}
                          className="rounded-lg border border-border/70 bg-background/55 px-3 py-2 text-left text-xs font-medium text-muted-foreground transition-colors hover:border-primary/35 hover:text-foreground"
                        >
                          {prompt}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            {activeChatQuery.isLoading ? (
              <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {localize(lang, "Загрузка чата", "Loading chat")}
              </div>
            ) : null}

            {messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                actionWorkingId={actionWorkingId}
                onConfirmAction={(actionId) => actionMutation.mutate({ actionId, intent: "confirm" })}
                onCancelAction={(actionId) => actionMutation.mutate({ actionId, intent: "cancel" })}
              />
            ))}

            {isBusy ? (
              <div className="grid grid-cols-[2rem_minmax(0,1fr)] gap-3 text-sm text-muted-foreground">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-primary">
                  <Loader2 className="h-4 w-4 animate-spin" />
                </div>
                <div className="flex h-8 items-center">{localize(lang, "Думаю", "Thinking")}</div>
              </div>
            ) : null}
            <div ref={endRef} />
          </div>
        </div>

        <form
          className="shrink-0 border-t border-border/70 bg-card/70 px-4 py-3 backdrop-blur"
          onSubmit={(event) => {
            event.preventDefault();
            submitMessage();
          }}
        >
          <div className="mx-auto flex max-w-6xl items-end gap-2">
            <Textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder={localize(lang, "Напишите задачу для ассистента...", "Write a task for the assistant...")}
              className="max-h-40 min-h-12 resize-none border-border/80 bg-background/85 text-sm"
              disabled={isBusy}
            />
            <Button
              type="submit"
              size="icon"
              className="h-12 w-12 shrink-0"
              disabled={!draft.trim() || isBusy}
              aria-label={localize(lang, "Отправить", "Send")}
              title={localize(lang, "Отправить", "Send")}
            >
              {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
        </form>
      </section>
    </div>
  );
}
