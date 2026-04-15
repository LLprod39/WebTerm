import { useCallback, useEffect, useMemo, useState } from "react";
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

// ─────────────────────────────────────────────────────────────────────────────
// Section Card Component
// ─────────────────────────────────────────────────────────────────────────────

function SectionCard({ title, icon: Icon, children, description, actions }: {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <section className="group relative overflow-hidden rounded-2xl border border-primary/10 bg-card/40 backdrop-blur-3xl shadow-sm transition-all duration-500 hover:shadow-[0_8px_30px_rgba(0,0,0,0.04)]">
      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-transparent opacity-0 transition-opacity duration-500 group-hover:opacity-100" />
      <div className="relative flex flex-col gap-4 border-b border-border/40 bg-secondary/10 px-6 py-5 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-primary/5 text-primary shadow-inner border border-primary/10 transition-transform duration-300 group-hover:scale-105">
            <Icon className="h-5 w-5 drop-shadow-sm" />
          </div>
          <div>
            <h2 className="text-lg font-bold tracking-tight text-foreground/90">{title}</h2>
            {description ? <p className="mt-1 flex items-center text-sm font-medium text-muted-foreground/80">{description}</p> : null}
          </div>
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      <div className="relative p-6">{children}</div>
    </section>
  );
}

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

  // Auth check
  if (authLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-sm text-muted-foreground">Загрузка...</div>
      </div>
    );
  }

  if (!isAdmin) {
    return <Navigate to="/settings/ai" replace />;
  }

  return (
    <div className="space-y-8 pb-10">
      {/* Page Header */}
      <div className="relative">
        <div className="absolute -inset-1 rounded-3xl bg-gradient-to-r from-primary/20 via-primary/5 to-transparent blur-2xl -z-10" />
        <h1 className="text-3xl font-black tracking-tight text-foreground">Аудит и журнал</h1>
        <p className="mt-2 text-base font-medium text-muted-foreground/80 max-w-2xl">
          Настройки логирования и подробная история всех действий пользователей на платформе
        </p>
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
            title="Настройки логирования"
            icon={Eye}
            description="Выберите какие действия пользователей записывать в журнал"
            actions={
              <Button size="sm" className="h-7 gap-1.5" onClick={handleSaveLogging} disabled={saving}>
                <Save className="h-3 w-3" />
                {saving ? "Сохранение..." : loggingSaved ? "Сохранено" : "Сохранить"}
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
                        <p className="text-[11px] font-medium text-muted-foreground/80 truncate">{item.desc}</p>
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

          <SectionCard title="Хранение и экспорт" icon={Database} description="Настройки ротации и формата логов">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
              </p>
            </div>
          </SectionCard>

          {/* Active Categories Summary */}
          <div className="rounded-lg border border-border bg-card px-5 py-4">
            <div className="mb-3 flex items-center gap-2">
              <Eye className="h-4 w-4 text-primary" />
              <span className="text-xs font-medium">Активные категории</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {LOGGING_ITEMS.filter((i) => loggingConfig[i.key as keyof typeof loggingConfig]).map((i) => (
                <Badge key={i.key} variant="secondary" className="gap-1 text-[10px]">
                  <i.icon className="h-2.5 w-2.5" /> {i.label}
                </Badge>
              ))}
              {LOGGING_ITEMS.every((i) => !loggingConfig[i.key as keyof typeof loggingConfig]) && (
                <p className="text-[11px] text-muted-foreground">Все категории отключены</p>
              )}
            </div>
          </div>
        </TabsContent>

        {/* Activity Tab */}
        <TabsContent value="activity" className="mt-4 space-y-4">
          <SectionCard title="Журнал действий" icon={Activity} description="Полная история действий пользователей на платформе">
            <div className="space-y-4">
              {/* Filters */}
              <div className="flex flex-wrap items-center gap-3">
                <div className="relative min-w-[240px] flex-1 xl:max-w-md">
                  <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={activitySearch}
                    onChange={(e) => setActivitySearch(e.target.value)}
                    placeholder="Поиск по пользователю, действию..."
                    className="h-8 pl-9 text-xs"
                  />
                </div>

                {/* Date presets */}
                <div className="flex items-center gap-1">
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
                <div className="flex items-center gap-1.5">
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
              <div className="overflow-hidden rounded-lg border border-border">
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
