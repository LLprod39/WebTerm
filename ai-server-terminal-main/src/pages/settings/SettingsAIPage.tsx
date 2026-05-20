import { useCallback, useEffect, useMemo, useState, type ElementType } from "react";
import { useI18n } from "@/lib/i18n";
import {
  Bot,
  RefreshCw,
  Save,
  Cpu,
  Key,
  Globe,
  Database,
  MessageSquare,
  Workflow,
  Brain,
  Lock,
  Network,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchModels,
  fetchSettings,
  refreshModels,
  saveSettings,
  fetchAuthSession,
  type SettingsConfig,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { SettingsSectionCard as SectionCard } from "@/components/settings/SettingsSectionCard";
import { QueryStateBlock } from "@/components/ui/page-shell";

// ─────────────────────────────────────────────────────────────────────────────
// Constants & Metadata
// ─────────────────────────────────────────────────────────────────────────────

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

const OLLAMA_RUNTIME_KEYS = [
  { value: "auto", key: "ai.ollama_auto" },
  { value: "local", key: "ai.ollama_local_only" },
  { value: "cloud", key: "ai.ollama_cloud_only" },
];

const OLLAMA_THINKING_KEYS = [
  { value: AUTO_OLLAMA_THINKING_VALUE, key: "ai.ollama_auto" },
  { value: "off", key: "ai.thinking_off" },
  { value: "on", key: "ai.thinking_on" },
  { value: "low", key: "ai.thinking_low" },
  { value: "medium", key: "ai.thinking_medium" },
  { value: "high", key: "ai.thinking_high" },
];

const PROVIDER_API_STATUS_KEY: Record<string, string> = {
  gemini: "gemini_set",
  grok: "grok_set",
  openai: "openai_set",
  claude: "claude_set",
  ollama: "ollama_set",
};

// Professional business metadata for providers
const PROVIDER_METADATA: Record<string, {
  accentColor: string;
  textColor: string;
  badge: string;
  brand: string;
  slogan: string;
}> = {
  grok: {
    accentColor: "bg-amber-500",
    textColor: "text-amber-500",
    badge: "Высокая производительность",
    brand: "xAI",
    slogan: "Анализ текстовых данных на высокой скорости инференса.",
  },
  gemini: {
    accentColor: "bg-violet-500",
    textColor: "text-violet-500",
    badge: "Широкий контекст",
    brand: "Google",
    slogan: "Модели общего назначения с поддержкой широкого окна контекста.",
  },
  openai: {
    accentColor: "bg-emerald-500",
    textColor: "text-emerald-500",
    badge: "Логические операции",
    brand: "OpenAI",
    slogan: "Стандарт индустрии для решения логических задач и вызова внешних функций.",
  },
  claude: {
    accentColor: "bg-orange-500",
    textColor: "text-orange-500",
    badge: "Работа с кодом",
    brand: "Anthropic",
    slogan: "Специализированные модели для анализа кода и проведения рефакторинга.",
  },
  ollama: {
    accentColor: "bg-sky-500",
    textColor: "text-sky-500",
    badge: "Локальное исполнение",
    brand: "Ollama",
    slogan: "Исполнение моделей на вычислительных ресурсах предприятия без отправки внешних запросов.",
  },
};

// Features supported by each routing role
const ROLE_FEATURES: Record<string, { label: string; tooltip: string }[]> = {
  "Чат / Терминальный AI": [
    { label: "Streaming", tooltip: "Потоковый моментальный вывод ответов в консоль." },
    { label: "Fast Response", tooltip: "Минимальная задержка перед ответом." },
    { label: "Context Aware", tooltip: "Учет предыстории сессии и настроек сервера." },
  ],
  "Агенты (ReAct)": [
    { label: "Tool Calling", tooltip: "Надежный вызов внешних SSH и системных инструментов." },
    { label: "Long Context", tooltip: "Анализ больших файлов конфигураций и системных логов." },
    { label: "Self-Correction", tooltip: "Корректировка действий при ошибках выполнения." },
  ],
  "Оркестратор (Pipeline)": [
    { label: "JSON Output", tooltip: "Строгая генерация структурированных данных." },
    { label: "Consistency", tooltip: "Стабильное выполнение шагов автоматизации." },
    { label: "State Control", tooltip: "Передача состояния между шагами выполнения сценария." },
  ],
};

// ─────────────────────────────────────────────────────────────────────────────
// Helper Functions
// ─────────────────────────────────────────────────────────────────────────────

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

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function PurposeModelSelectorFooter({ provider, availableModels, onRefresh, refreshing }: { provider: string; availableModels: string[]; onRefresh: () => void; refreshing: boolean }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2 text-[10px] font-medium text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <div className="h-1.5 w-1.5 rounded-full bg-primary/70" />
          {getProviderLabel(provider)}
        </span>
        {availableModels.length > 0 ? (
          <span className="flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-600 border border-emerald-500/20 dark:text-emerald-400">
            Каталог активен ({availableModels.length} мод.)
          </span>
        ) : (
          <span className="flex items-center gap-1 px-2 py-0.5 rounded bg-amber-500/10 text-amber-600 border border-amber-500/20 dark:text-amber-400">
            Ручной ввод
          </span>
        )}
      </div>
      {availableModels.length > 0 && (
        <Button 
          size="sm" 
          variant="ghost" 
          className="h-8 w-full justify-center text-xs text-muted-foreground hover:text-primary hover:bg-secondary transition-all duration-200" 
          onClick={onRefresh} 
          disabled={refreshing}
        >
          <RefreshCw className={cn("mr-2 h-3.5 w-3.5", refreshing && "animate-spin")} /> 
          Обновить каталог моделей
        </Button>
      )}
    </div>
  );
}

function PurposeModelSelector({
  label, description, icon: Icon, provider, model, availableModels,
  onProviderChange, onModelChange, onRefresh, refreshing, features,
}: {
  label: string; description: string; icon: ElementType;
  provider: string; model: string; availableModels: string[];
  onProviderChange: (p: string) => void; onModelChange: (m: string) => void;
  onRefresh: () => void; refreshing: boolean;
  features?: { label: string; tooltip: string }[];
}) {
  const providerColors: Record<string, string> = {
    grok: "bg-amber-500",
    gemini: "bg-violet-500",
    openai: "bg-emerald-500",
    claude: "bg-orange-500",
    ollama: "bg-sky-500",
  };
  const activeDotColor = providerColors[provider] || "bg-primary";

  return (
    <div className="group/selector relative flex flex-col justify-between space-y-4 rounded-xl border border-border/60 bg-card/40 p-5 shadow-sm transition-all duration-200 hover:border-border hover:bg-card/60">
      <div>
        <div className="flex items-start justify-between gap-3.5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-secondary text-foreground border border-border">
              <Icon className="h-5 w-5" />
            </div>
            <div>
              <h3 className="font-semibold text-sm tracking-tight text-foreground">{label}</h3>
              <p className="text-[11px] text-muted-foreground mt-0.5 leading-normal">{description}</p>
            </div>
          </div>
        </div>

        {/* Features Row */}
        {features && features.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-3">
            {features.map((f) => (
              <span
                key={f.label}
                title={f.tooltip}
                className="cursor-help rounded bg-muted px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground transition-all hover:bg-muted-foreground/15"
              >
                {f.label}
              </span>
            ))}
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 mt-4">
          <div className="space-y-1.5">
            <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Провайдер</label>
            <Select value={provider} onValueChange={onProviderChange}>
              <SelectTrigger className="h-9 transition-colors hover:border-primary/20 bg-background/50 hover:bg-background">
                <span className="flex items-center gap-2 truncate text-xs">
                  <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", activeDotColor)} />
                  <SelectValue />
                </span>
              </SelectTrigger>
              <SelectContent className="text-xs">
                {LLM_PROVIDERS.map((p) => (
                  <SelectItem key={p.value} value={p.value}>
                    <span className="flex items-center gap-2">
                      <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", providerColors[p.value] || "bg-muted-foreground/30")} />
                      {p.label}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          
          <div className="space-y-1.5">
            <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Модель</label>
            {availableModels.length > 0 ? (
              <Select value={model} onValueChange={onModelChange}>
                <SelectTrigger className="h-9 transition-colors hover:border-primary/20 bg-background/50 hover:bg-background text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="text-xs">
                  {availableModels.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <div className="flex gap-1.5">
                <Input 
                  value={model} 
                  onChange={(e) => onModelChange(e.target.value)} 
                  placeholder="Например, gpt-4o" 
                  className="h-9 text-xs transition-colors hover:border-primary/20 bg-background/50" 
                />
                <Button 
                  size="icon" 
                  variant="outline" 
                  className="h-9 w-9 shrink-0 transition-colors hover:bg-secondary bg-background/50" 
                  onClick={onRefresh} 
                  disabled={refreshing}
                >
                  <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="mt-4 pt-3 border-t border-border/30">
        <PurposeModelSelectorFooter 
          provider={provider} 
          availableModels={availableModels} 
          onRefresh={onRefresh} 
          refreshing={refreshing} 
        />
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────────────────────

export default function SettingsAIPage() {
  const queryClient = useQueryClient();
  const { t } = useI18n();
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
  
  const currentConfig = settingsData?.config;

  // Form states
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

  const getSuggestedModelForProvider = useCallback((nextProvider: string, preferredModel = ""): string => {
    const models = getModelsForProvider(nextProvider);
    if (!models.length) return preferredModel;
    if (preferredModel && models.includes(preferredModel)) return preferredModel;
    if (currentConfig) {
      const savedModel = getSavedModelForProvider(currentConfig, nextProvider);
      if (savedModel && models.includes(savedModel)) return savedModel;
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

  const onSaveOllama = async () => {
    setSaving(true);
    try {
      await saveSettings({
        ollama_base_url: ollamaBaseUrl,
        ollama_runtime_mode: ollamaRuntimeMode,
        ollama_cloud_enabled: ollamaCloudEnabled,
        ollama_cloud_base_url: ollamaCloudBaseUrl,
        ollama_think_mode: ollamaThinkMode === AUTO_OLLAMA_THINKING_VALUE ? "" : ollamaThinkMode,
      });
      await queryClient.invalidateQueries({ queryKey: ["settings", "config"] });
    } finally { setSaving(false); }
  };

  if (settingsLoading || settingsError || !settingsData?.success) {
    return (
      <QueryStateBlock
        loading={settingsLoading}
        error={settingsError || (!settingsLoading && !settingsData?.success ? new Error("Ошибка загрузки настроек") : undefined)}
        errorText="Не удалось загрузить настройки AI"
        onRetry={() => queryClient.invalidateQueries({ queryKey: ["settings", "config"] })}
      >
        {null}
      </QueryStateBlock>
    );
  }

  const config = settingsData.config;
  const apiKeys = settingsData.api_keys as Record<string, boolean> | undefined;
  
  const savedActiveProvider = LLM_PROVIDER_VALUES.includes(config.internal_llm_provider || "")
    ? config.internal_llm_provider
    : LLM_PROVIDER_VALUES.includes(config.default_provider || "")
      ? config.default_provider
      : "grok";

  const routeConfigs = [
    { key: "chat", shortLabel: "Chat", label: "Чат / Терминальный AI", description: "Интерактивный помощник", icon: MessageSquare, provider: chatProvider, model: chatModel },
    { key: "agent", shortLabel: "Agent", label: "Агенты (ReAct)", description: "Длинные задачи и итерации", icon: Bot, provider: agentProvider, model: agentModel },
    { key: "orchestrator", shortLabel: "Pipeline", label: "Оркестратор (Pipeline)", description: "Координация пайплайнов", icon: Workflow, provider: orchProvider, model: orchModel },
  ];

  const uniqueRouteProviders = Array.from(new Set(routeConfigs.map((route) => route.provider)));
  const ollamaLocalModels = modelsData?.ollama_local || [];
  const ollamaCloudModels = modelsData?.ollama_cloud || [];
  const ollamaCatalogModels = getModelsForProvider("ollama");
  const ollamaRoutingActive = provider === "ollama" || routeConfigs.some((route) => route.provider === "ollama");
  const ollamaRuntimeSummary = ollamaRuntimeMode === "cloud" ? "Только облако" : ollamaRuntimeMode === "local" ? "Только локально" : "Авто";

  const providerOverview = LLM_PROVIDERS.map((providerOption) => {
    const catalogSize = getModelsForProvider(providerOption.value).length;
    const activeRoutes = routeConfigs.filter((route) => route.provider === providerOption.value).map((route) => route.shortLabel);
    const configured = Boolean(apiKeys?.[PROVIDER_API_STATUS_KEY[providerOption.value]]);
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

  const configuredProviderCount = providerOverview.filter((p) => p.configured).length;

  return (
    <div className="space-y-6 pb-10">
      {/* Page Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-secondary text-foreground border border-border">
            <Bot className="h-4 w-4" />
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight text-foreground">Панель управления AI</h1>
            <p className="text-[11px] text-muted-foreground">Настройки провайдеров языковых моделей, конфигурация локального выполнения и маршрутизация.</p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          {aiDraftDirty ? (
            <span className="flex items-center gap-1.5 rounded-md border border-amber-500/25 bg-amber-500/10 px-2 py-1 text-amber-600">
              Несохраненные изменения
            </span>
          ) : (
            <span className="text-muted-foreground/60">Все настройки сохранены</span>
          )}
          <span className="text-border">·</span>
          <span>{configuredProviderCount} активных API</span>
        </div>
      </div>

      {/* Default Provider */}
      <SectionCard 
        title="Провайдер по умолчанию" 
        icon={Bot} 
        description="Выбор провайдера и базовой модели по умолчанию для стандартных запросов в системе."
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {providerOverview.map((providerItem) => {
              const meta = PROVIDER_METADATA[providerItem.value as keyof typeof PROVIDER_METADATA] || PROVIDER_METADATA.grok;
              return (
                <button
                  key={providerItem.value}
                  type="button"
                  onClick={() => handleDefaultProviderChange(providerItem.value)}
                  className={cn(
                    "group relative flex flex-col justify-between rounded-xl border p-4 text-left transition-all duration-200 active:scale-[0.99] outline-none",
                    providerItem.isSelected
                      ? "bg-primary/[0.02] border-primary shadow-sm"
                      : "border-border/60 bg-card/40 hover:border-border/80 hover:bg-card/70"
                  )}
                >
                  <div className="flex w-full items-start justify-between">
                    <div>
                      <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{meta.brand}</span>
                      <h3 className="text-sm font-bold tracking-tight text-foreground mt-0.5">{providerItem.label.split(" ")[0]}</h3>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="relative flex h-2 w-2 shrink-0">
                        <span className={cn("relative inline-flex h-2 w-2 rounded-full transition-all duration-300", 
                          providerItem.configured ? meta.accentColor : "bg-muted-foreground/30"
                        )} />
                      </span>
                    </div>
                  </div>
                  
                  <div className="mt-4 w-full space-y-2">
                    <p className="text-[10px] text-muted-foreground leading-snug">{meta.slogan}</p>
                    <span className={cn("inline-flex rounded px-1.5 py-0.5 text-[9px] font-semibold tracking-wide border bg-background/50", 
                      providerItem.isSelected ? "border-primary/20 text-primary" : "border-border/40 text-muted-foreground"
                    )}>
                      {meta.badge}
                    </span>
                  </div>

                  <div className="mt-4 pt-3 border-t border-border/30 w-full flex items-center justify-between">
                    <div className="flex flex-wrap gap-1">
                      {providerItem.activeRoutes.length > 0 ? (
                        providerItem.activeRoutes.map((route) => {
                          const routeLabels: Record<string, string> = {
                            "Chat": "Чат",
                            "Agent": "Агент",
                            "Pipeline": "Пайплайн"
                          };
                          return (
                            <span key={route} className="rounded bg-muted px-1.5 py-0.5 text-[9px] font-semibold text-muted-foreground border border-border/50">
                              {routeLabels[route] || route}
                            </span>
                          );
                        })
                      ) : (
                        <span className="text-[9px] text-muted-foreground/50 italic">Не назначен</span>
                      )}
                    </div>
                    <span className="text-[9px] font-medium text-muted-foreground shrink-0">
                      {providerItem.catalogSize > 0 ? `${providerItem.catalogSize} мод.` : "Ручной"}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="flex flex-wrap gap-3 mt-4">
            <Button 
              size="sm" 
              variant="outline" 
              onClick={applyDefaultToAll}
              className="font-medium bg-background/40 border-border hover:bg-secondary transition-all duration-200 text-xs"
            >
              Синхронизировать все роли
            </Button>
            <Button 
              size="sm" 
              variant="ghost" 
              onClick={resetAiDraft} 
              disabled={!aiDraftDirty}
              className="text-muted-foreground hover:text-foreground hover:bg-secondary transition-all duration-200 text-xs"
            >
              Сбросить изменения
            </Button>
          </div>
        </div>
      </SectionCard>

      {/* Purpose Routing */}
      <SectionCard
        title="Маршрутизация моделей по ролям"
        icon={Workflow}
        description="Назначение специализированных моделей для решения конкретных системных и прикладных задач."
        actions={
          <Button 
            size="sm" 
            onClick={onSavePurpose} 
            disabled={saving || !aiDraftDirty}
            className="shadow-sm font-medium text-xs transition-all duration-200 bg-primary text-primary-foreground hover:bg-primary/90"
          >
            {saving ? (
              <>
                <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                Сохранение конфигурации...
              </>
            ) : (
              <>
                <Save className="mr-1.5 h-3.5 w-3.5" />
                Сохранить настройки ролей
              </>
            )}
          </Button>
        }
      >
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <PurposeModelSelector
            label="Чат / Терминальный AI"
            description="Интерактивный помощник пользователя в окне терминала."
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
            features={ROLE_FEATURES["Чат / Терминальный AI"]}
          />
          <PurposeModelSelector
            label="Агенты (ReAct)"
            description="Запуск фоновых автономных агентов для решения системных задач."
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
            features={ROLE_FEATURES["Агенты (ReAct)"]}
          />
          <PurposeModelSelector
            label="Оркестратор (Pipeline)"
            description="Исполнение структурированных шагов в сценариях автоматизации."
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
            features={ROLE_FEATURES["Оркестратор (Pipeline)"]}
          />
        </div>
      </SectionCard>

      {/* Runtime & Advanced */}
      <SectionCard 
        title="Локальный инференс и параметры рассуждений" 
        icon={Database} 
        description="Настройка локального и облачного выполнения моделей Ollama и параметров обдумывания."
      >
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          {/* Ollama Runtime Control Panel */}
          <div className="relative space-y-4 rounded-xl border border-border/60 bg-card/40 p-5 shadow-sm">
            {/* Header */}
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-secondary text-foreground border border-border">
                  <Cpu className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="font-semibold text-sm text-foreground">Настройка инференса Ollama</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">Параметры подключения к локальным и облачным узлам выполнения моделей.</p>
                </div>
              </div>
              <Badge variant={ollamaRoutingActive ? "default" : "secondary"} className="px-2.5 py-0.5 text-[10px] font-semibold">
                {ollamaRoutingActive ? `Активен — ${ollamaRuntimeSummary}` : `Готов — ${ollamaRuntimeSummary}`}
              </Badge>
            </div>

            {/* Config Fields */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Режим выполнения</label>
                <Select
                  value={ollamaRuntimeMode}
                  onValueChange={(value) => {
                    setOllamaRuntimeMode(value);
                    if (value === "cloud") setOllamaCloudEnabled(true);
                  }}
                >
                  <SelectTrigger className="h-9 text-xs bg-background/50 hover:bg-background">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="text-xs">
                    {OLLAMA_RUNTIME_KEYS.map((option) => {
                      const runtimeLabels: Record<string, string> = {
                        "auto": "Автоматический выбор (Auto)",
                        "local": "Только локальный сервер",
                        "cloud": "Только облачный хаб"
                      };
                      return (
                        <SelectItem key={option.value} value={option.value}>
                          {runtimeLabels[option.value] || t(option.key)}
                        </SelectItem>
                      );
                    })}
                  </SelectContent>
                </Select>
                <p className="text-[10px] text-muted-foreground leading-normal mt-1">
                  {ollamaRuntimeMode === "auto" && "Автоматическое переключение в зависимости от доступности узлов."}
                  {ollamaRuntimeMode === "local" && "Использовать только локально запущенный сервер Ollama."}
                  {ollamaRuntimeMode === "cloud" && "Использовать облачный реестр Ollama Hub API."}
                </p>
              </div>
              
              <div className="flex flex-col justify-between rounded-xl border border-border/50 bg-background/30 p-3 hover:border-border transition-colors">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-xs font-semibold text-foreground">Облачные модели Ollama</h4>
                    <p className="text-[10px] text-muted-foreground">ollama.com/api</p>
                  </div>
                  <Switch
                    checked={ollamaCloudEnabled}
                    onCheckedChange={(checked) => {
                      setOllamaCloudEnabled(checked);
                      if (!checked && ollamaRuntimeMode === "cloud") setOllamaRuntimeMode("auto");
                    }}
                  />
                </div>
                <p className="text-[10px] text-muted-foreground mt-2 leading-snug">
                  Использование удаленного API Ollama Cloud для выполнения.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Адрес локального сервера</label>
                <div className="relative">
                  <Globe className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground/60" />
                  <Input 
                    value={ollamaBaseUrl} 
                    onChange={(e) => setOllamaBaseUrl(e.target.value)} 
                    placeholder="http://127.0.0.1:11434" 
                    className="h-9 pl-9 text-xs font-mono transition-colors hover:border-primary/20 focus-visible:ring-primary/20" 
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Адрес облачного сервера</label>
                <div className="relative">
                  <Globe className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground/60" />
                  <Input 
                    value={ollamaCloudBaseUrl} 
                    onChange={(e) => setOllamaCloudBaseUrl(e.target.value)} 
                    placeholder="https://ollama.com" 
                    className="h-9 pl-9 text-xs font-mono transition-colors hover:border-primary/20 focus-visible:ring-primary/20" 
                    disabled={!ollamaCloudEnabled} 
                  />
                </div>
              </div>
            </div>

            <div className="flex flex-wrap gap-2.5 pt-2 border-t border-border/30">
              <Button 
                size="sm" 
                variant="outline" 
                className="gap-1.5 text-xs bg-background/50 hover:bg-secondary transition-all duration-200" 
                onClick={onSaveOllama} 
                disabled={saving}
              >
                <Save className="h-3.5 w-3.5" /> 
                {saving ? "Сохранение..." : "Сохранить параметры"}
              </Button>
              <Button 
                size="sm" 
                variant="outline" 
                className="gap-1.5 text-xs bg-background/50 hover:bg-secondary transition-all duration-200" 
                onClick={() => onRefreshPurpose("ollama")} 
                disabled={refreshingPurpose === "ollama"}
              >
                <RefreshCw className={cn("h-3.5 w-3.5", refreshingPurpose === "ollama" && "animate-spin")} />
                Сканировать модели
              </Button>
            </div>

            {/* Model catalogs stats breakdown */}
            <div className="rounded-xl border border-dashed border-border/60 bg-background/10 px-4 py-3 flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap gap-2">
                <Badge variant="secondary" className="bg-secondary text-foreground hover:bg-secondary/80 text-[10px] font-medium border border-border">{ollamaLocalModels.length} локально</Badge>
                <Badge variant="secondary" className="bg-secondary text-foreground hover:bg-secondary/80 text-[10px] font-medium border border-border">{ollamaCloudModels.length} облако</Badge>
              </div>
              <span className="text-[10px] font-medium text-muted-foreground">Всего в каталоге: {ollamaCatalogModels.length}</span>
            </div>
          </div>

          {/* Reasoning Control Panel */}
          <div className="relative space-y-4 rounded-xl border border-border/60 bg-card/40 p-5 shadow-sm">
            {/* Header */}
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-secondary text-foreground border border-border">
                <Brain className="h-5 w-5" />
              </div>
              <div>
                <h3 className="font-semibold text-sm text-foreground">Параметры рассуждений моделей</h3>
                <p className="text-xs text-muted-foreground mt-0.5">Настройки вывода размышлений для логических моделей (Reasoning / Thinking).</p>
              </div>
            </div>

            {/* Ollama Thinking Option */}
            <div className="space-y-2 rounded-xl border border-border/40 bg-background/20 p-3 hover:border-border transition-colors">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-semibold text-foreground">Вывод рассуждений Ollama</h4>
                  <p className="text-[10px] text-muted-foreground mt-0.5">Отображение тегов &lt;think&gt; для локальных моделей (например, DeepSeek-R1).</p>
                </div>
              </div>
              <Select value={ollamaThinkMode} onValueChange={setOllamaThinkMode}>
                <SelectTrigger className="h-9 text-xs transition-colors hover:border-primary/20 bg-background/50 hover:bg-background">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="text-xs">
                  {OLLAMA_THINKING_KEYS.map((option) => {
                    const thinkLabels: Record<string, string> = {
                      [AUTO_OLLAMA_THINKING_VALUE]: "Автоматически (Auto)",
                      "off": "Скрывать размышления полностью",
                      "on": "Показывать размышления полностью",
                      "low": "Краткие размышления (Low)",
                      "medium": "Средняя глубина (Medium)",
                      "high": "Максимальная глубина (High)"
                    };
                    return (
                      <SelectItem key={option.value} value={option.value}>
                        {thinkLabels[option.value] || t(option.key)}
                      </SelectItem>
                    );
                  })}
                </SelectContent>
              </Select>
            </div>

            {/* OpenAI Reasoning Effort Option */}
            <div className="space-y-2 rounded-xl border border-border/40 bg-background/20 p-3 hover:border-border transition-colors">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-semibold text-foreground">Глубина рассуждений OpenAI (o-серия)</h4>
                  <p className="text-[10px] text-muted-foreground mt-0.5">Параметр reasoning_effort для моделей OpenAI o1 и o3-mini.</p>
                </div>
              </div>
              <Select value={reasoningEffort} onValueChange={setReasoningEffort}>
                <SelectTrigger className="h-9 text-xs transition-colors hover:border-primary/20 bg-background/50 hover:bg-background">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="text-xs">
                  <SelectItem value={AUTO_REASONING_VALUE}>Автоматически (Auto)</SelectItem>
                  <SelectItem value="none">Без рассуждений (None)</SelectItem>
                  <SelectItem value="low">Краткие размышления (Low)</SelectItem>
                  <SelectItem value="medium">Сбалансированная глубина (Medium)</SelectItem>
                  <SelectItem value="high">Глубокие рассуждения (High)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <p className="text-[10px] text-muted-foreground leading-normal italic bg-background/30 p-2.5 rounded-lg border border-border/30">
              * Выбор более глубоких рассуждений может увеличить задержку первого токена (TTFT), но повышает качество решения сложных логических задач.
            </p>
          </div>
        </div>
      </SectionCard>

      {/* API Keys Status */}
      {apiKeys && isAdmin && (
        <SectionCard 
          title="Статус подключения API-ключей" 
          icon={Lock} 
          description="Мониторинг доступности внешних провайдеров на основе загруженных в конфигурацию ключей."
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {[
              { name: "Gemini Pro", key: "gemini_set", enabled: config.gemini_enabled, desc: "Google AI Studio / Vertex AI" },
              { name: "Grok xAI", key: "grok_set", enabled: config.grok_enabled, desc: "xAI API" },
              { name: "OpenAI GPT", key: "openai_set", enabled: config.openai_enabled, desc: "OpenAI API (GPT & o-series)" },
              { name: "Claude Anthropic", key: "claude_set", enabled: config.claude_enabled, desc: "Anthropic API (Claude)" },
              { name: "Ollama Local Node", key: "ollama_local_set", enabled: config.ollama_enabled && ollamaRuntimeMode !== "cloud", desc: "Локальный адрес Ollama" },
              { name: "Ollama Cloud Hub", key: "ollama_cloud_set", enabled: config.ollama_enabled && ollamaCloudEnabled, desc: "Удаленный API-адрес Ollama" },
            ].map((p) => {
              const active = apiKeys[p.key];
              return (
                <div 
                  key={p.name} 
                  className={cn(
                    "relative overflow-hidden rounded-xl border p-4 transition-all duration-200 bg-card/40 border-border/60",
                    active ? "hover:border-emerald-500/30" : "hover:border-border/85"
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-2">
                        <h4 className="text-xs font-semibold text-foreground">{p.name}</h4>
                        {!p.enabled && (
                          <span className="rounded bg-muted-foreground/10 px-1 py-0.2 text-[8px] font-semibold text-muted-foreground">Откл.</span>
                        )}
                      </div>
                      <p className="text-[10px] text-muted-foreground/80 leading-normal">{p.desc}</p>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0 text-[10px] font-medium">
                      <span className={cn(
                        "h-1.5 w-1.5 rounded-full shrink-0",
                        active ? "bg-emerald-500" : "bg-muted-foreground/30"
                      )} />
                      <span className="text-muted-foreground">{active ? "Подключен" : "Не настроен"}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </SectionCard>
      )}

      {/* Domain Auth */}
      {isAdmin && config.domain_auth_enabled !== undefined && (
        <SectionCard 
          title="Доменная SSO-авторизация" 
          icon={Network} 
          description="Настройки сквозной аутентификации пользователей через прокси-сервер организации."
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-xl border border-border/50 bg-card/25 p-4 transition-all hover:border-border">
              <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Интеграция SSO</p>
              <div className="flex items-center gap-2 mt-1.5">
                <span className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  config.domain_auth_enabled ? "bg-emerald-500" : "bg-amber-500"
                )} />
                <p className="text-sm font-semibold text-foreground">
                  {config.domain_auth_enabled ? "Активно" : "Отключено"}
                </p>
              </div>
              <p className="text-[10px] text-muted-foreground mt-2 leading-snug">
                {config.domain_auth_enabled 
                  ? "Авторизация через корпоративный прокси включена." 
                  : "Требуется стандартный ввод логина и пароля."}
              </p>
            </div>
            
            <div className="rounded-xl border border-border/50 bg-card/25 p-4 transition-all hover:border-border">
              <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">HTTP-заголовок</p>
              <p className="font-mono text-sm font-semibold text-foreground mt-1.5">
                {config.domain_auth_header || "REMOTE_USER"}
              </p>
              <p className="text-[10px] text-muted-foreground mt-2 leading-snug">
                HTTP-заголовок, передающий имя пользователя из upstream-прокси (Nginx/Authelia/OAuth2).
              </p>
            </div>
            
            <div className="rounded-xl border border-border/50 bg-card/25 p-4 transition-all hover:border-border">
              <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Автоматическое создание профилей</p>
              <p className="text-sm font-semibold text-foreground mt-1.5">
                {config.domain_auth_auto_create ? "Разрешено" : "Запрещено"}
              </p>
              <p className="text-[10px] text-muted-foreground mt-2 leading-snug">
                Создание локального профиля при первом входе нового доменного пользователя.
              </p>
            </div>
          </div>
        </SectionCard>
      )}
    </div>
  );
}
