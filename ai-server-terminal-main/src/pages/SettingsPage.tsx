// @ts-nocheck
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bot,
  Activity,
  Users,
  Shield,
  FolderOpen,
  RefreshCw,
  Save,
  Search,
  ChevronRight,
  Cpu,
  Key,
  Globe,
  ScrollText,
  Eye,
  Terminal,
  MessageSquare,
  Workflow,
  Database,
  ToggleLeft,
  ToggleRight,
  FileText,
  Clock,
  CalendarIcon,
} from "lucide-react";
import { format, subDays, startOfDay, endOfDay } from "date-fns";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchModels,
  fetchSettings,
  fetchSettingsActivity,
  refreshModels,
  saveSettings,
  fetchAuthSession,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

function relativeTime(value: string): string {
  const d = new Date(value);
  const diff = Math.max(1, Math.floor((Date.now() - d.getTime()) / 60000));
  if (diff < 60) return `${diff}m ago`;
  if (diff < 1440) return `${Math.floor(diff / 60)}h ago`;
  return `${Math.floor(diff / 1440)}d ago`;
}

function SectionCard({ title, icon: Icon, children, description, actions }: {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-border bg-secondary/20">
        <div className="flex items-center gap-2.5">
          <div className="h-7 w-7 rounded-lg bg-primary/10 flex items-center justify-center">
            <Icon className="h-3.5 w-3.5 text-primary" />
          </div>
          <div>
            <h2 className="text-sm font-medium text-foreground">{title}</h2>
            {description && <p className="text-[10px] text-muted-foreground mt-0.5">{description}</p>}
          </div>
        </div>
        {actions}
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

const LLM_PROVIDERS = [
  { value: "grok", label: "Grok (xAI)" },
  { value: "gemini", label: "Gemini (Google)" },
  { value: "openai", label: "OpenAI" },
  { value: "claude", label: "Claude (Anthropic)" },
];

const AUTO_REASONING_VALUE = "__auto__";

function PurposeModelSelector({
  label, description, icon: Icon, provider, model, availableModels,
  onProviderChange, onModelChange, onRefresh, refreshing,
}: {
  label: string; description: string; icon: React.ElementType;
  provider: string; model: string; availableModels: string[];
  onProviderChange: (p: string) => void; onModelChange: (m: string) => void;
  onRefresh: () => void; refreshing: boolean;
}) {
  return (
    <div className="rounded-lg border border-border p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-primary" />
        <div>
          <p className="text-xs font-medium text-foreground">{label}</p>
          <p className="text-[10px] text-muted-foreground">{description}</p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <label className="text-[10px] font-medium text-muted-foreground uppercase">Провайдер</label>
          <Select value={provider} onValueChange={onProviderChange}>
            <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              {LLM_PROVIDERS.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <label className="text-[10px] font-medium text-muted-foreground uppercase">Модель</label>
          {availableModels.length > 0 ? (
            <Select value={model} onValueChange={onModelChange}>
              <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                {availableModels.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
              </SelectContent>
            </Select>
          ) : (
            <div className="flex gap-1.5">
              <Input value={model} onChange={(e) => onModelChange(e.target.value)} placeholder="Model name" className="h-8 text-xs" />
              <Button size="icon" variant="outline" className="h-8 w-8 shrink-0" onClick={onRefresh} disabled={refreshing}>
                <RefreshCw className={cn("h-3 w-3", refreshing && "animate-spin")} />
              </Button>
            </div>
          )}
        </div>
      </div>
      {availableModels.length > 0 && (
        <Button size="sm" variant="ghost" className="h-5 text-[9px] px-1.5 gap-1 text-muted-foreground" onClick={onRefresh} disabled={refreshing}>
          <RefreshCw className={cn("h-2.5 w-2.5", refreshing && "animate-spin")} /> Обновить список
        </Button>
      )}
    </div>
  );
}

// Activity category icons
const CATEGORY_ICONS: Record<string, React.ElementType> = {
  terminal: Terminal,
  ai: Bot,
  agent: Bot,
  pipeline: Workflow,
  auth: Shield,
  server: Database,
  settings: Key,
};

const DATE_PRESETS = [
  { label: "Сегодня", days: 0 },
  { label: "Вчера", days: 1 },
  { label: "7 дней", days: 7 },
  { label: "14 дней", days: 14 },
  { label: "30 дней", days: 30 },
];

// Logging config (stored in localStorage as the backend API may not support it yet)
const DEFAULT_LOGGING_CONFIG = {
  log_terminal_commands: true,
  log_ai_assistant: true,
  log_agent_runs: true,
  log_pipeline_runs: true,
  log_auth_events: true,
  log_server_changes: true,
  log_settings_changes: true,
  log_file_operations: false,
  log_mcp_calls: true,
  retention_days: 90,
  export_format: "json",
};

function getLoggingConfig() {
  try {
    const stored = localStorage.getItem("weu_logging_config");
    if (stored) return { ...DEFAULT_LOGGING_CONFIG, ...JSON.parse(stored) };
  } catch {}
  return { ...DEFAULT_LOGGING_CONFIG };
}

function saveLoggingConfig(config: Record<string, unknown>) {
  localStorage.setItem("weu_logging_config", JSON.stringify(config));
}

export default function SettingsPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);

  const { data: authData } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const isAdmin = authData?.user?.is_staff ?? false;

  const { data: settingsData, isLoading: settingsLoading, error: settingsError } = useQuery({
    queryKey: ["settings", "config"],
    queryFn: fetchSettings,
    staleTime: 30_000,
  });

  const { data: modelsData } = useQuery({
    queryKey: ["settings", "models"],
    queryFn: fetchModels,
    staleTime: 30_000,
  });

  // Activity with date range
  const [activitySearch, setActivitySearch] = useState("");
  const [activityDays, setActivityDays] = useState(7);
  const [dateFrom, setDateFrom] = useState<Date | undefined>(subDays(new Date(), 7));
  const [dateTo, setDateTo] = useState<Date | undefined>(new Date());

  const computedDays = useMemo(() => {
    if (dateFrom && dateTo) {
      return Math.max(1, Math.ceil((dateTo.getTime() - dateFrom.getTime()) / 86400000));
    }
    return activityDays;
  }, [dateFrom, dateTo, activityDays]);

  const { data: activityData } = useQuery({
    queryKey: ["settings", "activity", computedDays],
    queryFn: () => fetchSettingsActivity(200, computedDays),
    staleTime: 20_000,
  });

  // AI model state
  const [provider, setProvider] = useState<string>("grok");
  const [model, setModel] = useState<string>("");
  const [chatProvider, setChatProvider] = useState("grok");
  const [chatModel, setChatModel] = useState("");
  const [agentProvider, setAgentProvider] = useState("grok");
  const [agentModel, setAgentModel] = useState("");
  const [orchProvider, setOrchProvider] = useState("grok");
  const [orchModel, setOrchModel] = useState("");
  const [refreshingPurpose, setRefreshingPurpose] = useState<string | null>(null);
  const [reasoningEffort, setReasoningEffort] = useState<string>(AUTO_REASONING_VALUE);
  const [refreshing, setRefreshing] = useState(false);

  // Logging config state
  const [loggingConfig, setLoggingConfig] = useState(getLoggingConfig);
  const [loggingSaved, setLoggingSaved] = useState(false);

  useEffect(() => {
    const config = settingsData?.config;
    if (!config) return;
    const llmProviders = ["gemini", "grok", "openai", "claude"];
    const activeProvider = llmProviders.includes(config.internal_llm_provider || "")
      ? config.internal_llm_provider
      : llmProviders.includes(config.default_provider || "")
        ? config.default_provider
        : "grok";
    setProvider(activeProvider);
    if (activeProvider === "gemini") setModel(config.chat_model_gemini || "");
    else if (activeProvider === "openai") setModel(config.chat_model_openai || "");
    else if (activeProvider === "claude") setModel(config.chat_model_claude || "");
    else setModel(config.chat_model_grok || "");

    setChatProvider(config.chat_llm_provider || activeProvider);
    setChatModel(config.chat_llm_model || "");
    setAgentProvider(config.agent_llm_provider || activeProvider);
    setAgentModel(config.agent_llm_model || "");
    setOrchProvider(config.orchestrator_llm_provider || activeProvider);
    setOrchModel(config.orchestrator_llm_model || "");
    setReasoningEffort(config.openai_reasoning_effort || AUTO_REASONING_VALUE);
  }, [settingsData]);

  const getModelsForProvider = (p: string): string[] => {
    if (!modelsData) return [];
    if (p === "gemini") return modelsData.gemini || [];
    if (p === "openai") return modelsData.openai || [];
    if (p === "claude") return modelsData.claude || [];
    return modelsData.grok || [];
  };

  const availableModels = useMemo(() => getModelsForProvider(provider), [modelsData, provider]);

  const onRefreshPurpose = async (p: string) => {
    setRefreshingPurpose(p);
    try {
      await refreshModels(p as "gemini" | "grok" | "openai" | "claude");
      await queryClient.invalidateQueries({ queryKey: ["settings", "models"] });
    } finally { setRefreshingPurpose(null); }
  };

  const onSavePurpose = async () => {
    setSaving(true);
    try {
      await saveSettings({
        chat_llm_provider: chatProvider, chat_llm_model: chatModel,
        agent_llm_provider: agentProvider, agent_llm_model: agentModel,
        orchestrator_llm_provider: orchProvider, orchestrator_llm_model: orchModel,
        internal_llm_provider: chatProvider,
        openai_reasoning_effort: reasoningEffort === AUTO_REASONING_VALUE ? "" : reasoningEffort,
      });
      await queryClient.invalidateQueries({ queryKey: ["settings", "config"] });
    } finally { setSaving(false); }
  };

  const onSave = async () => {
    setSaving(true);
    try {
      const llmProviders = ["gemini", "grok", "openai", "claude"];
      const isLlmProvider = llmProviders.includes(provider);
      const payload: Record<string, unknown> = { default_provider: provider };
      if (provider === "gemini") payload.chat_model_gemini = model;
      if (provider === "grok") payload.chat_model_grok = model;
      if (provider === "openai") payload.chat_model_openai = model;
      if (provider === "claude") payload.chat_model_claude = model;
      if (isLlmProvider) {
        payload.internal_llm_provider = provider;
        payload.gemini_enabled = provider === "gemini";
        payload.grok_enabled = provider === "grok";
        payload.openai_enabled = provider === "openai";
        payload.claude_enabled = provider === "claude";
      }
      await saveSettings(payload);
      await queryClient.invalidateQueries({ queryKey: ["settings", "config"] });
    } finally { setSaving(false); }
  };

  const onRefreshModels = async () => {
    setRefreshing(true);
    try {
      await refreshModels(provider as "gemini" | "grok" | "openai" | "claude");
      await queryClient.invalidateQueries({ queryKey: ["settings", "models"] });
    } finally { setRefreshing(false); }
  };

  const updateLogging = (key: string, val: unknown) => {
    const next = { ...loggingConfig, [key]: val };
    setLoggingConfig(next);
    setLoggingSaved(false);
  };

  const handleSaveLogging = () => {
    saveLoggingConfig(loggingConfig);
    setLoggingSaved(true);
    setTimeout(() => setLoggingSaved(false), 2000);
  };

  const filteredActivity = useMemo(() => {
    const events = activityData?.events || [];
    let filtered = events;
    if (activitySearch) {
      const q = activitySearch.toLowerCase();
      filtered = events.filter(
        (e) =>
          e.username?.toLowerCase().includes(q) ||
          e.action?.toLowerCase().includes(q) ||
          (e.description || "").toLowerCase().includes(q) ||
          e.category?.toLowerCase().includes(q),
      );
    }
    // Filter by date range
    if (dateFrom) {
      const from = startOfDay(dateFrom).getTime();
      filtered = filtered.filter((e) => new Date(e.timestamp || e.created_at || "").getTime() >= from);
    }
    if (dateTo) {
      const to = endOfDay(dateTo).getTime();
      filtered = filtered.filter((e) => new Date(e.timestamp || e.created_at || "").getTime() <= to);
    }
    return filtered;
  }, [activityData, activitySearch, dateFrom, dateTo]);

  if (settingsLoading) {
    return <div className="p-6 text-sm text-muted-foreground">{t("loading")}</div>;
  }
  if (settingsError || !settingsData?.success) {
    return <div className="p-6 text-sm text-destructive">{t("set.error")}</div>;
  }

  const config = settingsData.config;
  const apiKeys = settingsData.api_keys as Record<string, boolean> | undefined;

  const LOGGING_ITEMS = [
    { key: "log_terminal_commands", label: "Команды терминала", desc: "Записывать все SSH-команды пользователей", icon: Terminal },
    { key: "log_ai_assistant", label: "AI ассистент", desc: "Записывать запросы и ответы AI помощника", icon: MessageSquare },
    { key: "log_agent_runs", label: "Запуски агентов", desc: "Логировать все действия и итерации агентов", icon: Bot },
    { key: "log_pipeline_runs", label: "Pipeline запуски", desc: "Логировать выполнение pipeline и результаты", icon: Workflow },
    { key: "log_auth_events", label: "Авторизация", desc: "Входы, выходы, неудачные попытки", icon: Shield },
    { key: "log_server_changes", label: "Изменения серверов", desc: "Создание, обновление, удаление серверов", icon: Database },
    { key: "log_settings_changes", label: "Изменения настроек", desc: "Любые изменения в конфигурации платформы", icon: Key },
    { key: "log_mcp_calls", label: "MCP вызовы", desc: "Все вызовы к MCP серверам и инструментам", icon: Cpu },
    { key: "log_file_operations", label: "Файловые операции", desc: "Загрузки, скачивания и изменения файлов", icon: FileText },
  ];

  return (
    <div className="p-5 max-w-5xl mx-auto space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-foreground">{t("settings.title")}</h1>
        <p className="text-xs text-muted-foreground mt-0.5">Управление платформой, моделями, доступом и аудитом</p>
      </div>

      <Tabs defaultValue="ai" className="space-y-4">
        <TabsList className="w-full justify-start bg-secondary/30 p-1 flex-wrap">
          <TabsTrigger value="ai" className="gap-1.5 data-[state=active]:bg-card">
            <Bot className="h-3.5 w-3.5" /> AI модели
          </TabsTrigger>
          <TabsTrigger value="access" className="gap-1.5 data-[state=active]:bg-card">
            <Shield className="h-3.5 w-3.5" /> Доступ
          </TabsTrigger>
          {isAdmin && (
            <TabsTrigger value="logging" className="gap-1.5 data-[state=active]:bg-card">
              <ScrollText className="h-3.5 w-3.5" /> Логирование
            </TabsTrigger>
          )}
          <TabsTrigger value="activity" className="gap-1.5 data-[state=active]:bg-card">
            <Activity className="h-3.5 w-3.5" /> Журнал
          </TabsTrigger>
        </TabsList>

        {/* ==================== AI TAB ==================== */}
        <TabsContent value="ai" className="space-y-4">
          {/* Default model */}
          <SectionCard title="Основная модель" icon={Bot} description="Модель по умолчанию для всех задач">
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-[10px] font-medium text-muted-foreground uppercase">Провайдер</label>
                  <Select value={provider} onValueChange={setProvider}>
                    <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {LLM_PROVIDERS.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <label className="text-[10px] font-medium text-muted-foreground uppercase">Модель</label>
                  {availableModels.length > 0 ? (
                    <Select value={model} onValueChange={setModel}>
                      <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {availableModels.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  ) : (
                    <div className="flex gap-2">
                      <Input value={model} onChange={(e) => setModel(e.target.value)} placeholder="Model name" className="h-9" />
                      <Button size="sm" variant="outline" className="h-9 px-3" onClick={onRefreshModels} disabled={refreshing}>
                        <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
                      </Button>
                    </div>
                  )}
                </div>
              </div>
              <div className="flex gap-2">
                <Button size="sm" className="gap-1.5" onClick={onSave} disabled={saving}>
                  <Save className="h-3.5 w-3.5" /> {saving ? "Сохранение..." : "Сохранить"}
                </Button>
                {availableModels.length > 0 && (
                  <Button size="sm" variant="outline" className="gap-1.5" onClick={onRefreshModels} disabled={refreshing}>
                    <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} /> Обновить модели
                  </Button>
                )}
              </div>
            </div>
          </SectionCard>

          {/* Purpose-based models */}
          <SectionCard title="Модели по назначению" icon={Cpu} description="Отдельные модели для разных задач платформы">
            <div className="space-y-3">
              <PurposeModelSelector
                label="Чат / Терминальный AI" description="AI помощник в терминале" icon={MessageSquare}
                provider={chatProvider} model={chatModel} availableModels={getModelsForProvider(chatProvider)}
                onProviderChange={(p) => { setChatProvider(p); setChatModel(""); }}
                onModelChange={setChatModel} onRefresh={() => onRefreshPurpose(chatProvider)}
                refreshing={refreshingPurpose === chatProvider}
              />
              <PurposeModelSelector
                label="Агенты (ReAct)" description="Выполнение задач с инструментами" icon={Bot}
                provider={agentProvider} model={agentModel} availableModels={getModelsForProvider(agentProvider)}
                onProviderChange={(p) => { setAgentProvider(p); setAgentModel(""); }}
                onModelChange={setAgentModel} onRefresh={() => onRefreshPurpose(agentProvider)}
                refreshing={refreshingPurpose === agentProvider}
              />
              <PurposeModelSelector
                label="Оркестратор (Pipeline)" description="Планирование в мультиагентных пайплайнах" icon={Workflow}
                provider={orchProvider} model={orchModel} availableModels={getModelsForProvider(orchProvider)}
                onProviderChange={(p) => { setOrchProvider(p); setOrchModel(""); }}
                onModelChange={setOrchModel} onRefresh={() => onRefreshPurpose(orchProvider)}
                refreshing={refreshingPurpose === orchProvider}
              />

              {/* Reasoning effort */}
              <div className="rounded-lg border border-border p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs font-medium">OpenAI Reasoning Effort</p>
                    <p className="text-[10px] text-muted-foreground">Глубина reasoning в Responses API</p>
                  </div>
                  <Select value={reasoningEffort} onValueChange={setReasoningEffort}>
                    <SelectTrigger className="h-8 w-36 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={AUTO_REASONING_VALUE}>Auto</SelectItem>
                      <SelectItem value="none">None ⚡⚡</SelectItem>
                      <SelectItem value="low">Low ⚡</SelectItem>
                      <SelectItem value="medium">Medium ⚖️</SelectItem>
                      <SelectItem value="high">High 🔬</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Button size="sm" className="gap-1.5" onClick={onSavePurpose} disabled={saving}>
                <Save className="h-3.5 w-3.5" /> {saving ? "Сохранение..." : "Сохранить модели"}
              </Button>
            </div>
          </SectionCard>

          {/* API Keys status */}
          {apiKeys && isAdmin && (
            <SectionCard title="API ключи" icon={Key} description="Статус подключения провайдеров">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { name: "Gemini", key: "gemini_set", enabled: config.gemini_enabled },
                  { name: "Grok", key: "grok_set", enabled: config.grok_enabled },
                  { name: "OpenAI", key: "openai_set", enabled: config.openai_enabled },
                  { name: "Claude", key: "claude_set", enabled: config.claude_enabled },
                ].map((p) => (
                  <div key={p.name} className="flex items-center gap-3 rounded-lg border border-border px-3 py-3">
                    <div className={cn("h-2.5 w-2.5 rounded-full", apiKeys[p.key] ? "bg-green-500" : "bg-red-500")} />
                    <div>
                      <p className="text-xs font-medium">{p.name}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {apiKeys[p.key] ? "Подключен" : "Не задан"}
                        {p.enabled ? " · Активен" : ""}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </SectionCard>
          )}

          {/* Domain auth */}
          {isAdmin && config.domain_auth_enabled !== undefined && (
            <SectionCard title="Доменная авторизация" icon={Globe} description="SSO через HTTP-заголовок">
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-lg border border-border px-3 py-2.5">
                  <p className="text-[10px] text-muted-foreground uppercase">Статус</p>
                  <p className="text-sm font-medium">{config.domain_auth_enabled ? "Включен" : "Выключен"}</p>
                </div>
                <div className="rounded-lg border border-border px-3 py-2.5">
                  <p className="text-[10px] text-muted-foreground uppercase">Header</p>
                  <p className="text-sm font-mono">{config.domain_auth_header || "REMOTE_USER"}</p>
                </div>
                <div className="rounded-lg border border-border px-3 py-2.5">
                  <p className="text-[10px] text-muted-foreground uppercase">Авто-создание</p>
                  <p className="text-sm font-medium">{config.domain_auth_auto_create ? "Да" : "Нет"}</p>
                </div>
              </div>
            </SectionCard>
          )}
        </TabsContent>

        {/* ==================== ACCESS TAB ==================== */}
        <TabsContent value="access">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              { title: "Пользователи", desc: "Управление аккаунтами и ролями", icon: Users, url: "/settings/users" },
              { title: "Группы", desc: "Группы серверов и доступ", icon: FolderOpen, url: "/settings/groups" },
              { title: "Разрешения", desc: "Политики доступа к модулям", icon: Shield, url: "/settings/permissions" },
            ].map((page) => (
              <Link
                key={page.url}
                to={page.url}
                className="flex items-center gap-4 bg-card border border-border rounded-lg p-5 hover:border-primary/30 hover:bg-primary/5 transition-all group"
              >
                <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                  <page.icon className="h-5 w-5 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium group-hover:text-primary transition-colors">{page.title}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{page.desc}</p>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
              </Link>
            ))}
          </div>
        </TabsContent>

        {/* ==================== LOGGING TAB ==================== */}
        {isAdmin && (
          <TabsContent value="logging" className="space-y-4">
            <SectionCard
              title="Настройки логирования"
              icon={ScrollText}
              description="Выберите какие действия пользователей записывать в журнал"
              actions={
                <Button size="sm" className="gap-1.5 h-7" onClick={handleSaveLogging}>
                  <Save className="h-3 w-3" />
                  {loggingSaved ? "✓ Сохранено" : "Сохранить"}
                </Button>
              }
            >
              <div className="space-y-1">
                {LOGGING_ITEMS.map((item) => {
                  const Icon = item.icon;
                  const enabled = loggingConfig[item.key];
                  return (
                    <label
                      key={item.key}
                      className="flex items-center gap-3 rounded-lg px-3 py-3 hover:bg-muted/30 transition-colors cursor-pointer"
                    >
                      <div className={cn(
                        "h-8 w-8 rounded-lg flex items-center justify-center shrink-0 transition-colors",
                        enabled ? "bg-primary/10" : "bg-muted/50"
                      )}>
                        <Icon className={cn("h-4 w-4", enabled ? "text-primary" : "text-muted-foreground")} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium">{item.label}</p>
                        <p className="text-[10px] text-muted-foreground">{item.desc}</p>
                      </div>
                      <Switch
                        checked={enabled}
                        onCheckedChange={(v) => updateLogging(item.key, v)}
                      />
                    </label>
                  );
                })}
              </div>
            </SectionCard>

            <SectionCard title="Хранение и экспорт" icon={Database} description="Настройки ротации и формата логов">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-xs">Хранить логи (дней)</Label>
                  <Select
                    value={String(loggingConfig.retention_days)}
                    onValueChange={(v) => updateLogging("retention_days", Number(v))}
                  >
                    <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="30">30 дней</SelectItem>
                      <SelectItem value="60">60 дней</SelectItem>
                      <SelectItem value="90">90 дней</SelectItem>
                      <SelectItem value="180">180 дней</SelectItem>
                      <SelectItem value="365">1 год</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Формат экспорта</Label>
                  <Select
                    value={loggingConfig.export_format}
                    onValueChange={(v) => updateLogging("export_format", v)}
                  >
                    <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="json">JSON</SelectItem>
                      <SelectItem value="csv">CSV</SelectItem>
                      <SelectItem value="syslog">Syslog</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="mt-4 rounded-lg border border-border bg-muted/20 px-4 py-3">
                <p className="text-[11px] text-muted-foreground">
                  Логи хранятся на сервере в таблице <code className="text-foreground">core_ui_useractivitylog</code>.
                  При превышении срока хранения старые записи автоматически удаляются.
                  Экспорт доступен через API: <code className="text-foreground">GET /api/settings/activity/?format=json&days=30</code>
                </p>
              </div>
            </SectionCard>

            {/* Summary of active logging */}
            <div className="rounded-lg border border-border bg-card px-5 py-4">
              <div className="flex items-center gap-2 mb-3">
                <Eye className="h-4 w-4 text-primary" />
                <span className="text-xs font-medium">Активные категории</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {LOGGING_ITEMS.filter((i) => loggingConfig[i.key]).map((i) => (
                  <Badge key={i.key} variant="secondary" className="text-[10px] gap-1">
                    <i.icon className="h-2.5 w-2.5" /> {i.label}
                  </Badge>
                ))}
                {LOGGING_ITEMS.every((i) => !loggingConfig[i.key]) && (
                  <p className="text-[11px] text-muted-foreground">Все категории отключены</p>
                )}
              </div>
            </div>
          </TabsContent>
        )}

        {/* ==================== ACTIVITY TAB ==================== */}
        <TabsContent value="activity" className="space-y-4">
          <SectionCard title="Журнал действий" icon={Activity} description="Полная история действий пользователей на платформе">
            <div className="space-y-4">
              {/* Filters */}
              <div className="flex flex-wrap items-center gap-3">
                <div className="relative flex-1 min-w-[200px] max-w-sm">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    value={activitySearch}
                    onChange={(e) => setActivitySearch(e.target.value)}
                    placeholder="Поиск по пользователю, действию..."
                    className="pl-9 h-8 text-xs"
                  />
                </div>

                {/* Date presets */}
                <div className="flex items-center gap-1">
                  {DATE_PRESETS.map((preset) => (
                    <Button
                      key={preset.days}
                      size="sm"
                      variant={activityDays === preset.days ? "default" : "outline"}
                      className="h-7 text-[10px] px-2"
                      onClick={() => {
                        setActivityDays(preset.days);
                        setDateFrom(subDays(new Date(), preset.days || 0));
                        setDateTo(new Date());
                      }}
                    >
                      {preset.label}
                    </Button>
                  ))}
                </div>

                {/* Date range pickers */}
                <div className="flex items-center gap-1.5">
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button variant="outline" size="sm" className="h-7 text-[10px] gap-1 px-2">
                        <CalendarIcon className="h-3 w-3" />
                        {dateFrom ? format(dateFrom, "dd.MM.yy") : "От"}
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                      <Calendar
                        mode="single"
                        selected={dateFrom}
                        onSelect={setDateFrom}
                        disabled={(date) => date > new Date()}
                        className="p-3 pointer-events-auto"
                      />
                    </PopoverContent>
                  </Popover>
                  <span className="text-[10px] text-muted-foreground">—</span>
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button variant="outline" size="sm" className="h-7 text-[10px] gap-1 px-2">
                        <CalendarIcon className="h-3 w-3" />
                        {dateTo ? format(dateTo, "dd.MM.yy") : "До"}
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                      <Calendar
                        mode="single"
                        selected={dateTo}
                        onSelect={setDateTo}
                        disabled={(date) => date > new Date()}
                        className="p-3 pointer-events-auto"
                      />
                    </PopoverContent>
                  </Popover>
                </div>

                <Badge variant="outline" className="text-[10px] shrink-0">
                  {filteredActivity.length} записей
                </Badge>
              </div>

              {/* Activity table */}
              <div className="rounded-lg border border-border overflow-hidden">
                <div className="max-h-[500px] overflow-auto">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-card z-10">
                      <tr className="text-[10px] text-muted-foreground uppercase border-b border-border">
                        <th className="px-3 py-2 text-left font-medium w-10">Тип</th>
                        <th className="px-3 py-2 text-left font-medium">Пользователь</th>
                        <th className="px-3 py-2 text-left font-medium">Действие</th>
                        <th className="px-3 py-2 text-left font-medium">Описание</th>
                        <th className="px-3 py-2 text-right font-medium w-20">Время</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/50">
                      {filteredActivity.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                            Нет записей за выбранный период
                          </td>
                        </tr>
                      ) : (
                        filteredActivity.map((event, i) => {
                          const CatIcon = CATEGORY_ICONS[event.category] || Activity;
                          return (
                            <tr key={i} className="hover:bg-muted/20 transition-colors">
                              <td className="px-3 py-2">
                                <div className="h-6 w-6 rounded bg-muted/40 flex items-center justify-center">
                                  <CatIcon className="h-3 w-3 text-muted-foreground" />
                                </div>
                              </td>
                              <td className="px-3 py-2 font-medium text-foreground whitespace-nowrap">{event.username}</td>
                              <td className="px-3 py-2">
                                <Badge variant="outline" className="text-[9px] font-normal">{event.action}</Badge>
                              </td>
                              <td className="px-3 py-2 text-muted-foreground max-w-xs truncate">{event.description || "—"}</td>
                              <td className="px-3 py-2 text-right text-muted-foreground whitespace-nowrap">
                                {relativeTime(event.timestamp || event.created_at || "")}
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </SectionCard>
        </TabsContent>
      </Tabs>
    </div>
  );
}
