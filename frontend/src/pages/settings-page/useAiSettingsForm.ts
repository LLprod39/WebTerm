import { useCallback, useEffect, useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Bot, MessageSquare, Workflow } from "lucide-react";
import {
  refreshModels,
  saveSettings,
  type ModelsResponse,
  type SettingsConfig,
} from "@/lib/api";
import {
  AUTO_OLLAMA_THINKING_VALUE,
  AUTO_REASONING_VALUE,
  getProviderEnabled,
  getSavedModelForProvider,
  LLM_PROVIDERS,
  LLM_PROVIDER_VALUES,
  PROVIDER_API_STATUS_KEY,
} from "./constants";
import type { ProviderOverviewItem, RouteModelConfig } from "./aiSettingsTypes";

type RefreshableProvider = "gemini" | "grok" | "openai" | "fair" | "claude" | "ollama";

type UseAiSettingsFormArgs = {
  currentConfig?: SettingsConfig;
  modelsData?: ModelsResponse;
  apiKeys?: Record<string, boolean>;
  saving: boolean;
  setSaving: Dispatch<SetStateAction<boolean>>;
};

export type UseAiSettingsFormResult = ReturnType<typeof useAiSettingsForm>;

export function useAiSettingsForm({
  currentConfig,
  modelsData,
  apiKeys,
  saving,
  setSaving,
}: UseAiSettingsFormArgs) {
  const queryClient = useQueryClient();
  const [provider, setProvider] = useState<string>("grok");
  const [model, setModel] = useState<string>("");
  const [chatProvider, setChatProvider] = useState("grok");
  const [chatModel, setChatModel] = useState("");
  const [agentProvider, setAgentProvider] = useState("grok");
  const [agentModel, setAgentModel] = useState("");
  const [orchProvider, setOrchProvider] = useState("grok");
  const [orchModel, setOrchModel] = useState("");
  const [fairBaseUrl, setFairBaseUrl] = useState("https://fair-hyperion.dev.k8s.erg.kz/api/hyperion/openai/v1");
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState("http://127.0.0.1:11434");
  const [ollamaRuntimeMode, setOllamaRuntimeMode] = useState("auto");
  const [ollamaCloudEnabled, setOllamaCloudEnabled] = useState(false);
  const [ollamaCloudBaseUrl, setOllamaCloudBaseUrl] = useState("https://ollama.com");
  const [ollamaThinkMode, setOllamaThinkMode] = useState<string>(AUTO_OLLAMA_THINKING_VALUE);
  const [refreshingPurpose, setRefreshingPurpose] = useState<string | null>(null);
  const [reasoningEffort, setReasoningEffort] = useState<string>(AUTO_REASONING_VALUE);
  const [refreshing, setRefreshing] = useState(false);
  const [apiKeyDrafts, setApiKeyDrafts] = useState<Record<string, string>>({});
  const [savingApiKey, setSavingApiKey] = useState<string | null>(null);

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
    setFairBaseUrl(config.fair_base_url || "https://fair-hyperion.dev.k8s.erg.kz/api/hyperion/openai/v1");
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

  const getModelsForProvider = useCallback((nextProvider: string): string[] => {
    if (!modelsData) return [];
    if (nextProvider === "gemini") return modelsData.gemini || [];
    if (nextProvider === "openai") return modelsData.openai || [];
    if (nextProvider === "fair") return modelsData.fair || [];
    if (nextProvider === "claude") return modelsData.claude || [];
    if (nextProvider === "ollama") {
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

  const onRefreshPurpose = useCallback(async (nextProvider: string) => {
    setRefreshingPurpose(nextProvider);
    try {
      await refreshModels(nextProvider as RefreshableProvider);
      await queryClient.invalidateQueries({ queryKey: ["settings", "models"] });
    } finally {
      setRefreshingPurpose(null);
    }
  }, [queryClient]);

  const onSavePurpose = useCallback(async () => {
    setSaving(true);
    try {
      await saveSettings({
        chat_llm_provider: chatProvider,
        chat_llm_model: chatModel,
        agent_llm_provider: agentProvider,
        agent_llm_model: agentModel,
        orchestrator_llm_provider: orchProvider,
        orchestrator_llm_model: orchModel,
        internal_llm_provider: chatProvider,
        fair_base_url: fairBaseUrl,
        ollama_base_url: ollamaBaseUrl,
        ollama_runtime_mode: ollamaRuntimeMode,
        ollama_cloud_enabled: ollamaCloudEnabled,
        ollama_cloud_base_url: ollamaCloudBaseUrl,
        ollama_think_mode: ollamaThinkMode === AUTO_OLLAMA_THINKING_VALUE ? "" : ollamaThinkMode,
        openai_reasoning_effort: reasoningEffort === AUTO_REASONING_VALUE ? "" : reasoningEffort,
      });
      await queryClient.invalidateQueries({ queryKey: ["settings", "config"] });
    } finally {
      setSaving(false);
    }
  }, [
    agentModel,
    agentProvider,
    chatModel,
    chatProvider,
    fairBaseUrl,
    ollamaBaseUrl,
    ollamaCloudBaseUrl,
    ollamaCloudEnabled,
    ollamaRuntimeMode,
    ollamaThinkMode,
    orchModel,
    orchProvider,
    queryClient,
    reasoningEffort,
    setSaving,
  ]);

  const onSave = useCallback(async () => {
    setSaving(true);
    try {
      const isLlmProvider = LLM_PROVIDER_VALUES.includes(provider);
      const payload: Record<string, unknown> = {
        default_provider: provider,
        fair_base_url: fairBaseUrl,
        ollama_base_url: ollamaBaseUrl,
        ollama_runtime_mode: ollamaRuntimeMode,
        ollama_cloud_enabled: ollamaCloudEnabled,
        ollama_cloud_base_url: ollamaCloudBaseUrl,
        ollama_think_mode: ollamaThinkMode === AUTO_OLLAMA_THINKING_VALUE ? "" : ollamaThinkMode,
      };
      if (provider === "gemini") payload.chat_model_gemini = model;
      if (provider === "grok") payload.chat_model_grok = model;
      if (provider === "openai") payload.chat_model_openai = model;
      if (provider === "fair") payload.chat_model_fair = model;
      if (provider === "claude") payload.chat_model_claude = model;
      if (provider === "ollama") payload.chat_model_ollama = model;
      if (isLlmProvider) {
        payload.internal_llm_provider = provider;
        payload.gemini_enabled = provider === "gemini";
        payload.grok_enabled = provider === "grok";
        payload.openai_enabled = provider === "openai";
        payload.fair_enabled = provider === "fair";
        payload.claude_enabled = provider === "claude";
        payload.ollama_enabled = provider === "ollama";
      }
      await saveSettings(payload);
      await queryClient.invalidateQueries({ queryKey: ["settings", "config"] });
    } finally {
      setSaving(false);
    }
  }, [
    fairBaseUrl,
    model,
    ollamaBaseUrl,
    ollamaCloudBaseUrl,
    ollamaCloudEnabled,
    ollamaRuntimeMode,
    ollamaThinkMode,
    provider,
    queryClient,
    setSaving,
  ]);

  const onSaveOllama = useCallback(async () => {
    setSaving(true);
    try {
      await saveSettings({
        fair_base_url: fairBaseUrl,
        ollama_base_url: ollamaBaseUrl,
        ollama_runtime_mode: ollamaRuntimeMode,
        ollama_cloud_enabled: ollamaCloudEnabled,
        ollama_cloud_base_url: ollamaCloudBaseUrl,
        ollama_think_mode: ollamaThinkMode === AUTO_OLLAMA_THINKING_VALUE ? "" : ollamaThinkMode,
        openai_reasoning_effort: reasoningEffort === AUTO_REASONING_VALUE ? "" : reasoningEffort,
      });
      await queryClient.invalidateQueries({ queryKey: ["settings", "config"] });
    } finally {
      setSaving(false);
    }
  }, [
    fairBaseUrl,
    ollamaBaseUrl,
    ollamaCloudBaseUrl,
    ollamaCloudEnabled,
    ollamaRuntimeMode,
    ollamaThinkMode,
    queryClient,
    reasoningEffort,
    setSaving,
  ]);

  const onRefreshModels = useCallback(async () => {
    setRefreshing(true);
    try {
      await refreshModels(provider as RefreshableProvider);
      await queryClient.invalidateQueries({ queryKey: ["settings", "models"] });
    } finally {
      setRefreshing(false);
    }
  }, [provider, queryClient]);

  const setApiKeyDraft = useCallback((providerKey: string, value: string) => {
    setApiKeyDrafts((current) => ({ ...current, [providerKey]: value }));
  }, []);

  const onSaveApiKey = useCallback(async (providerKey: string) => {
    const value = (apiKeyDrafts[providerKey] || "").trim();
    if (!value) return;
    setSavingApiKey(providerKey);
    try {
      await saveSettings({ api_keys: { [providerKey]: value } });
      setApiKeyDrafts((current) => ({ ...current, [providerKey]: "" }));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["settings", "config"] }),
        queryClient.invalidateQueries({ queryKey: ["settings", "models"] }),
      ]);
    } finally {
      setSavingApiKey(null);
    }
  }, [apiKeyDrafts, queryClient]);

  const onClearApiKey = useCallback(async (providerKey: string) => {
    setSavingApiKey(providerKey);
    try {
      await saveSettings({ clear_api_keys: [providerKey] });
      setApiKeyDrafts((current) => ({ ...current, [providerKey]: "" }));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["settings", "config"] }),
        queryClient.invalidateQueries({ queryKey: ["settings", "models"] }),
      ]);
    } finally {
      setSavingApiKey(null);
    }
  }, [queryClient]);

  const savedActiveProvider = useMemo(() => {
    if (!currentConfig) return "grok";
    return LLM_PROVIDER_VALUES.includes(currentConfig.internal_llm_provider || "")
      ? currentConfig.internal_llm_provider
      : LLM_PROVIDER_VALUES.includes(currentConfig.default_provider || "")
        ? currentConfig.default_provider
        : "grok";
  }, [currentConfig]);

  const routeConfigs = useMemo<RouteModelConfig[]>(() => [
    {
      key: "chat",
      shortLabel: "Chat",
      label: "Чат / терминал",
      description: "Быстрые ответы и подсказки в терминале",
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
      label: "Пайплайны",
      description: "Планирование и координация запусков",
      icon: Workflow,
      provider: orchProvider,
      model: orchModel,
    },
  ], [agentModel, agentProvider, chatModel, chatProvider, orchModel, orchProvider]);

  const uniqueRouteProviders = useMemo(
    () => Array.from(new Set(routeConfigs.map((route) => route.provider))),
    [routeConfigs],
  );
  const ollamaLocalModels = modelsData?.ollama_local || [];
  const ollamaCloudModels = modelsData?.ollama_cloud || [];
  const ollamaCatalogModels = getModelsForProvider("ollama");
  const ollamaRoutingActive = provider === "ollama" || routeConfigs.some((route) => route.provider === "ollama");
  const openAiRoutingActive = provider === "openai" || routeConfigs.some((route) => route.provider === "openai");
  const ollamaRuntimeSummary =
    ollamaRuntimeMode === "cloud"
      ? "Только облако"
      : ollamaRuntimeMode === "local"
        ? "Только локально"
        : "Авто";

  const providerOverview = useMemo<ProviderOverviewItem[]>(() => {
    if (!currentConfig) return [];
    return LLM_PROVIDERS.map((providerOption) => {
      const catalogSize = getModelsForProvider(providerOption.value).length;
      const activeRoutes = routeConfigs
        .filter((route) => route.provider === providerOption.value)
        .map((route) => route.shortLabel);
      return {
        ...providerOption,
        catalogSize,
        activeRoutes,
        enabled: getProviderEnabled(currentConfig, providerOption.value),
        configured: Boolean(apiKeys?.[PROVIDER_API_STATUS_KEY[providerOption.value]]),
        isSelected: provider === providerOption.value,
      };
    });
  }, [apiKeys, currentConfig, getModelsForProvider, provider, routeConfigs]);

  const aiDraftDirty = Boolean(currentConfig) && (
    provider !== savedActiveProvider ||
    model !== getSavedModelForProvider(currentConfig as SettingsConfig, provider) ||
    chatProvider !== ((currentConfig as SettingsConfig).chat_llm_provider || savedActiveProvider) ||
    chatModel !== ((currentConfig as SettingsConfig).chat_llm_model || "") ||
    agentProvider !== ((currentConfig as SettingsConfig).agent_llm_provider || savedActiveProvider) ||
    agentModel !== ((currentConfig as SettingsConfig).agent_llm_model || "") ||
    orchProvider !== ((currentConfig as SettingsConfig).orchestrator_llm_provider || savedActiveProvider) ||
    orchModel !== ((currentConfig as SettingsConfig).orchestrator_llm_model || "") ||
    fairBaseUrl !== ((currentConfig as SettingsConfig).fair_base_url || "https://fair-hyperion.dev.k8s.erg.kz/api/hyperion/openai/v1") ||
    ollamaBaseUrl !== ((currentConfig as SettingsConfig).ollama_base_url || "http://127.0.0.1:11434") ||
    ollamaRuntimeMode !== ((currentConfig as SettingsConfig).ollama_runtime_mode || "auto") ||
    ollamaCloudEnabled !== Boolean((currentConfig as SettingsConfig).ollama_cloud_enabled) ||
    ollamaCloudBaseUrl !== ((currentConfig as SettingsConfig).ollama_cloud_base_url || "https://ollama.com") ||
    ollamaThinkMode !== ((currentConfig as SettingsConfig).ollama_think_mode || AUTO_OLLAMA_THINKING_VALUE) ||
    reasoningEffort !== ((currentConfig as SettingsConfig).openai_reasoning_effort || AUTO_REASONING_VALUE)
  );
  const configuredProviderCount = providerOverview.filter((providerItem) => providerItem.configured).length;

  return {
    provider,
    model,
    chatProvider,
    chatModel,
    agentProvider,
    agentModel,
    orchProvider,
    orchModel,
    fairBaseUrl,
    ollamaBaseUrl,
    ollamaRuntimeMode,
    ollamaCloudEnabled,
    ollamaCloudBaseUrl,
    ollamaThinkMode,
    refreshingPurpose,
    reasoningEffort,
    refreshing,
    saving,
    apiKeyDrafts,
    savingApiKey,
    availableModels,
    routeConfigs,
    uniqueRouteProviders,
    ollamaLocalModels,
    ollamaCloudModels,
    ollamaCatalogModels,
    ollamaRoutingActive,
    openAiRoutingActive,
    ollamaRuntimeSummary,
    providerOverview,
    aiDraftDirty,
    configuredProviderCount,
    setModel,
    setChatProvider,
    setChatModel,
    setAgentProvider,
    setAgentModel,
    setOrchProvider,
    setOrchModel,
    setFairBaseUrl,
    setOllamaBaseUrl,
    setOllamaRuntimeMode,
    setOllamaCloudEnabled,
    setOllamaCloudBaseUrl,
    setOllamaThinkMode,
    setReasoningEffort,
    getModelsForProvider,
    getSuggestedModelForProvider,
    handleDefaultProviderChange,
    applyDefaultToAll,
    fillMissingModels,
    resetAiDraft,
    onRefreshPurpose,
    onSavePurpose,
    onSave,
    onSaveOllama,
    onRefreshModels,
    setApiKeyDraft,
    onSaveApiKey,
    onClearApiKey,
  };
}
