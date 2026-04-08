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
  Sparkles,
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
  fetchFrontendBootstrap,
  fetchModels,
  fetchServerMemoryOverview,
  fetchSettings,
  fetchSettingsActivity,
  promoteServerMemorySnapshotToNote,
  promoteServerMemorySnapshotToSkill,
  refreshModels,
  runServerMemoryDreams,
  saveSettings,
  archiveServerMemorySnapshot,
  fetchAuthSession,
  updateServerMemoryPolicy,
  type FrontendServer,
  type ServerMemoryOverviewResponse,
  type ServerMemorySnapshotRecord,
  type SettingsConfig,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { SettingsWorkspace } from "@/components/settings/SettingsWorkspace";

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
    <section className="overflow-hidden rounded-xl border border-border/70 bg-card">
      <div className="flex flex-col gap-4 border-b border-border/60 bg-secondary/15 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg bg-background/80 text-muted-foreground">
            <Icon className="h-3.5 w-3.5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-foreground">{title}</h2>
            {description ? <p className="mt-1 text-sm leading-6 text-muted-foreground">{description}</p> : null}
          </div>
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      <div className="p-5">{children}</div>
    </section>
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
    <div className="space-y-3 rounded-xl border border-border/70 bg-background/40 p-4">
      <div className="flex items-center gap-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-background text-muted-foreground">
          <Icon className="h-3.5 w-3.5" />
        </div>
        <div>
          <p className="text-xs font-medium text-foreground">{label}</p>
          <p className="text-[11px] text-muted-foreground">{description}</p>
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
        <Button size="sm" variant="ghost" className="h-7 justify-start px-2 text-[11px] text-muted-foreground" onClick={onRefresh} disabled={refreshing}>
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
type SettingsTabValue = "ai" | "access" | "memory" | "logging" | "activity";

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

  const { data: frontendBootstrap } = useQuery({
    queryKey: ["settings", "memory", "servers"],
    queryFn: fetchFrontendBootstrap,
    enabled: isAdmin,
    staleTime: 60_000,
  });
  const memoryServers = frontendBootstrap?.servers || [];
  const [selectedMemoryServerId, setSelectedMemoryServerId] = useState<number | null>(null);
  const [memoryDreamRunning, setMemoryDreamRunning] = useState(false);
  const [memoryPolicySaving, setMemoryPolicySaving] = useState(false);
  const [memoryActionKey, setMemoryActionKey] = useState<string | null>(null);
  const [memoryPolicyDraft, setMemoryPolicyDraft] = useState<ServerMemoryOverviewResponse["policy"] | null>(null);

  useEffect(() => {
    if (!isAdmin) return;
    if (selectedMemoryServerId) return;
    const firstServer = memoryServers[0];
    if (firstServer) {
      setSelectedMemoryServerId(firstServer.id);
    }
  }, [isAdmin, memoryServers, selectedMemoryServerId]);

  const {
    data: memoryOverview,
    isLoading: memoryLoading,
    refetch: refetchMemoryOverview,
  } = useQuery({
    queryKey: ["settings", "memory", "overview", selectedMemoryServerId],
    queryFn: () => fetchServerMemoryOverview(selectedMemoryServerId as number),
    enabled: isAdmin && Boolean(selectedMemoryServerId),
    staleTime: 20_000,
  });

  useEffect(() => {
    if (!memoryOverview) return;
    setMemoryPolicyDraft(memoryOverview.policy);
  }, [memoryOverview]);

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

  const selectedMemoryServer = useMemo(
    () => memoryServers.find((server) => server.id === selectedMemoryServerId) || null,
    [memoryServers, selectedMemoryServerId],
  );

  const refreshMemoryOverview = useCallback(async () => {
    if (!selectedMemoryServerId) return;
    await queryClient.invalidateQueries({ queryKey: ["settings", "memory", "overview", selectedMemoryServerId] });
    await refetchMemoryOverview();
  }, [queryClient, refetchMemoryOverview, selectedMemoryServerId]);

  const onRunMemoryDreams = useCallback(async () => {
    if (!selectedMemoryServerId) return;
    setMemoryDreamRunning(true);
    try {
      await runServerMemoryDreams(selectedMemoryServerId, { job_kind: "hybrid" });
      await refreshMemoryOverview();
    } finally {
      setMemoryDreamRunning(false);
    }
  }, [refreshMemoryOverview, selectedMemoryServerId]);

  const onSaveMemoryPolicy = useCallback(async () => {
    if (!selectedMemoryServerId || !memoryPolicyDraft) return;
    setMemoryPolicySaving(true);
    try {
      await updateServerMemoryPolicy(selectedMemoryServerId, memoryPolicyDraft);
      await refreshMemoryOverview();
    } finally {
      setMemoryPolicySaving(false);
    }
  }, [memoryPolicyDraft, refreshMemoryOverview, selectedMemoryServerId]);

  const onArchiveMemorySnapshot = useCallback(async (snapshotId: number) => {
    if (!selectedMemoryServerId) return;
    setMemoryActionKey(`archive:${snapshotId}`);
    try {
      await archiveServerMemorySnapshot(selectedMemoryServerId, snapshotId);
      await refreshMemoryOverview();
    } finally {
      setMemoryActionKey(null);
    }
  }, [refreshMemoryOverview, selectedMemoryServerId]);

  const onPromoteMemorySnapshotToNote = useCallback(async (snapshotId: number) => {
    if (!selectedMemoryServerId) return;
    setMemoryActionKey(`note:${snapshotId}`);
    try {
      await promoteServerMemorySnapshotToNote(selectedMemoryServerId, snapshotId);
      await refreshMemoryOverview();
    } finally {
      setMemoryActionKey(null);
    }
  }, [refreshMemoryOverview, selectedMemoryServerId]);

  const onPromoteMemorySnapshotToSkill = useCallback(async (snapshotId: number) => {
    if (!selectedMemoryServerId) return;
    setMemoryActionKey(`skill:${snapshotId}`);
    try {
      await promoteServerMemorySnapshotToSkill(selectedMemoryServerId, snapshotId);
      await refreshMemoryOverview();
    } finally {
      setMemoryActionKey(null);
    }
  }, [refreshMemoryOverview, selectedMemoryServerId]);

  const renderMemorySnapshotAudit = useCallback((item: ServerMemorySnapshotRecord) => (
    <div className="mt-3 space-y-2 text-[10px] text-muted-foreground">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-secondary px-1.5 py-0.5">{item.source_kind}</span>
        {item.source_ref ? <span className="rounded bg-secondary/60 px-1.5 py-0.5">{item.source_ref}</span> : null}
        <span>confidence {Math.round((item.confidence || 0) * 100)}%</span>
        <span>importance {item.importance_score}</span>
        <span>stability {item.stability_score}</span>
        {item.created_by_username ? <span>by {item.created_by_username}</span> : null}
        {item.updated_at ? <span>{new Date(item.updated_at).toLocaleString()}</span> : null}
      </div>
      {item.action_summary ? <p className="text-[11px] text-foreground/80">{item.action_summary}</p> : null}
      {item.rewrite_reason ? <p>Reason: {item.rewrite_reason}</p> : null}
      {item.prior_version ? <p>Prior version: v{item.prior_version}</p> : null}
      {item.history.length > 1 ? (
        <details className="rounded-md border border-border/60 bg-background/30 px-3 py-2">
          <summary className="cursor-pointer text-[11px] font-medium text-foreground">
            Version history ({item.history.length})
          </summary>
          <div className="mt-2 space-y-2">
            {item.history.map((historyItem) => (
              <div key={historyItem.id} className="rounded border border-border/50 bg-secondary/10 px-2 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={historyItem.is_active ? "secondary" : "outline"}>v{historyItem.version}</Badge>
                  {historyItem.source_kind ? <span>{historyItem.source_kind}</span> : null}
                  {historyItem.source_ref ? <span>{historyItem.source_ref}</span> : null}
                  {historyItem.created_by_username ? <span>by {historyItem.created_by_username}</span> : null}
                  {historyItem.updated_at ? <span>{new Date(historyItem.updated_at).toLocaleString()}</span> : null}
                </div>
                {historyItem.action_summary ? <p className="mt-1 text-[11px] text-foreground/80">{historyItem.action_summary}</p> : null}
                {historyItem.rewrite_reason ? <p className="mt-1">Reason: {historyItem.rewrite_reason}</p> : null}
                {historyItem.content_preview ? (
                  <p className="mt-1 whitespace-pre-wrap text-[11px] leading-relaxed">{historyItem.content_preview}</p>
                ) : null}
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  ), []);

  const renderWorkerStateCard = useCallback((label: string, state: ServerMemoryOverviewResponse["daemon_state"] | undefined) => {
    if (!state) return null;
    const statusTone =
      state.status === "running"
        ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
        : state.status === "error"
          ? "bg-destructive/10 text-destructive border-destructive/30"
          : "bg-secondary text-muted-foreground border-border";
    return (
      <div key={`${label}-${state.worker_key}`} className="rounded-lg border border-border bg-secondary/10 px-3 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium text-foreground">{label}</p>
          <span className={cn("rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide", statusTone)}>
            {state.status}
          </span>
          {state.is_stale ? <Badge variant="destructive">stale</Badge> : null}
        </div>
        <div className="mt-2 space-y-1 text-xs text-muted-foreground">
          {state.command ? <p className="truncate">cmd: {state.command}</p> : null}
          <p>worker: {state.worker_key}</p>
          {state.hostname ? <p>host: {state.hostname}</p> : null}
          {state.pid ? <p>pid: {state.pid}</p> : null}
          {state.heartbeat_at ? <p>heartbeat: {new Date(state.heartbeat_at).toLocaleString()}</p> : null}
          {state.last_cycle_finished_at ? <p>last cycle: {new Date(state.last_cycle_finished_at).toLocaleString()}</p> : null}
          {state.last_error ? <p className="text-destructive">error: {state.last_error}</p> : null}
          {Object.keys(state.last_summary || {}).length ? (
            <details className="rounded border border-border/50 bg-background/30 px-2 py-2">
              <summary className="cursor-pointer text-[11px] font-medium text-foreground">Last summary</summary>
              <pre className="mt-2 whitespace-pre-wrap text-[10px] leading-relaxed text-muted-foreground">
                {JSON.stringify(state.last_summary, null, 2)}
              </pre>
            </details>
          ) : null}
        </div>
      </div>
    );
  }, []);

  const renderMemoryCandidateActions = useCallback((item: ServerMemorySnapshotRecord) => (
    <div className="mt-3 flex flex-wrap gap-2">
      <Button
        size="sm"
        variant="outline"
        className="h-7 px-3 text-xs"
        disabled={memoryActionKey === `note:${item.id}`}
        onClick={() => void onPromoteMemorySnapshotToNote(item.id)}
      >
        {memoryActionKey === `note:${item.id}` ? "Promoting..." : "Promote Note"}
      </Button>
      {item.memory_key.startsWith("skill_draft:") ? (
        <Button
          size="sm"
          variant="outline"
          className="h-7 px-3 text-xs"
          disabled={memoryActionKey === `skill:${item.id}`}
          onClick={() => void onPromoteMemorySnapshotToSkill(item.id)}
        >
          {memoryActionKey === `skill:${item.id}` ? "Promoting..." : "Promote Skill"}
        </Button>
      ) : null}
      <Button
        size="sm"
        variant="outline"
        className="h-7 px-3 text-xs text-destructive border-destructive/30 hover:bg-destructive/10"
        disabled={memoryActionKey === `archive:${item.id}`}
        onClick={() => void onArchiveMemorySnapshot(item.id)}
      >
        {memoryActionKey === `archive:${item.id}` ? "Archiving..." : "Archive"}
      </Button>
    </div>
  ), [memoryActionKey, onArchiveMemorySnapshot, onPromoteMemorySnapshotToNote, onPromoteMemorySnapshotToSkill]);

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
    if (activeTab === "logging" || activeTab === "activity" || activeTab === "memory") {
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
            value: "memory" as const,
            label: "AI Memory",
            description: "Dreams, snapshots и learned operational patterns",
            icon: ScrollText,
            badge: memoryOverview ? String(memoryOverview.stats.canonical + memoryOverview.stats.patterns) : undefined,
          },
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
    <SettingsWorkspace
      title={t("settings.title")}
      description="Главные системные параметры платформы: AI-маршрутизация, доступы, аудит и рабочий журнал без лишней визуальной перегрузки."
      asideHint="Начинай с общей AI-схемы и доступов. Логирование и журнал нужны для контроля, но не должны мешать основному рабочему потоку."
      actions={
        <>
          <Badge variant="outline">{activeTabMeta.label}</Badge>
          <Badge variant="secondary">{configuredProviderCount} провайдера готово</Badge>
          {aiDraftDirty ? <Badge>Есть AI-черновик</Badge> : <Badge variant="outline">Все сохранено</Badge>}
        </>
      }
    >
      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as SettingsTabValue)} className="space-y-5">
        <div className="workspace-subtle rounded-xl px-4 py-3 text-sm leading-6 text-muted-foreground">
          Держи настройки простыми: один основной провайдер, отдельные роли только там, где это действительно нужно, и минимум точечных исключений в доступах.
        </div>

        <TabsList className={cn(
          "grid h-auto w-full grid-cols-1 gap-1 rounded-xl border border-border/60 bg-card p-1 md:grid-cols-2",
          isAdmin ? "xl:grid-cols-5" : "xl:grid-cols-2",
        )}>
            {settingsTabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <TabsTrigger
                  key={tab.value}
                  value={tab.value}
                  className="gap-1.5 whitespace-nowrap rounded-lg px-3 py-2 data-[state=active]:bg-background"
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
          <div className="flex flex-col gap-3 rounded-2xl border border-border/60 bg-secondary/20 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
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
              <Badge variant="outline">{uniqueRouteProviders.length > 1 ? "Раздельная маршрутизация" : "Один провайдер на все роли"}</Badge>
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
                      "rounded-2xl border px-4 py-3 text-left transition-colors",
                      providerItem.isSelected
                        ? "border-primary/40 bg-primary/5"
                        : "border-border/60 bg-secondary/15 hover:border-border hover:bg-secondary/35"
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground">{providerItem.label}</p>
                        <p className="text-[11px] text-muted-foreground">
                          {providerItem.catalogSize ? `${providerItem.catalogSize} моделей` : "Каталог пуст, доступен ручной ввод"}
                        </p>
                      </div>
                      {providerItem.isSelected ? <Badge className="shrink-0">Основной</Badge> : null}
                    </div>
                    <div className="mt-3 flex items-center gap-2 text-[11px] text-muted-foreground">
                      <span className={cn("h-2 w-2 rounded-full", providerItem.configured ? "bg-emerald-400" : "bg-amber-400")} />
                      <span>{providerItem.configured ? "Готов к использованию" : "Нужна настройка"}</span>
                    </div>
                    <p className="mt-2 text-[11px] text-muted-foreground">
                      {providerItem.activeRoutes.length > 0
                        ? `Маршруты: ${providerItem.activeRoutes.join(", ")}`
                        : "Отдельные роли пока не используют этот провайдер"}
                    </p>
                  </button>
                ))}
              </div>

              <div className="space-y-4 rounded-2xl border border-border/60 bg-secondary/15 p-4">
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

                <div className="flex flex-col gap-2 rounded-xl border border-border/60 bg-background/40 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
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
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-end gap-2">
                  <Button size="sm" variant="ghost" className="gap-1.5" onClick={onRefreshModels} disabled={refreshing}>
                    <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} /> Обновить каталог
                  </Button>
                  <Button size="sm" className="gap-1.5" onClick={onSave} disabled={saving}>
                    <Save className="h-3.5 w-3.5" /> {saving ? "Сохранение..." : "Сохранить основную"}
                  </Button>
                </div>
              </div>
            </div>
          </SectionCard>

          <SectionCard title="Маршруты по ролям" icon={Cpu} description="Отдельные пары провайдер/модель для чата, агентов и pipeline-оркестратора">
            <div className="space-y-4">
              <div className="flex flex-col gap-3 rounded-2xl border border-border/60 bg-secondary/20 p-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="space-y-1">
                  <p className="text-xs font-medium text-foreground">Быстрые действия</p>
                  <p className="text-[11px] text-muted-foreground">
                    Можно скопировать основную модель в роли, дозаполнить пустые поля или откатить AI-черновик к сохраненному состоянию.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="secondary" className="gap-1.5" onClick={applyDefaultToAll}>
                    <Bot className="h-3.5 w-3.5" /> Копировать основную
                  </Button>
                  <Button size="sm" variant="secondary" className="gap-1.5" onClick={fillMissingModels}>
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
          <SectionCard title="Настройки доступа" icon={Shield} description="Три понятных шага: пользователи, группы, затем точечные исключения.">
            <div className="workspace-subtle rounded-xl px-4 py-3 text-sm leading-6 text-muted-foreground">
              Базовую модель прав лучше собирать через профили и группы. Раздел разрешений используй только там, где действительно нужно сделать исключение.
            </div>

            <div className="mt-4 overflow-hidden rounded-xl border border-border/70">
              {[
                { title: "Пользователи", desc: "Аккаунты, профили доступа и группы пользователя", icon: Users, url: "/settings/users" },
                { title: "Группы", desc: "Команды, участники и общая политика доступа", icon: FolderOpen, url: "/settings/groups" },
                { title: "Разрешения", desc: "Точечные allow/deny правила для исключений", icon: Shield, url: "/settings/permissions" },
              ].map((page, index, pages) => (
                <Link
                  key={page.url}
                  to={page.url}
                  className={cn(
                    "group flex items-center gap-4 bg-card px-4 py-4 transition-colors hover:bg-secondary/30",
                    index < pages.length - 1 && "border-b border-border/70",
                  )}
                >
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-background">
                    <page.icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-foreground">{page.title}</p>
                    <p className="mt-0.5 text-sm text-muted-foreground">{page.desc}</p>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground" aria-hidden="true" />
                </Link>
              ))}
            </div>
          </SectionCard>
        </TabsContent>

        {/* ==================== MEMORY TAB ==================== */}
        {isAdmin && (
          <TabsContent value="memory" className="space-y-4">
            <SectionCard
              title="AI Memory и Dreams"
              icon={ScrollText}
              description="Админская зона для настройки снов, canonical snapshots и learned operational patterns."
              actions={
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="gap-1.5 h-7"
                    onClick={() => void refreshMemoryOverview()}
                    disabled={!selectedMemoryServerId || memoryLoading}
                  >
                    <RefreshCw className={cn("h-3 w-3", memoryLoading && "animate-spin")} />
                    Обновить
                  </Button>
                  <Button
                    size="sm"
                    className="gap-1.5 h-7"
                    onClick={() => void onRunMemoryDreams()}
                    disabled={!selectedMemoryServerId || memoryDreamRunning}
                  >
                    <Sparkles className={cn("h-3 w-3", memoryDreamRunning && "animate-spin")} />
                    {memoryDreamRunning ? "Dreaming..." : "Run Dreams Now"}
                  </Button>
                </div>
              }
            >
              <div className="space-y-4">
                <div className="grid gap-3 lg:grid-cols-[minmax(0,240px)_minmax(0,1fr)]">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Сервер</Label>
                    <Select
                      value={selectedMemoryServerId ? String(selectedMemoryServerId) : ""}
                      onValueChange={(value) => setSelectedMemoryServerId(Number(value))}
                    >
                      <SelectTrigger className="h-9">
                        <SelectValue placeholder="Выбери сервер" />
                      </SelectTrigger>
                      <SelectContent>
                        {memoryServers.map((server: FrontendServer) => (
                          <SelectItem key={server.id} value={String(server.id)}>
                            {server.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="rounded-xl border border-border/60 bg-secondary/15 px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{selectedMemoryServer?.name || "Сервер не выбран"}</Badge>
                      <Badge
                        variant={memoryOverview?.daemon_state?.status === "running" ? "default" : "secondary"}
                      >
                        Dreams daemon: {memoryOverview?.daemon_state?.status || "unknown"}
                      </Badge>
                      {memoryOverview?.daemon_state?.is_stale ? (
                        <Badge variant="outline">Lease stale</Badge>
                      ) : null}
                    </div>
                    <p className="mt-2 text-[11px] text-muted-foreground">
                      Здесь живут только системные AI memory controls. Пользовательские текстовые заметки остаются в карточке сервера.
                    </p>
                    {memoryOverview?.daemon_state?.heartbeat_at ? (
                      <p className="mt-1 text-[11px] text-muted-foreground">
                        Heartbeat: {new Date(memoryOverview.daemon_state.heartbeat_at).toLocaleString()}
                      </p>
                    ) : null}
                  </div>
                </div>

                {memoryPolicyDraft ? (
                  <div className="rounded-xl border border-border/60 bg-background/40 p-4 space-y-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <p className="text-sm font-medium text-foreground">Dream Policy</p>
                        <p className="text-xs text-muted-foreground">
                          Управляет nearline compaction, nightly distillation и тем, что реально попадает в server brain.
                        </p>
                      </div>
                      <Button
                        size="sm"
                        className="h-8 px-4"
                        onClick={() => void onSaveMemoryPolicy()}
                        disabled={memoryPolicySaving || !selectedMemoryServerId}
                      >
                        <Save className="mr-1 h-3 w-3" />
                        {memoryPolicySaving ? "Saving..." : "Save Memory Policy"}
                      </Button>
                    </div>

                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                      <div className="space-y-1.5">
                        <Label className="text-xs">Dream mode</Label>
                        <Select
                          value={memoryPolicyDraft.dream_mode}
                          onValueChange={(value) =>
                            setMemoryPolicyDraft((current) => current ? { ...current, dream_mode: value } : current)
                          }
                        >
                          <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="heuristic">Heuristic</SelectItem>
                            <SelectItem value="nightly_llm">Nightly LLM</SelectItem>
                            <SelectItem value="hybrid">Hybrid</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs">Nightly model</Label>
                        <Input
                          value={memoryPolicyDraft.nightly_model_alias}
                          onChange={(event) =>
                            setMemoryPolicyDraft((current) =>
                              current ? { ...current, nightly_model_alias: event.target.value } : current,
                            )
                          }
                          className="h-9"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs">Nearline threshold</Label>
                        <Input
                          type="number"
                          min={2}
                          max={50}
                          value={memoryPolicyDraft.nearline_event_threshold}
                          onChange={(event) =>
                            setMemoryPolicyDraft((current) =>
                              current
                                ? { ...current, nearline_event_threshold: Number(event.target.value || 2) }
                                : current,
                            )
                          }
                          className="h-9"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs">Sleep start</Label>
                        <Input
                          type="number"
                          min={0}
                          max={23}
                          value={memoryPolicyDraft.sleep_start_hour}
                          onChange={(event) =>
                            setMemoryPolicyDraft((current) =>
                              current ? { ...current, sleep_start_hour: Number(event.target.value || 0) } : current,
                            )
                          }
                          className="h-9"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs">Sleep end</Label>
                        <Input
                          type="number"
                          min={0}
                          max={23}
                          value={memoryPolicyDraft.sleep_end_hour}
                          onChange={(event) =>
                            setMemoryPolicyDraft((current) =>
                              current ? { ...current, sleep_end_hour: Number(event.target.value || 0) } : current,
                            )
                          }
                          className="h-9"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs">Raw retention</Label>
                        <Input
                          type="number"
                          min={7}
                          max={365}
                          value={memoryPolicyDraft.raw_event_retention_days}
                          onChange={(event) =>
                            setMemoryPolicyDraft((current) =>
                              current
                                ? { ...current, raw_event_retention_days: Number(event.target.value || 7) }
                                : current,
                            )
                          }
                          className="h-9"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs">Episode retention</Label>
                        <Input
                          type="number"
                          min={14}
                          max={365}
                          value={memoryPolicyDraft.episode_retention_days}
                          onChange={(event) =>
                            setMemoryPolicyDraft((current) =>
                              current
                                ? { ...current, episode_retention_days: Number(event.target.value || 14) }
                                : current,
                            )
                          }
                          className="h-9"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                      <label className="flex items-center gap-2 text-xs text-muted-foreground">
                        <input
                          type="checkbox"
                          checked={memoryPolicyDraft.is_enabled}
                          onChange={(event) =>
                            setMemoryPolicyDraft((current) =>
                              current ? { ...current, is_enabled: event.target.checked } : current,
                            )
                          }
                        />
                        AI memory enabled
                      </label>
                      <label className="flex items-center gap-2 text-xs text-muted-foreground">
                        <input
                          type="checkbox"
                          checked={memoryPolicyDraft.human_habits_capture_enabled}
                          onChange={(event) =>
                            setMemoryPolicyDraft((current) =>
                              current ? { ...current, human_habits_capture_enabled: event.target.checked } : current,
                            )
                          }
                        />
                        Human habits capture
                      </label>
                      <label className="flex items-center gap-2 text-xs text-muted-foreground">
                        <input
                          type="checkbox"
                          checked={memoryPolicyDraft.rdp_semantic_capture_enabled}
                          onChange={(event) =>
                            setMemoryPolicyDraft((current) =>
                              current ? { ...current, rdp_semantic_capture_enabled: event.target.checked } : current,
                            )
                          }
                        />
                        RDP semantic capture
                      </label>
                    </div>
                    <p className="mt-2 text-[11px] text-muted-foreground">
                      Если выключить AI memory, новый layered memory pipeline и dreams перестанут
                      собирать события. Останется старый формат: очень короткая автоматическая
                      выжимка после рабочей сессии.
                    </p>
                  </div>
                ) : null}

                {memoryOverview ? (
                  <>
                    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
                      <div className="rounded-lg border border-border bg-secondary/10 px-3 py-2">
                        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Canonical</p>
                        <p className="mt-1 text-lg font-semibold text-foreground">{memoryOverview.stats.canonical}</p>
                      </div>
                      <div className="rounded-lg border border-border bg-secondary/10 px-3 py-2">
                        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Patterns</p>
                        <p className="mt-1 text-lg font-semibold text-foreground">{memoryOverview.stats.patterns}</p>
                      </div>
                      <div className="rounded-lg border border-border bg-secondary/10 px-3 py-2">
                        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Automation</p>
                        <p className="mt-1 text-lg font-semibold text-foreground">{memoryOverview.stats.automation_candidates}</p>
                      </div>
                      <div className="rounded-lg border border-border bg-secondary/10 px-3 py-2">
                        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Skill Drafts</p>
                        <p className="mt-1 text-lg font-semibold text-foreground">{memoryOverview.stats.skill_drafts}</p>
                      </div>
                      <div className="rounded-lg border border-border bg-secondary/10 px-3 py-2">
                        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Revalidation</p>
                        <p className="mt-1 text-lg font-semibold text-foreground">{memoryOverview.stats.revalidation_open}</p>
                      </div>
                      <div className="rounded-lg border border-border bg-secondary/10 px-3 py-2">
                        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Episodes</p>
                        <p className="mt-1 text-lg font-semibold text-foreground">{memoryOverview.stats.episodes}</p>
                      </div>
                      <div className="rounded-lg border border-border bg-secondary/10 px-3 py-2">
                        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Archive</p>
                        <p className="mt-1 text-lg font-semibold text-foreground">{memoryOverview.stats.archive}</p>
                      </div>
                    </div>

                    <SectionCard
                      title="Worker status"
                      icon={Activity}
                      description="Состояние фоновых workers, которые крутят dreams, execution plane и watcher scans."
                    >
                      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
                        {renderWorkerStateCard("Memory dreams", memoryOverview.worker_states?.memory_dreams || memoryOverview.daemon_state)}
                        {renderWorkerStateCard("Agent execution", memoryOverview.worker_states?.agent_execution)}
                        {renderWorkerStateCard("Watchers", memoryOverview.worker_states?.watchers)}
                      </div>
                    </SectionCard>

                    {memoryOverview.canonical.length > 0 ? (
                      <SectionCard title="Canonical snapshots" icon={Database} description="Активная память сервера, которая реально уходит в prompt.">
                        <div className="space-y-2">
                          {memoryOverview.canonical.map((item) => (
                            <div key={item.id} className="rounded-lg border border-border bg-secondary/10 px-3 py-3">
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="text-sm font-medium text-foreground">{item.title}</p>
                                <Badge variant="secondary">{item.memory_key}</Badge>
                                <Badge variant="outline">v{item.version}</Badge>
                              </div>
                              <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{item.content}</p>
                              {renderMemorySnapshotAudit(item)}
                            </div>
                          ))}
                        </div>
                      </SectionCard>
                    ) : null}

                    {memoryOverview.patterns.length > 0 || memoryOverview.automation_candidates.length > 0 || memoryOverview.skill_drafts.length > 0 ? (
                      <SectionCard title="Learned candidates" icon={Bot} description="То, что dreams и pattern learning предлагают поднять в operational knowledge.">
                        <div className="space-y-3">
                          {[...memoryOverview.patterns, ...memoryOverview.automation_candidates, ...memoryOverview.skill_drafts].map((item) => (
                            <div key={item.id} className="rounded-lg border border-border bg-secondary/10 px-3 py-3">
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="text-sm font-medium text-foreground">{item.title}</p>
                                <Badge variant="secondary">{item.memory_key}</Badge>
                                <Badge variant="outline">v{item.version}</Badge>
                              </div>
                              <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{item.content}</p>
                              {renderMemorySnapshotAudit(item)}
                              {renderMemoryCandidateActions(item)}
                            </div>
                          ))}
                        </div>
                      </SectionCard>
                    ) : null}

                    {memoryOverview.revalidation.length > 0 ? (
                      <SectionCard title="Revalidation queue" icon={RefreshCw} description="Факты, которые снам нужно перепроверить или уточнить.">
                        <div className="space-y-2">
                          {memoryOverview.revalidation.map((item) => (
                            <div key={item.id} className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-3">
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="text-sm font-medium text-foreground">{item.title}</p>
                                <Badge variant="outline">{item.memory_key}</Badge>
                              </div>
                              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{item.reason}</p>
                            </div>
                          ))}
                        </div>
                      </SectionCard>
                    ) : null}

                    {memoryOverview.episodes.length > 0 ? (
                      <SectionCard title="Recent episodes" icon={Clock} description="Последние схлопнутые эпизоды из raw event inbox.">
                        <div className="space-y-2">
                          {memoryOverview.episodes.slice(0, 6).map((item) => (
                            <div key={item.id} className="rounded-lg border border-border bg-secondary/10 px-3 py-3">
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="text-sm font-medium text-foreground">{item.title}</p>
                                <Badge variant="secondary">{item.episode_kind}</Badge>
                                <Badge variant="outline">{item.event_count} events</Badge>
                              </div>
                              <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{item.summary}</p>
                            </div>
                          ))}
                        </div>
                      </SectionCard>
                    ) : null}

                    {memoryOverview.archive.length > 0 ? (
                      <SectionCard title="Archive" icon={FolderOpen} description="Старые и superseded memory artefacts, исключенные из prompt.">
                        <div className="space-y-2">
                          {memoryOverview.archive.slice(0, 6).map((item) => (
                            <div key={`${item.kind}-${item.id}`} className="rounded-lg border border-border/60 bg-secondary/5 px-3 py-3">
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="text-sm font-medium text-foreground">{item.title}</p>
                                <Badge variant="outline">{item.kind}</Badge>
                              </div>
                              <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                                {"content" in item ? item.content : item.summary}
                              </p>
                            </div>
                          ))}
                        </div>
                      </SectionCard>
                    ) : null}
                  </>
                ) : (
                  <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                    {selectedMemoryServerId ? "Загрузка memory overview..." : "Выбери сервер, чтобы увидеть AI memory настройки."}
                  </div>
                )}
              </div>
            </SectionCard>
          </TabsContent>
        )}

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
      </Tabs>
    </SettingsWorkspace>
  );
}
