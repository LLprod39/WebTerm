import { useCallback, useEffect, useMemo, useState } from "react";
import type { ElementType } from "react";
import {
  Bot,
  Activity,
  Shield,
  ScrollText,
} from "lucide-react";
import { subDays, startOfDay, endOfDay } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchFrontendBootstrap,
  fetchModels,
  fetchServerMemoryOverview,
  fetchSettings,
  fetchSettingsActivity,
  promoteServerMemorySnapshotToNote,
  promoteServerMemorySnapshotToSkill,
  runServerMemoryDreams,
  archiveServerMemorySnapshot,
  fetchAuthSession,
  updateServerMemoryPolicy,
  saveSettings,
  type ServerMemoryOverviewResponse,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { SettingsWorkspace } from "@/components/settings/SettingsWorkspace";
import { AiSettingsPanel } from "./settings-page/AiSettingsPanel";
import { AccessSettingsPanel } from "./settings-page/AccessSettingsPanel";
import { ActivityLogPanel } from "./settings-page/ActivityLogPanel";
import { LoggingSettingsPanel } from "./settings-page/LoggingSettingsPanel";
import { MemorySettingsPanel } from "./settings-page/MemorySettingsPanel";
import { useAiSettingsForm } from "./settings-page/useAiSettingsForm";
import {
  DEFAULT_LOGGING_CONFIG,
  LOGGING_KEYS,
  type SettingsTabValue,
} from "./settings-page/constants";

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
  const apiKeys = settingsData?.api_keys as Record<string, boolean> | undefined;

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

  // Logging config state
  const [loggingConfig, setLoggingConfig] = useState({ ...DEFAULT_LOGGING_CONFIG });
  const [loggingSaved, setLoggingSaved] = useState(false);

  useEffect(() => {
    if (!currentConfig) return;
    setLoggingConfig({
      ...DEFAULT_LOGGING_CONFIG,
      ...Object.fromEntries(LOGGING_KEYS.map((key) => [key, currentConfig[key] ?? DEFAULT_LOGGING_CONFIG[key]])),
    });
  }, [currentConfig]);

  const aiSettings = useAiSettingsForm({
    currentConfig,
    modelsData,
    apiKeys,
    saving,
    setSaving,
  });

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
  const settingsTabs: Array<{
    value: SettingsTabValue;
    label: string;
    description: string;
    icon: ElementType;
    badge?: string;
  }> = [
    {
      value: "ai",
      label: "Модели",
      description: "Провайдеры, роли, runtime и каталог моделей",
      icon: Bot,
      badge: aiSettings.aiDraftDirty ? "Черновик" : undefined,
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
            label: "Автозаметки",
            description: "Долгосрочные записи и рабочие паттерны",
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
      description="Главные системные параметры платформы: модели, доступы, аудит и рабочий журнал."
      asideHint="Начните с модели по умолчанию и доступов. Журнал нужен для контроля, но не должен мешать основному рабочему потоку."
      actions={
        <>
          <Badge variant="outline">{activeTabMeta.label}</Badge>
          <Badge variant="secondary">{aiSettings.configuredProviderCount} провайдера готово</Badge>
          {aiSettings.aiDraftDirty ? <Badge>Есть черновик</Badge> : <Badge variant="outline">Все сохранено</Badge>}
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
          <AiSettingsPanel config={config} apiKeys={apiKeys} isAdmin={isAdmin} form={aiSettings} />
        </TabsContent>

        {/* ==================== ACCESS TAB ==================== */}
        <TabsContent value="access">
          <AccessSettingsPanel />
        </TabsContent>

        {/* ==================== MEMORY TAB ==================== */}
        {isAdmin && (
          <TabsContent value="memory" className="space-y-4">
            <MemorySettingsPanel
              memoryServers={memoryServers}
              selectedMemoryServerId={selectedMemoryServerId}
              selectedMemoryServer={selectedMemoryServer}
              memoryOverview={memoryOverview}
              memoryLoading={memoryLoading}
              memoryDreamRunning={memoryDreamRunning}
              memoryPolicySaving={memoryPolicySaving}
              memoryActionKey={memoryActionKey}
              memoryPolicyDraft={memoryPolicyDraft}
              onSelectedMemoryServerIdChange={setSelectedMemoryServerId}
              onMemoryPolicyDraftChange={setMemoryPolicyDraft}
              onRefreshMemoryOverview={refreshMemoryOverview}
              onRunMemoryDreams={onRunMemoryDreams}
              onSaveMemoryPolicy={onSaveMemoryPolicy}
              onArchiveMemorySnapshot={onArchiveMemorySnapshot}
              onPromoteMemorySnapshotToNote={onPromoteMemorySnapshotToNote}
              onPromoteMemorySnapshotToSkill={onPromoteMemorySnapshotToSkill}
            />
          </TabsContent>
        )}

        {/* ==================== LOGGING TAB ==================== */}
        {isAdmin && (
          <TabsContent value="logging" className="space-y-4">
            <LoggingSettingsPanel
              loggingConfig={loggingConfig}
              loggingSaved={loggingSaved}
              saving={saving}
              onSave={handleSaveLogging}
              onUpdate={updateLogging}
            />
          </TabsContent>
        )}

        {/* ==================== ACTIVITY TAB ==================== */}
        {isAdmin && (
          <TabsContent value="activity" className="space-y-4">
            <ActivityLogPanel
              activitySearch={activitySearch}
              activityDays={activityDays}
              dateFrom={dateFrom}
              dateTo={dateTo}
              filteredActivity={filteredActivity}
              onSearchChange={setActivitySearch}
              onActivityDaysChange={setActivityDays}
              onDateFromChange={setDateFrom}
              onDateToChange={setDateTo}
            />
          </TabsContent>
        )}
      </Tabs>
    </SettingsWorkspace>
  );
}
