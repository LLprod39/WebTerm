import { useCallback, useEffect, useMemo, useState } from "react";
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
  type SettingsConfig,
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
  { value: "ollama", label: "Ollama" },
];

const AUTO_REASONING_VALUE = "__auto__";
const AUTO_OLLAMA_THINKING_VALUE = "__auto__";
const LLM_PROVIDER_VALUES = LLM_PROVIDERS.map((provider) => provider.value);
const OLLAMA_RUNTIME_OPTIONS = [
  { value: "auto", label: "Авто" },
  { value: "local", label: "Только локально" },
  { value: "cloud", label: "Только облако" },
];
const OLLAMA_THINKING_OPTIONS = [
  { value: AUTO_OLLAMA_THINKING_VALUE, label: "Авто" },
  { value: "off", label: "Выкл" },
  { value: "on", label: "Вкл" },
  { value: "low", label: "Низкий" },
  { value: "medium", label: "Средний" },
  { value: "high", label: "Высокий" },
];
const PROVIDER_API_STATUS_KEY: Record<string, string> = {
  gemini: "gemini_set",
  grok: "grok_set",
  openai: "openai_set",
  claude: "claude_set",
  ollama: "ollama_set",
};

function getProviderLabel(value: string): string {
  return LLM_PROVIDERS.find((provider) => provider.value === value)?.label || value;
}

function getProviderEnabled(config: SettingsConfig, provider: string): boolean {
  if (provider === "gemini") return config.gemini_enabled;
  if (provider === "openai") return config.openai_enabled;
  if (provider === "claude") return config.claude_enabled;
  if (provider === "ollama") return config.ollama_enabled;
  return config.grok_enabled;
}

function getSavedModelForProvider(config: SettingsConfig, provider: string): string {
  if (provider === "gemini") return config.chat_model_gemini || "";
  if (provider === "openai") return config.chat_model_openai || "";
  if (provider === "claude") return config.chat_model_claude || "";
  if (provider === "ollama") return config.chat_model_ollama || "";
  return config.chat_model_grok || "";
}

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
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
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
      <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] text-muted-foreground">
        <span>{getProviderLabel(provider)}</span>
        <span>{availableModels.length ? `${availableModels.length} моделей в каталоге` : "Ручной ввод модели"}</span>
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
  log_http_requests: true,
  retention_days: 90,
  export_format: "json",
};
const LOGGING_KEYS = Object.keys(DEFAULT_LOGGING_CONFIG);
type SettingsTabValue = "ai" | "access" | "logging" | "activity";

export default function SettingsPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<SettingsTabValue>("ai");

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
  const currentConfig = settingsData?.config;

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
    enabled: isAdmin,
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
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState("http://127.0.0.1:11434");
  const [ollamaRuntimeMode, setOllamaRuntimeMode] = useState("auto");
  const [ollamaCloudEnabled, setOllamaCloudEnabled] = useState(false);
  const [ollamaCloudBaseUrl, setOllamaCloudBaseUrl] = useState("https://ollama.com");
  const [ollamaThinkMode, setOllamaThinkMode] = useState<string>(AUTO_OLLAMA_THINKING_VALUE);
  const [refreshingPurpose, setRefreshingPurpose] = useState<string | null>(null);
  const [reasoningEffort, setReasoningEffort] = useState<string>(AUTO_REASONING_VALUE);
  const [refreshing, setRefreshing] = useState(false);

  // Logging config state
  const [loggingConfig, setLoggingConfig] = useState({ ...DEFAULT_LOGGING_CONFIG });
  const [loggingSaved, setLoggingSaved] = useState(false);

  const hydrateAiForm = useCallback((config: SettingsConfig) => {
    const activeProvider = LLM_PROVIDER_VALUES.includes(config.internal_llm_provider || "")
      ? config.internal_llm_provider
      : LLM_PROVIDER_VALUES.includes(config.default_provider || "")
        ? config.default_provider
        : "grok";
    setProvider(activeProvider);
    setModel(getSavedModelForProvider(config, activeProvider));
    setChatProvider(config.chat_llm_provider || activeProvider);
    setChatModel(config.chat_llm_model || "");
    setAgentProvider(config.agent_llm_provider || activeProvider);
    setAgentModel(config.agent_llm_model || "");
    setOrchProvider(config.orchestrator_llm_provider || activeProvider);
    setOrchModel(config.orchestrator_llm_model || "");
    setOllamaBaseUrl(config.ollama_base_url || "http://127.0.0.1:11434");
    setOllamaRuntimeMode(config.ollama_runtime_mode || "auto");
    setOllamaCloudEnabled(Boolean(config.ollama_cloud_enabled));
    setOllamaCloudBaseUrl(config.ollama_cloud_base_url || "https://ollama.com");
    setOllamaThinkMode(config.ollama_think_mode || AUTO_OLLAMA_THINKING_VALUE);
    setReasoningEffort(config.openai_reasoning_effort || AUTO_REASONING_VALUE);
    setLoggingConfig({
      ...DEFAULT_LOGGING_CONFIG,
      ...Object.fromEntries(LOGGING_KEYS.map((key) => [key, config[key] ?? DEFAULT_LOGGING_CONFIG[key]])),
    });
  }, []);

  useEffect(() => {
    if (!currentConfig) return;
    hydrateAiForm(currentConfig);
  }, [currentConfig, hydrateAiForm]);

  const getModelsForProvider = useCallback((p: string): string[] => {
    if (!modelsData) return [];
    if (p === "gemini") return modelsData.gemini || [];
    if (p === "openai") return modelsData.openai || [];
    if (p === "claude") return modelsData.claude || [];
    if (p === "ollama") {
      const localModels = modelsData.ollama_local || [];
      const cloudModels = modelsData.ollama_cloud || [];
      const ordered = ollamaRuntimeMode === "cloud"
        ? [...cloudModels, ...localModels]
        : [...localModels, ...cloudModels];
      return Array.from(new Set(ordered));
    }
    return modelsData.grok || [];
  }, [modelsData, ollamaRuntimeMode]);

  const availableModels = useMemo(() => getModelsForProvider(provider), [getModelsForProvider, provider]);
  const getSuggestedModelForProvider = useCallback((nextProvider: string, preferredModel = ""): string => {
    const models = getModelsForProvider(nextProvider);
    if (!models.length) {
      return preferredModel;
    }
    if (preferredModel && models.includes(preferredModel)) {
      return preferredModel;
    }
    if (currentConfig) {
      const savedModel = getSavedModelForProvider(currentConfig, nextProvider);
      if (savedModel && models.includes(savedModel)) {
        return savedModel;
      }
    }
    return models[0];
  }, [currentConfig, getModelsForProvider]);

  const handleDefaultProviderChange = useCallback((nextProvider: string) => {
    setProvider(nextProvider);
    setModel(getSuggestedModelForProvider(nextProvider));
  }, [getSuggestedModelForProvider]);

  const applyDefaultToAll = useCallback(() => {
    const nextModel = model || getSuggestedModelForProvider(provider);
    setChatProvider(provider);
    setChatModel(nextModel);
    setAgentProvider(provider);
    setAgentModel(nextModel);
    setOrchProvider(provider);
    setOrchModel(nextModel);
  }, [getSuggestedModelForProvider, model, provider]);

  const fillMissingModels = useCallback(() => {
    setModel((current) => current || getSuggestedModelForProvider(provider));
    setChatModel((current) => current || getSuggestedModelForProvider(chatProvider));
    setAgentModel((current) => current || getSuggestedModelForProvider(agentProvider));
    setOrchModel((current) => current || getSuggestedModelForProvider(orchProvider));
  }, [
    agentProvider,
    chatProvider,
    getSuggestedModelForProvider,
    orchProvider,
    provider,
  ]);

  const resetAiDraft = useCallback(() => {
    if (!currentConfig) return;
    hydrateAiForm(currentConfig);
  }, [currentConfig, hydrateAiForm]);

  const onRefreshPurpose = async (p: string) => {
    setRefreshingPurpose(p);
    try {
      await refreshModels(p as "gemini" | "grok" | "openai" | "claude" | "ollama");
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
        ollama_base_url: ollamaBaseUrl,
        ollama_runtime_mode: ollamaRuntimeMode,
        ollama_cloud_enabled: ollamaCloudEnabled,
        ollama_cloud_base_url: ollamaCloudBaseUrl,
        ollama_think_mode: ollamaThinkMode === AUTO_OLLAMA_THINKING_VALUE ? "" : ollamaThinkMode,
        openai_reasoning_effort: reasoningEffort === AUTO_REASONING_VALUE ? "" : reasoningEffort,
      });
      await queryClient.invalidateQueries({ queryKey: ["settings", "config"] });
    } finally { setSaving(false); }
  };

  const onSave = async () => {
    setSaving(true);
    try {
      const isLlmProvider = LLM_PROVIDER_VALUES.includes(provider);
      const payload: Record<string, unknown> = {
        default_provider: provider,
        ollama_base_url: ollamaBaseUrl,
        ollama_runtime_mode: ollamaRuntimeMode,
        ollama_cloud_enabled: ollamaCloudEnabled,
        ollama_cloud_base_url: ollamaCloudBaseUrl,
        ollama_think_mode: ollamaThinkMode === AUTO_OLLAMA_THINKING_VALUE ? "" : ollamaThinkMode,
      };
      if (provider === "gemini") payload.chat_model_gemini = model;
      if (provider === "grok") payload.chat_model_grok = model;
      if (provider === "openai") payload.chat_model_openai = model;
      if (provider === "claude") payload.chat_model_claude = model;
      if (provider === "ollama") payload.chat_model_ollama = model;
      if (isLlmProvider) {
        payload.internal_llm_provider = provider;
        payload.gemini_enabled = provider === "gemini";
        payload.grok_enabled = provider === "grok";
        payload.openai_enabled = provider === "openai";
        payload.claude_enabled = provider === "claude";
        payload.ollama_enabled = provider === "ollama";
      }
      await saveSettings(payload);
      await queryClient.invalidateQueries({ queryKey: ["settings", "config"] });
    } finally { setSaving(false); }
  };

  const onSaveOllama = async () => {
    setSaving(true);
    try {
      await saveSettings({
        ollama_base_url: ollamaBaseUrl,
        ollama_runtime_mode: ollamaRuntimeMode,
        ollama_cloud_enabled: ollamaCloudEnabled,
        ollama_cloud_base_url: ollamaCloudBaseUrl,
        ollama_think_mode: ollamaThinkMode === AUTO_OLLAMA_THINKING_VALUE ? "" : ollamaThinkMode,
        openai_reasoning_effort: reasoningEffort === AUTO_REASONING_VALUE ? "" : reasoningEffort,
      });
      await queryClient.invalidateQueries({ queryKey: ["settings", "config"] });
    } finally { setSaving(false); }
  };

  const onRefreshModels = async () => {
    setRefreshing(true);
    try {
      await refreshModels(provider as "gemini" | "grok" | "openai" | "claude" | "ollama");
      await queryClient.invalidateQueries({ queryKey: ["settings", "models"] });
    } finally { setRefreshing(false); }
  };

  const updateLogging = (key: string, val: unknown) => {
    const next = { ...loggingConfig, [key]: val };
    setLoggingConfig(next);
    setLoggingSaved(false);
  };

  const handleSaveLogging = async () => {
    setSaving(true);
    try {
      await saveSettings(Object.fromEntries(LOGGING_KEYS.map((key) => [key, loggingConfig[key]])));
      await queryClient.invalidateQueries({ queryKey: ["settings", "config"] });
      setLoggingSaved(true);
      setTimeout(() => setLoggingSaved(false), 2000);
    } finally {
      setSaving(false);
    }
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

  useEffect(() => {
    if (isAdmin) return;
    if (activeTab === "logging" || activeTab === "activity") {
      setActiveTab("ai");
    }
  }, [activeTab, isAdmin]);

  if (settingsLoading) {
    return <div className="p-6 text-sm text-muted-foreground">{t("loading")}</div>;
  }
  if (settingsError || !settingsData?.success) {
    return <div className="p-6 text-sm text-destructive">{t("set.error")}</div>;
  }

  const config = settingsData.config;
  const apiKeys = settingsData.api_keys as Record<string, boolean> | undefined;
  const savedActiveProvider = LLM_PROVIDER_VALUES.includes(config.internal_llm_provider || "")
    ? config.internal_llm_provider
    : LLM_PROVIDER_VALUES.includes(config.default_provider || "")
      ? config.default_provider
      : "grok";
  const routeConfigs = [
    {
      key: "chat",
      shortLabel: "Chat",
      label: "Чат / Терминальный AI",
      description: "Интерактивный помощник и терминальные подсказки",
      icon: MessageSquare,
      provider: chatProvider,
      model: chatModel,
    },
    {
      key: "agent",
      shortLabel: "Agent",
      label: "Агенты (ReAct)",
      description: "Длинные задачи, инструменты и итерации",
      icon: Bot,
      provider: agentProvider,
      model: agentModel,
    },
    {
      key: "orchestrator",
      shortLabel: "Pipeline",
      label: "Оркестратор (Pipeline)",
      description: "Планирование и координация пайплайнов",
      icon: Workflow,
      provider: orchProvider,
      model: orchModel,
    },
  ];
  const uniqueRouteProviders = Array.from(new Set(routeConfigs.map((route) => route.provider)));
  const ollamaLocalModels = modelsData?.ollama_local || [];
  const ollamaCloudModels = modelsData?.ollama_cloud || [];
  const ollamaCatalogModels = getModelsForProvider("ollama");
  const ollamaRoutingActive = provider === "ollama" || routeConfigs.some((route) => route.provider === "ollama");
  const ollamaRuntimeSummary =
    ollamaRuntimeMode === "cloud"
      ? "Только облако"
      : ollamaRuntimeMode === "local"
        ? "Только локально"
        : "Авто";
  const providerOverview = LLM_PROVIDERS.map((providerOption) => {
    const catalogSize = getModelsForProvider(providerOption.value).length;
    const activeRoutes = routeConfigs
      .filter((route) => route.provider === providerOption.value)
      .map((route) => route.shortLabel);
    const configured = providerOption.value === "ollama"
      ? Boolean(apiKeys?.[PROVIDER_API_STATUS_KEY[providerOption.value]])
      : Boolean(apiKeys?.[PROVIDER_API_STATUS_KEY[providerOption.value]]);
    return {
      ...providerOption,
      catalogSize,
      activeRoutes,
      enabled: getProviderEnabled(config, providerOption.value),
      configured,
      isSelected: provider === providerOption.value,
    };
  });
  const aiDraftDirty = (
    provider !== savedActiveProvider ||
    model !== getSavedModelForProvider(config, provider) ||
    chatProvider !== (config.chat_llm_provider || savedActiveProvider) ||
    chatModel !== (config.chat_llm_model || "") ||
    agentProvider !== (config.agent_llm_provider || savedActiveProvider) ||
    agentModel !== (config.agent_llm_model || "") ||
    orchProvider !== (config.orchestrator_llm_provider || savedActiveProvider) ||
    orchModel !== (config.orchestrator_llm_model || "") ||
    ollamaBaseUrl !== (config.ollama_base_url || "http://127.0.0.1:11434") ||
    ollamaRuntimeMode !== (config.ollama_runtime_mode || "auto") ||
    ollamaCloudEnabled !== Boolean(config.ollama_cloud_enabled) ||
    ollamaCloudBaseUrl !== (config.ollama_cloud_base_url || "https://ollama.com") ||
    ollamaThinkMode !== (config.ollama_think_mode || AUTO_OLLAMA_THINKING_VALUE) ||
    reasoningEffort !== (config.openai_reasoning_effort || AUTO_REASONING_VALUE)
  );
  const missingModelsCount = [model, ...routeConfigs.map((route) => route.model)].filter((value) => !value).length;
  const catalogSyncedCount = providerOverview.filter((providerItem) => providerItem.catalogSize > 0).length;
  const configuredProviderCount = providerOverview.filter((providerItem) => providerItem.configured).length;

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
    { key: "log_http_requests", label: "HTTP/API запросы", desc: "Логировать каждый web/API запрос пользователя", icon: Globe },
  ];
  const settingsTabs: Array<{
    value: SettingsTabValue;
    label: string;
    description: string;
    icon: React.ElementType;
    badge?: string;
  }> = [
    {
      value: "ai",
      label: "AI модели",
      description: "Провайдеры, роли, runtime и каталог моделей",
      icon: Bot,
      badge: aiDraftDirty ? "Черновик" : undefined,
    },
    {
      value: "access",
      label: "Доступ",
      description: "Пользователи, группы и права доступа",
      icon: Shield,
    },
    ...(isAdmin
      ? [
          {
            value: "logging" as const,
            label: "Логирование",
            description: "Аудит, retention и экспорт",
            icon: ScrollText,
          },
          {
            value: "activity" as const,
            label: "Журнал",
            description: "Последние действия и история событий",
            icon: Activity,
            badge: filteredActivity.length ? String(filteredActivity.length) : undefined,
          },
        ]
      : []),
  ];
  const activeTabMeta = settingsTabs.find((tab) => tab.value === activeTab) || settingsTabs[0];

  return (
    <div className="min-h-full w-full px-4 py-5 xl:px-6 2xl:px-8">
      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as SettingsTabValue)} className="space-y-5">
        <div className="mx-auto w-full max-w-[1520px] space-y-5">
          <div className="rounded-2xl border border-border bg-card px-5 py-5 shadow-sm lg:px-6">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
              <div className="space-y-1.5">
                <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-primary/80">Settings Workspace</p>
                <h1 className="text-2xl font-semibold text-foreground">{t("settings.title")}</h1>
                <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
                  Более широкий и спокойный layout без узкой центральной колонки и без перегруженной боковой навигации.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline">{activeTabMeta.label}</Badge>
                <Badge variant="secondary">{configuredProviderCount} настроено</Badge>
                <Badge variant="outline">Ollama {ollamaRuntimeSummary}</Badge>
                {aiDraftDirty ? <Badge>Есть черновик</Badge> : <Badge variant="secondary">Без несохраненных изменений</Badge>}
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-xl border border-border bg-background px-4 py-3">
                <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Раздел</p>
                <p className="mt-1 text-sm font-medium text-foreground">{activeTabMeta.label}</p>
                <p className="mt-1 text-[11px] text-muted-foreground">{activeTabMeta.description}</p>
              </div>
              <div className="rounded-xl border border-border bg-background px-4 py-3">
                <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Основная модель</p>
                <p className="mt-1 text-sm font-medium text-foreground">{getProviderLabel(provider)}</p>
                <p className="mt-1 text-[11px] text-muted-foreground">{model || "Модель не выбрана"}</p>
              </div>
              <div className="rounded-xl border border-border bg-background px-4 py-3">
                <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Маршруты</p>
                <p className="mt-1 text-sm font-medium text-foreground">{uniqueRouteProviders.length} провайдера</p>
                <p className="mt-1 text-[11px] text-muted-foreground">{routeConfigs.map((route) => route.shortLabel).join(" / ")}</p>
              </div>
              <div className="rounded-xl border border-border bg-background px-4 py-3">
                <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Ollama</p>
                <p className="mt-1 text-sm font-medium text-foreground">{ollamaCatalogModels.length} моделей</p>
                <p className="mt-1 text-[11px] text-muted-foreground">{ollamaLocalModels.length} local, {ollamaCloudModels.length} cloud</p>
              </div>
            </div>
          </div>

          <TabsList className="flex h-auto w-max min-w-full justify-start gap-1 overflow-x-auto rounded-xl bg-secondary/35 p-1">
            {settingsTabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <TabsTrigger
                  key={tab.value}
                  value={tab.value}
                  className="gap-1.5 whitespace-nowrap rounded-lg px-3 py-2 data-[state=active]:bg-card data-[state=active]:shadow-sm"
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span>{tab.label}</span>
                  {tab.badge ? <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">{tab.badge}</Badge> : null}
                </TabsTrigger>
              );
            })}
          </TabsList>

        {/* ==================== AI TAB ==================== */}
        <TabsContent value="ai" className="space-y-4">
          <div className="flex flex-col gap-3 rounded-xl border border-border bg-card px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="space-y-1">
              <p className="text-sm font-medium text-foreground">AI модели и маршрутизация</p>
              <p className="max-w-3xl text-xs text-muted-foreground">
                Сначала выбери провайдера по умолчанию, потом разнеси модели по ролям, и только после этого трогай runtime и reasoning.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant={aiDraftDirty ? "default" : "secondary"}>
                {aiDraftDirty ? "Есть несохраненные изменения" : "AI-конфиг синхронизирован"}
              </Badge>
              <Badge variant="outline">
                {uniqueRouteProviders.length > 1 ? "Раздельная маршрутизация" : "Один провайдер на все роли"}
              </Badge>
              <Badge variant="outline">
                {missingModelsCount === 0 ? "Пустых моделей нет" : `${missingModelsCount} полей без модели`}
              </Badge>
            </div>
          </div>

          <SectionCard title="Провайдер по умолчанию" icon={Bot} description="Выбор основного провайдера и модели для общего режима">
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-3">
                {providerOverview.map((providerItem) => (
                  <button
                    key={providerItem.value}
                    type="button"
                    onClick={() => handleDefaultProviderChange(providerItem.value)}
                    className={cn(
                      "rounded-xl border p-3 text-left transition-all",
                      providerItem.isSelected
                        ? "border-primary bg-primary/5 shadow-sm"
                        : "border-border bg-card hover:border-primary/30 hover:bg-primary/5"
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground">{providerItem.label}</p>
                        <p className="text-[11px] text-muted-foreground">
                          {providerItem.catalogSize ? `${providerItem.catalogSize} моделей` : "Каталог пуст, доступен ручной ввод"}
                        </p>
                      </div>
                      {providerItem.isSelected && <Badge className="shrink-0">Основной</Badge>}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      <Badge variant={providerItem.configured ? "secondary" : "outline"}>
                        {providerItem.configured ? "Готов" : "Требует настройку"}
                      </Badge>
                      <Badge variant={providerItem.enabled ? "secondary" : "outline"}>
                        {providerItem.enabled ? "Активен" : "Не включен"}
                      </Badge>
                    </div>
                    <p className="mt-3 text-[11px] text-muted-foreground">
                      {providerItem.activeRoutes.length > 0
                        ? `Маршруты: ${providerItem.activeRoutes.join(", ")}`
                        : "Отдельные роли пока не используют этот провайдер"}
                    </p>
                  </button>
                ))}
              </div>

              <div className="rounded-xl border border-border bg-card/80 p-4 space-y-4">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-medium text-muted-foreground uppercase">Провайдер</label>
                    <Select value={provider} onValueChange={handleDefaultProviderChange}>
                      <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {LLM_PROVIDERS.map((providerItem) => (
                          <SelectItem key={providerItem.value} value={providerItem.value}>{providerItem.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-medium text-muted-foreground uppercase">Модель</label>
                    {availableModels.length > 0 ? (
                      <Select value={model} onValueChange={setModel}>
                        <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {availableModels.map((providerModel) => (
                            <SelectItem key={providerModel} value={providerModel}>{providerModel}</SelectItem>
                          ))}
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

                <div className="flex flex-col gap-2 rounded-lg border border-dashed border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="space-y-1">
                    <p className="text-xs font-medium">{getProviderLabel(provider)}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {availableModels.length
                        ? "Модель можно выбрать из синхронизированного каталога."
                        : "Для этого провайдера сейчас используется ручной ввод модели."}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="secondary">{availableModels.length ? `${availableModels.length} вариантов` : "Ручной ввод"}</Badge>
                    <Badge variant="outline">{getProviderEnabled(config, provider) ? "Провайдер включен" : "Провайдер еще не активирован"}</Badge>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button size="sm" className="gap-1.5" onClick={onSave} disabled={saving}>
                    <Save className="h-3.5 w-3.5" /> {saving ? "Сохранение..." : "Сохранить основную"}
                  </Button>
                  <Button size="sm" variant="outline" className="gap-1.5" onClick={onRefreshModels} disabled={refreshing}>
                    <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} /> Обновить каталог
                  </Button>
                </div>
              </div>
            </div>
          </SectionCard>

          <SectionCard title="Маршруты по ролям" icon={Cpu} description="Отдельные пары провайдер/модель для чата, агентов и pipeline-оркестратора">
            <div className="space-y-4">
              <div className="flex flex-col gap-3 rounded-xl border border-border bg-muted/20 p-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="space-y-1">
                  <p className="text-xs font-medium text-foreground">Быстрые действия</p>
                  <p className="text-[11px] text-muted-foreground">
                    Можно скопировать основную модель в роли, дозаполнить пустые поля или откатить AI-черновик к сохраненному состоянию.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" className="gap-1.5" onClick={applyDefaultToAll}>
                    <Bot className="h-3.5 w-3.5" /> Копировать основную
                  </Button>
                  <Button size="sm" variant="outline" className="gap-1.5" onClick={fillMissingModels}>
                    <Cpu className="h-3.5 w-3.5" /> Заполнить пустые
                  </Button>
                  <Button size="sm" variant="ghost" className="gap-1.5" onClick={resetAiDraft}>
                    <RefreshCw className="h-3.5 w-3.5" /> Сбросить черновик
                  </Button>
                  <Button size="sm" className="gap-1.5" onClick={onSavePurpose} disabled={saving}>
                    <Save className="h-3.5 w-3.5" /> {saving ? "Сохранение..." : "Сохранить маршруты"}
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
                <PurposeModelSelector
                  label="Чат / Терминальный AI"
                  description="Интерактивный AI помощник"
                  icon={MessageSquare}
                  provider={chatProvider}
                  model={chatModel}
                  availableModels={getModelsForProvider(chatProvider)}
                  onProviderChange={(nextProvider) => {
                    setChatProvider(nextProvider);
                    setChatModel(getSuggestedModelForProvider(nextProvider));
                  }}
                  onModelChange={setChatModel}
                  onRefresh={() => onRefreshPurpose(chatProvider)}
                  refreshing={refreshingPurpose === chatProvider}
                />
                <PurposeModelSelector
                  label="Агенты (ReAct)"
                  description="Инструменты, планирование и итерации"
                  icon={Bot}
                  provider={agentProvider}
                  model={agentModel}
                  availableModels={getModelsForProvider(agentProvider)}
                  onProviderChange={(nextProvider) => {
                    setAgentProvider(nextProvider);
                    setAgentModel(getSuggestedModelForProvider(nextProvider));
                  }}
                  onModelChange={setAgentModel}
                  onRefresh={() => onRefreshPurpose(agentProvider)}
                  refreshing={refreshingPurpose === agentProvider}
                />
                <PurposeModelSelector
                  label="Оркестратор (Pipeline)"
                  description="Координация multi-step pipeline run"
                  icon={Workflow}
                  provider={orchProvider}
                  model={orchModel}
                  availableModels={getModelsForProvider(orchProvider)}
                  onProviderChange={(nextProvider) => {
                    setOrchProvider(nextProvider);
                    setOrchModel(getSuggestedModelForProvider(nextProvider));
                  }}
                  onModelChange={setOrchModel}
                  onRefresh={() => onRefreshPurpose(orchProvider)}
                  refreshing={refreshingPurpose === orchProvider}
                />
              </div>
            </div>
          </SectionCard>

          <SectionCard title="Runtime и расширенные опции" icon={Database} description="Ollama local/cloud runtime и управление reasoning">
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <div className="rounded-xl border border-border p-4 space-y-4">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-xs font-medium">Ollama Runtime</p>
                    <p className="text-[11px] text-muted-foreground">Один провайдер для локального `ollama serve` и облачного `ollama.com/api`</p>
                  </div>
                  <Badge variant={ollamaRoutingActive ? "default" : "secondary"}>
                    {ollamaRoutingActive ? `Используется · ${ollamaRuntimeSummary}` : `Готов · ${ollamaRuntimeSummary}`}
                  </Badge>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-medium text-muted-foreground uppercase">Режим runtime</label>
                    <Select
                      value={ollamaRuntimeMode}
                      onValueChange={(value) => {
                        setOllamaRuntimeMode(value);
                        if (value === "cloud") {
                          setOllamaCloudEnabled(true);
                        }
                      }}
                    >
                      <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {OLLAMA_RUNTIME_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2.5">
                      <div>
                        <p className="text-xs font-medium">Ollama Cloud</p>
                        <p className="text-[10px] text-muted-foreground">Прямой доступ к `ollama.com/api`</p>
                      </div>
                      <Switch
                        checked={ollamaCloudEnabled}
                        onCheckedChange={(checked) => {
                          setOllamaCloudEnabled(checked);
                          if (!checked && ollamaRuntimeMode === "cloud") {
                            setOllamaRuntimeMode("auto");
                          }
                        }}
                      />
                    </div>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-[10px] font-medium text-muted-foreground uppercase">Local Base URL</label>
                  <Input
                    value={ollamaBaseUrl}
                    onChange={(e) => setOllamaBaseUrl(e.target.value)}
                    placeholder="http://127.0.0.1:11434"
                    className="h-9"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-[10px] font-medium text-muted-foreground uppercase">Cloud API URL</label>
                  <Input
                    value={ollamaCloudBaseUrl}
                    onChange={(e) => setOllamaCloudBaseUrl(e.target.value)}
                    placeholder="https://ollama.com"
                    className="h-9"
                    disabled={!ollamaCloudEnabled}
                  />
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" className="gap-1.5" onClick={onSaveOllama} disabled={saving}>
                    <Save className="h-3.5 w-3.5" /> {saving ? "Сохранение..." : "Сохранить runtime"}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="gap-1.5"
                    onClick={() => onRefreshPurpose("ollama")}
                    disabled={refreshingPurpose === "ollama"}
                  >
                    <RefreshCw className={cn("h-3.5 w-3.5", refreshingPurpose === "ollama" && "animate-spin")} />
                    Проверить модели
                  </Button>
                </div>

                <div className="rounded-lg border border-dashed border-border px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="secondary">{ollamaLocalModels.length ? `${ollamaLocalModels.length} local` : "local: 0"}</Badge>
                    <Badge variant="secondary">{ollamaCloudModels.length ? `${ollamaCloudModels.length} cloud` : "cloud: 0"}</Badge>
                    <Badge variant="outline">{ollamaRuntimeSummary}</Badge>
                    <Badge variant="outline">{ollamaCatalogModels.length} всего в каталоге</Badge>
                  </div>
                  <p className="mt-2 text-[11px] text-muted-foreground">
                    `Auto` держит локальный runtime основным. `Cloud only` идёт напрямую в `ollama.com/api`. Для облака нужен `OLLAMA_API_KEY`, а cloud-модели в списке помечаются суффиксом `(cloud)`.
                  </p>
                </div>
              </div>

              <div className="rounded-xl border border-border p-4 space-y-4">
                <div>
                  <p className="text-xs font-medium">Reasoning Controls</p>
                  <p className="text-[11px] text-muted-foreground">Отдельные настройки для thinking-моделей в Ollama и reasoning в OpenAI</p>
                </div>

                <div className="space-y-2">
                  <div>
                    <p className="text-xs font-medium">Ollama Thinking</p>
                    <p className="text-[11px] text-muted-foreground">Для `glm-4.7-flash` и других thinking-моделей отправляет `think=false/true/low/medium/high`</p>
                  </div>

                  <Select value={ollamaThinkMode} onValueChange={setOllamaThinkMode}>
                    <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {OLLAMA_THINKING_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <div className="rounded-lg border border-dashed border-border px-4 py-3">
                    <p className="text-xs font-medium">
                      {ollamaThinkMode === AUTO_OLLAMA_THINKING_VALUE
                        ? "Модель сама решает, включать ли reasoning."
                        : ollamaThinkMode === "off"
                          ? "Reasoning будет принудительно отключен."
                          : `В Ollama будет отправлен think=${ollamaThinkMode}.`}
                    </p>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Для cloud и local runtime используется один и тот же параметр `think`, если модель его поддерживает.
                    </p>
                  </div>
                </div>

                <div className="space-y-2">
                  <div>
                    <p className="text-xs font-medium">OpenAI Reasoning</p>
                    <p className="text-[11px] text-muted-foreground">Управляет глубиной reasoning для Responses API, если OpenAI участвует в маршрутах</p>
                  </div>

                  <Select value={reasoningEffort} onValueChange={setReasoningEffort}>
                    <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={AUTO_REASONING_VALUE}>Auto</SelectItem>
                      <SelectItem value="none">None</SelectItem>
                      <SelectItem value="low">Low</SelectItem>
                      <SelectItem value="medium">Medium</SelectItem>
                      <SelectItem value="high">High</SelectItem>
                    </SelectContent>
                  </Select>

                  <div className="rounded-lg border border-dashed border-border px-4 py-3">
                    <p className="text-xs font-medium">
                      {provider === "openai" || routeConfigs.some((route) => route.provider === "openai")
                        ? "OpenAI сейчас участвует в активной схеме."
                        : "OpenAI сейчас не выбран, но параметр можно подготовить заранее."}
                    </p>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      `Auto` оставляет выбор движку. `Low/Medium/High` полезны, когда нужно жестче контролировать стоимость и глубину ответа.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </SectionCard>

          {/* API Keys status */}
          {apiKeys && isAdmin && (
            <SectionCard title="API ключи" icon={Key} description="Статус подключения провайдеров">
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-6 gap-3">
                {[
                  { name: "Gemini", key: "gemini_set", enabled: config.gemini_enabled },
                  { name: "Grok", key: "grok_set", enabled: config.grok_enabled },
                  { name: "OpenAI", key: "openai_set", enabled: config.openai_enabled },
                  { name: "Claude", key: "claude_set", enabled: config.claude_enabled },
                  { name: "Ollama Local", key: "ollama_local_set", enabled: config.ollama_enabled && ollamaRuntimeMode !== "cloud" },
                  { name: "Ollama Cloud", key: "ollama_cloud_set", enabled: config.ollama_enabled && ollamaCloudEnabled },
                ].map((p) => (
                  <div key={p.name} className="rounded-lg border border-border px-3 py-3">
                    <div className="flex items-center gap-3">
                      <div className={cn("h-2.5 w-2.5 rounded-full", apiKeys[p.key] ? "bg-green-500" : "bg-red-500")} />
                      <div>
                        <p className="text-xs font-medium">{p.name}</p>
                        <p className="text-[10px] text-muted-foreground">
                          {apiKeys[p.key]
                            ? "Подключен"
                            : p.name === "Ollama Local"
                              ? "Нужен Base URL"
                              : p.name === "Ollama Cloud"
                                ? "Нужен OLLAMA_API_KEY"
                                : "Не задан"}
                          {p.enabled ? " · Активен" : ""}
                        </p>
                      </div>
                    </div>
                    <div>
                      <p className="mt-3 text-[10px] text-muted-foreground">
                        {p.name === "Ollama Local"
                          ? (ollamaBaseUrl || "http://127.0.0.1:11434")
                          : p.name === "Ollama Cloud"
                            ? (ollamaCloudBaseUrl || "https://ollama.com")
                          : "Ключ сохранен в backend"}
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
                <Button size="sm" className="gap-1.5 h-7" onClick={handleSaveLogging} disabled={saving}>
                  <Save className="h-3 w-3" />
                  {saving ? "Сохранение..." : loggingSaved ? "✓ Сохранено" : "Сохранить"}
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
        {isAdmin && (
          <TabsContent value="activity" className="space-y-4">
            <SectionCard title="Журнал действий" icon={Activity} description="Полная история действий пользователей на платформе">
              <div className="space-y-4">
                {/* Filters */}
                <div className="flex flex-wrap items-center gap-3">
                  <div className="relative flex-1 min-w-[240px] xl:max-w-md">
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
        )}
        </div>
      </Tabs>
    </div>
  );
}
