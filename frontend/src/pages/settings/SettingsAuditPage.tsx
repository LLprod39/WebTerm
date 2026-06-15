import { useCallback, useEffect, useMemo, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { Navigate } from "react-router-dom";
import {
  Activity,
  Bot,
  Terminal,
  MessageSquare,
  Workflow,
  Shield,
  Database,
  Key,
  Cpu,
  FileText,
  Globe,
  Save,
  Eye,
  Search,
  CalendarIcon,
} from "lucide-react";
import { format, subDays, startOfDay, endOfDay } from "date-fns";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchSettings,
  fetchSettingsActivity,
  saveSettings,
  fetchAuthSession,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { SettingsSectionCard as SectionCard } from "@/components/settings/SettingsSectionCard";
import { QueryStateBlock } from "@/components/ui/page-shell";

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

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

const LOGGING_ITEM_KEYS = [
  { key: "log_terminal_commands", labelKey: "audit.terminal_label", descKey: "audit.terminal_desc", icon: Terminal },
  { key: "log_ai_assistant", labelKey: "audit.ai_label", descKey: "audit.ai_desc", icon: MessageSquare },
  { key: "log_agent_runs", labelKey: "audit.agents_label", descKey: "audit.agents_desc", icon: Bot },
  { key: "log_pipeline_runs", labelKey: "audit.pipelines_label", descKey: "audit.pipelines_desc", icon: Workflow },
  { key: "log_auth_events", labelKey: "audit.auth_label", descKey: "audit.auth_desc", icon: Shield },
  { key: "log_server_changes", labelKey: "audit.servers_label", descKey: "audit.servers_desc", icon: Database },
  { key: "log_settings_changes", labelKey: "audit.settings_label", descKey: "audit.settings_desc", icon: Key },
  { key: "log_mcp_calls", labelKey: "audit.mcp_label", descKey: "audit.mcp_desc", icon: Cpu },
  { key: "log_file_operations", labelKey: "audit.files_label", descKey: "audit.files_desc", icon: FileText },
  { key: "log_http_requests", labelKey: "audit.http_label", descKey: "audit.http_desc", icon: Globe },
];

const CATEGORY_ICONS: Record<string, React.ElementType> = {
  terminal: Terminal,
  ai: Bot,
  agent: Bot,
  pipeline: Workflow,
  auth: Shield,
  server: Database,
  settings: Key,
};

const DATE_PRESET_KEYS = [
  { labelKey: "adash.preset_today", days: 0 },
  { labelKey: "audit.yesterday", days: 1 },
  { labelKey: "adash.preset_7d", days: 7 },
  { labelKey: "adash.preset_14d", days: 14 },
  { labelKey: "adash.preset_30d", days: 30 },
];

function relativeTime(value: string): string {
  const d = new Date(value);
  const diff = Math.max(1, Math.floor((Date.now() - d.getTime()) / 60000));
  if (diff < 60) return `${diff}m ago`;
  if (diff < 1440) return `${Math.floor(diff / 60)}h ago`;
  return `${Math.floor(diff / 1440)}d ago`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────────────────────

export default function SettingsAuditPage() {
  const { t } = useI18n();
  const LOGGING_ITEMS = LOGGING_ITEM_KEYS.map((i) => ({ ...i, label: t(i.labelKey), desc: t(i.descKey) }));
  const DATE_PRESETS = DATE_PRESET_KEYS.map((p) => ({ ...p, label: t(p.labelKey) }));
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [loggingSaved, setLoggingSaved] = useState(false);
  const [activeTab, setActiveTab] = useState<"logging" | "activity">("logging");

  const { data: authData, isLoading: authLoading } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const isAdmin = authData?.user?.is_staff ?? false;

  const { data: settingsData } = useQuery({
    queryKey: ["settings", "config"],
    queryFn: fetchSettings,
    staleTime: 30_000,
  });
  const currentConfig = settingsData?.config;

  // Logging config state
  const [loggingConfig, setLoggingConfig] = useState({ ...DEFAULT_LOGGING_CONFIG });

  // Activity state
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

  // Hydrate logging config
  useEffect(() => {
    if (!currentConfig) return;
    setLoggingConfig({
      ...DEFAULT_LOGGING_CONFIG,
      ...Object.fromEntries(LOGGING_KEYS.map((key) => [key, currentConfig[key] ?? DEFAULT_LOGGING_CONFIG[key as keyof typeof DEFAULT_LOGGING_CONFIG]])),
    });
  }, [currentConfig]);

  const updateLogging = useCallback((key: string, value: unknown) => {
    setLoggingConfig((prev) => ({ ...prev, [key]: value }));
    setLoggingSaved(false);
  }, []);

  const handleSaveLogging = async () => {
    setSaving(true);
    try {
      await saveSettings(loggingConfig);
      await queryClient.invalidateQueries({ queryKey: ["settings", "config"] });
      setLoggingSaved(true);
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

  if (authLoading) {
    return <QueryStateBlock loading>{null}</QueryStateBlock>;
  }

  if (!isAdmin) {
    return <Navigate to="/settings/ai" replace />;
  }

  return (
    <div className="space-y-6 pb-10">
      {/* Page Header */}
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
          <Activity className="h-4 w-4 text-primary" />
        </div>
        <div>
          <h1 className="text-base font-semibold tracking-tight text-foreground">Аудит и журнал</h1>
          <p className="text-[11px] text-muted-foreground">Логирование и история действий пользователей</p>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "logging" | "activity")} className="w-full">
        <TabsList className="grid h-auto w-full max-w-md grid-cols-2 gap-2 rounded-2xl border border-primary/10 bg-card/40 p-1.5 shadow-sm backdrop-blur-xl">
          <TabsTrigger value="logging" className="gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all data-[state=active]:bg-primary/10 data-[state=active]:text-primary data-[state=active]:shadow-sm">
            <Eye className="h-4 w-4" />
            Логирование
          </TabsTrigger>
          <TabsTrigger value="activity" className="gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all data-[state=active]:bg-primary/10 data-[state=active]:text-primary data-[state=active]:shadow-sm">
            <Activity className="h-4 w-4" />
            Журнал
            {filteredActivity.length > 0 && (
              <Badge variant="default" className="ml-1 h-5 px-1.5 text-[10px] bg-primary text-primary-foreground">{filteredActivity.length}</Badge>
            )}
          </TabsTrigger>
        </TabsList>

        {/* Logging Tab */}
        <TabsContent value="logging" className="mt-4 space-y-4">
          <SectionCard
            title={t("audit.log_settings")}
            icon={Eye}
            description={t("audit.log_settings_desc")}
            actions={
              <Button size="sm" className="h-7 gap-1.5" onClick={handleSaveLogging} disabled={saving}>
                <Save className="h-3 w-3" />
                {saving ? t("audit.saving") : loggingSaved ? t("ai.saved") : t("audit.save")}
              </Button>
            }
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {LOGGING_ITEMS.map((item) => {
                const Icon = item.icon;
                const enabled = loggingConfig[item.key as keyof typeof loggingConfig];
                return (
                  <label
                    key={item.key}
                    className="group flex cursor-pointer items-center justify-between gap-4 rounded-xl border border-primary/5 bg-background/50 px-4 py-4 shadow-sm transition-all duration-300 hover:border-primary/20 hover:bg-background/80 hover:shadow-md"
                  >
                    <div className="flex items-center gap-4 min-w-0">
                      <div className={cn(
                        "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl shadow-inner transition-colors duration-300",
                        enabled ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground group-hover:bg-muted/80"
                      )}>
                        <Icon className="h-5 w-5" />
                      </div>
                      <div className="min-w-0">
                        <p className={cn("text-sm font-bold tracking-tight transition-colors", enabled ? "text-foreground" : "text-foreground/70")}>{item.label}</p>
                        <p className="line-clamp-2 text-[11px] font-medium leading-4 text-muted-foreground/80">{item.desc}</p>
                      </div>
                    </div>
                    <Switch
                      checked={Boolean(enabled)}
                      onCheckedChange={(v) => updateLogging(item.key, v)}
                      className="data-[state=checked]:bg-primary"
                    />
                  </label>
                );
              })}
            </div>
          </SectionCard>

          <SectionCard title={t("audit.storage_title")} icon={Database} description={t("audit.storage_desc")}>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label className="text-xs">{t("audit.retention_label")}</Label>
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
                <Label className="text-xs">{t("audit.export_format")}</Label>
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
              </p>
            </div>
          </SectionCard>

          {/* Active Categories Summary */}
          <div className="rounded-xl border border-border/60 bg-secondary/10 px-5 py-4 shadow-sm">
            <div className="mb-3 flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10">
                <Eye className="h-3.5 w-3.5 text-primary" />
              </div>
              <span className="text-xs font-semibold text-foreground">{t("audit.filter_tab")}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {LOGGING_ITEMS.filter((i) => loggingConfig[i.key as keyof typeof loggingConfig]).map((i) => (
                <Badge key={i.key} variant="secondary" className="gap-1 text-[10px]">
                  <i.icon className="h-2.5 w-2.5" /> {i.label}
                </Badge>
              ))}
              {LOGGING_ITEMS.every((i) => !loggingConfig[i.key as keyof typeof loggingConfig]) && (
                <p className="text-[11px] text-muted-foreground">{t("audit.log_settings")}</p>
              )}
            </div>
          </div>
        </TabsContent>

        {/* Activity Tab */}
        <TabsContent value="activity" className="mt-4 space-y-4">
          <SectionCard title={t("audit.activity_log")} icon={Activity} description={t("audit.activity_desc")}>
            <div className="space-y-4">
              {/* Filters */}
              <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
                <div className="relative min-w-0 flex-1 md:min-w-[240px] xl:max-w-md">
                  <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={activitySearch}
                    onChange={(e) => setActivitySearch(e.target.value)}
                    placeholder={t("audit.search_placeholder")}
                    className="h-8 pl-9 text-xs"
                  />
                </div>

                {/* Date presets */}
                <div className="flex max-w-full items-center gap-1 overflow-x-auto pb-1 md:pb-0">
                  {DATE_PRESETS.map((preset) => (
                    <Button
                      key={preset.days}
                      size="sm"
                      variant={activityDays === preset.days ? "default" : "outline"}
                      className="h-7 px-2 text-[10px]"
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
                <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0">
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button variant="outline" size="sm" className="h-7 gap-1 px-2 text-[10px]">
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
                        className="pointer-events-auto p-3"
                      />
                    </PopoverContent>
                  </Popover>
                  <span className="text-[10px] text-muted-foreground">—</span>
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button variant="outline" size="sm" className="h-7 gap-1 px-2 text-[10px]">
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
                        className="pointer-events-auto p-3"
                      />
                    </PopoverContent>
                  </Popover>
                </div>

                <Badge variant="outline" className="shrink-0 text-[10px]">
                  {filteredActivity.length} записей
                </Badge>
              </div>

              {/* Activity table */}
              <div className="space-y-2 md:hidden">
                {filteredActivity.length === 0 ? (
                  <div className="rounded-lg border border-border px-3 py-8 text-center text-sm text-muted-foreground">
                    Нет записей за выбранный период
                  </div>
                ) : (
                  filteredActivity.slice(0, 30).map((event, idx) => {
                    const CategoryIcon = CATEGORY_ICONS[event.category || ""] || Activity;
                    return (
                      <div key={idx} className="rounded-lg border border-border/70 bg-background/40 px-3 py-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-[11px] text-muted-foreground">{relativeTime(event.timestamp || event.created_at || "")}</span>
                              <span className="text-xs font-medium text-foreground">{event.username || "—"}</span>
                            </div>
                            <div className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                              <CategoryIcon className="h-3 w-3 shrink-0" />
                              <span>{event.category || "—"}</span>
                            </div>
                          </div>
                          <Badge variant="secondary" className="shrink-0 text-[10px]">{event.action || "—"}</Badge>
                        </div>
                        <p className="mt-2 break-words text-xs leading-5 text-muted-foreground">
                          {event.description || "—"}
                        </p>
                      </div>
                    );
                  })
                )}
              </div>

              <div className="hidden overflow-hidden rounded-lg border border-border md:block">
                <div className="max-h-[500px] overflow-auto">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 z-10 bg-card">
                      <tr className="border-b border-border text-[10px] uppercase text-muted-foreground">
                        <th className="px-3 py-2 text-left font-medium">Время</th>
                        <th className="px-3 py-2 text-left font-medium">Пользователь</th>
                        <th className="px-3 py-2 text-left font-medium">Категория</th>
                        <th className="px-3 py-2 text-left font-medium">Действие</th>
                        <th className="px-3 py-2 text-left font-medium">Описание</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredActivity.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="px-3 py-8 text-center text-muted-foreground">
                            Нет записей за выбранный период
                          </td>
                        </tr>
                      ) : (
                        filteredActivity.map((event, idx) => {
                          const CategoryIcon = CATEGORY_ICONS[event.category || ""] || Activity;
                          return (
                            <tr key={idx} className="border-b border-border/50 transition-colors hover:bg-muted/30">
                              <td className="whitespace-nowrap px-3 py-2.5 text-muted-foreground">
                                {relativeTime(event.timestamp || event.created_at || "")}
                              </td>
                              <td className="px-3 py-2.5">
                                <span className="font-medium text-foreground">{event.username || "—"}</span>
                              </td>
                              <td className="px-3 py-2.5">
                                <div className="flex items-center gap-1.5">
                                  <CategoryIcon className="h-3 w-3 text-muted-foreground" />
                                  <span className="text-muted-foreground">{event.category || "—"}</span>
                                </div>
                              </td>
                              <td className="px-3 py-2.5">
                                <Badge variant="secondary" className="text-[10px]">{event.action || "—"}</Badge>
                              </td>
                              <td className="max-w-[300px] truncate px-3 py-2.5 text-muted-foreground">
                                {event.description || "—"}
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
