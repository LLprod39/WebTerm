import { useCallback, useEffect, useMemo, useState } from "react";
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
// Constants
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
// Purpose Model Selector Component
// ─────────────────────────────────────────────────────────────────────────────

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
    <div className="group/selector relative space-y-4 rounded-xl border border-primary/5 bg-background/50 p-5 shadow-sm transition-all duration-300 hover:border-primary/20 hover:bg-background/80 hover:shadow-md">
      <div className="flex items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary shadow-inner transition-colors group-hover/selector:bg-primary group-hover/selector:text-primary-foreground">
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="font-semibold tracking-tight text-foreground/90">{label}</p>
          <p className="text-xs text-muted-foreground/80">{description}</p>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground/70">Провайдер</label>
          <Select value={provider} onValueChange={onProviderChange}>
            <SelectTrigger className="h-9 transition-colors group-hover/selector:border-primary/30"><SelectValue /></SelectTrigger>
            <SelectContent>
              {LLM_PROVIDERS.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground/70">Модель</label>
          {availableModels.length > 0 ? (
            <Select value={model} onValueChange={onModelChange}>
              <SelectTrigger className="h-9 transition-colors group-hover/selector:border-primary/30"><SelectValue /></SelectTrigger>
              <SelectContent>
                {availableModels.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
              </SelectContent>
            </Select>
          ) : (
            <div className="flex gap-1.5">
              <Input value={model} onChange={(e) => onModelChange(e.target.value)} placeholder="Model name" className="h-9 text-xs" />
              <Button size="icon" variant="outline" className="h-9 w-9 shrink-0 transition-colors hover:bg-primary/5 hover:text-primary" onClick={onRefresh} disabled={refreshing}>
                <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />
              </Button>
            </div>
          )}
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border/40 pt-3 text-[11px] font-medium text-muted-foreground">
        <span className="flex items-center gap-1.5"><div className="h-1.5 w-1.5 rounded-full bg-primary/60" />{getProviderLabel(provider)}</span>
        <span>{availableModels.length ? `${availableModels.length} моделей в каталоге` : "Ручной ввод модели"}</span>
      </div>
      {availableModels.length > 0 && (
        <Button size="sm" variant="ghost" className="mt-1 h-8 w-full justify-center px-3 text-xs text-muted-foreground/80 transition-colors hover:bg-primary/5 hover:text-primary" onClick={onRefresh} disabled={refreshing}>
          <RefreshCw className={cn("mr-2 h-3 w-3", refreshing && "animate-spin")} /> Обновить каталог
        </Button>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────────────────────

export default function SettingsAIPage() {
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
  
  const currentConfig = settingsData?.config;

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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">AI конфигурация</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">Провайдеры, модели и маршрутизация</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {aiDraftDirty ? (
            <span className="text-primary font-medium">Есть несохранённые изменения</span>
          ) : (
            <span>Сохранено</span>
          )}
          <span className="text-border">·</span>
          <span>{configuredProviderCount} провайдера</span>
        </div>
      </div>

      {/* Default Provider */}
      <SectionCard title="Провайдер по умолчанию" icon={Bot} description="Выбор основного провайдера и модели">
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {providerOverview.map((providerItem) => (
              <button
                key={providerItem.value}
                type="button"
                onClick={() => handleDefaultProviderChange(providerItem.value)}
                className={cn(
                  "group relative flex flex-col items-start rounded-lg border p-3 text-left transition-all",
                  providerItem.isSelected
                    ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                    : "border-border hover:border-primary/50 hover:bg-secondary/30"
                )}
              >
                <div className="flex w-full items-center justify-between">
                  <span className="text-sm font-medium">{providerItem.label}</span>
                  {providerItem.configured ? (
                    <div className="h-2 w-2 rounded-full bg-emerald-500" />
                  ) : (
                    <div className="h-2 w-2 rounded-full bg-muted-foreground/30" />
                  )}
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {providerItem.activeRoutes.length > 0 ? (
                    providerItem.activeRoutes.map((route) => (
                      <Badge key={route} variant="secondary" className="text-[9px]">{route}</Badge>
                    ))
                  ) : (
                    <span className="text-[10px] text-muted-foreground">Не используется</span>
                  )}
                </div>
                <p className="mt-1.5 text-[10px] text-muted-foreground">
                  {providerItem.catalogSize} моделей
                </p>
              </button>
            ))}
          </div>

          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={applyDefaultToAll}>
              Применить ко всем ролям
            </Button>
            <Button size="sm" variant="outline" onClick={resetAiDraft} disabled={!aiDraftDirty}>
              Сбросить черновик
            </Button>
          </div>
        </div>
      </SectionCard>

      {/* Purpose Routing */}
      <SectionCard
        title="Маршрутизация по ролям"
        icon={Workflow}
        description="Разные модели для разных типов задач"
        actions={
          <Button size="sm" onClick={onSavePurpose} disabled={saving || !aiDraftDirty}>
            <Save className="mr-1.5 h-3.5 w-3.5" />
            {saving ? "Сохранение..." : "Сохранить маршруты"}
          </Button>
        }
      >
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <PurposeModelSelector
            label="Чат / Терминальный AI"
            description="Интерактивный помощник"
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
            description="Инструменты и итерации"
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
            description="Координация multi-step"
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
      </SectionCard>

      {/* Runtime & Advanced */}
      <SectionCard title="Runtime и расширенные опции" icon={Database} description="Ollama local/cloud runtime и reasoning">
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {/* Ollama Runtime */}
          <div className="space-y-4 rounded-xl border border-border p-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-medium">Ollama Runtime</p>
                <p className="text-[11px] text-muted-foreground">Локальный и облачный runtime</p>
              </div>
              <Badge variant={ollamaRoutingActive ? "default" : "secondary"}>
                {ollamaRoutingActive ? `Активен - ${ollamaRuntimeSummary}` : `Готов - ${ollamaRuntimeSummary}`}
              </Badge>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <label className="text-[10px] font-medium uppercase text-muted-foreground">Режим runtime</label>
                <Select
                  value={ollamaRuntimeMode}
                  onValueChange={(value) => {
                    setOllamaRuntimeMode(value);
                    if (value === "cloud") setOllamaCloudEnabled(true);
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
              <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2.5">
                <div>
                  <p className="text-xs font-medium">Ollama Cloud</p>
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
            </div>

            <div className="space-y-1.5">
              <label className="text-[10px] font-medium uppercase text-muted-foreground">Local Base URL</label>
              <Input value={ollamaBaseUrl} onChange={(e) => setOllamaBaseUrl(e.target.value)} placeholder="http://127.0.0.1:11434" className="h-9" />
            </div>

            <div className="space-y-1.5">
              <label className="text-[10px] font-medium uppercase text-muted-foreground">Cloud API URL</label>
              <Input value={ollamaCloudBaseUrl} onChange={(e) => setOllamaCloudBaseUrl(e.target.value)} placeholder="https://ollama.com" className="h-9" disabled={!ollamaCloudEnabled} />
            </div>

            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" className="gap-1.5" onClick={onSaveOllama} disabled={saving}>
                <Save className="h-3.5 w-3.5" /> {saving ? "Сохранение..." : "Сохранить runtime"}
              </Button>
              <Button size="sm" variant="outline" className="gap-1.5" onClick={() => onRefreshPurpose("ollama")} disabled={refreshingPurpose === "ollama"}>
                <RefreshCw className={cn("h-3.5 w-3.5", refreshingPurpose === "ollama" && "animate-spin")} />
                Проверить модели
              </Button>
            </div>

            <div className="rounded-lg border border-dashed border-border px-4 py-3">
              <div className="flex flex-wrap gap-2">
                <Badge variant="secondary">{ollamaLocalModels.length} local</Badge>
                <Badge variant="secondary">{ollamaCloudModels.length} cloud</Badge>
                <Badge variant="outline">{ollamaCatalogModels.length} всего</Badge>
              </div>
            </div>
          </div>

          {/* Reasoning Controls */}
          <div className="space-y-4 rounded-xl border border-border p-4">
            <div>
              <p className="text-sm font-medium">Reasoning Controls</p>
              <p className="text-[11px] text-muted-foreground">Настройки thinking-моделей</p>
            </div>

            <div className="space-y-2">
              <div>
                <p className="text-xs font-medium">Ollama Thinking</p>
                <p className="text-[11px] text-muted-foreground">Для thinking-моделей</p>
              </div>
              <Select value={ollamaThinkMode} onValueChange={setOllamaThinkMode}>
                <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {OLLAMA_THINKING_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <div>
                <p className="text-xs font-medium">OpenAI Reasoning</p>
                <p className="text-[11px] text-muted-foreground">Глубина reasoning для Responses API</p>
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
            </div>
          </div>
        </div>
      </SectionCard>

      {/* API Keys Status */}
      {apiKeys && isAdmin && (
        <SectionCard title="API ключи" icon={Key} description="Статус подключения провайдеров">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-6">
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
                  <div className={cn("h-2.5 w-2.5 rounded-full", apiKeys[p.key] ? "bg-emerald-500" : "bg-red-500")} />
                  <div>
                    <p className="text-xs font-medium">{p.name}</p>
                    <p className="text-[10px] text-muted-foreground">
                      {apiKeys[p.key] ? "Подключен" : "Не задан"}
                      {p.enabled ? " - Активен" : ""}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      {/* Domain Auth */}
      {isAdmin && config.domain_auth_enabled !== undefined && (
        <SectionCard title="Доменная авторизация" icon={Globe} description="SSO через HTTP-заголовок">
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-lg border border-border px-3 py-2.5">
              <p className="text-[10px] uppercase text-muted-foreground">Статус</p>
              <p className="text-sm font-medium">{config.domain_auth_enabled ? "Включен" : "Выключен"}</p>
            </div>
            <div className="rounded-lg border border-border px-3 py-2.5">
              <p className="text-[10px] uppercase text-muted-foreground">Header</p>
              <p className="font-mono text-sm">{config.domain_auth_header || "REMOTE_USER"}</p>
            </div>
            <div className="rounded-lg border border-border px-3 py-2.5">
              <p className="text-[10px] uppercase text-muted-foreground">Авто-создание</p>
              <p className="text-sm font-medium">{config.domain_auth_auto_create ? "Да" : "Нет"}</p>
            </div>
          </div>
        </SectionCard>
      )}
    </div>
  );
}
