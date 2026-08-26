import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Eye } from "lucide-react";
import { endOfDay, startOfDay, subDays } from "date-fns";

import {
  fetchAuthSession,
  fetchSettings,
  fetchSettingsActivity,
  saveSettings,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { QueryStateBlock } from "@/components/ui/page-shell";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  DEFAULT_LOGGING_CONFIG,
  LOGGING_KEYS,
  AUDIT_LOGGING_PRESETS,
  type AuditLoggingPresetKey,
  type LoggingConfig,
  type LoggingConfigKey,
} from "../settings-audit/auditSettingsModel";
import { AuditActivityTab } from "../settings-audit/AuditActivityTab";
import { AuditLoggingTab } from "../settings-audit/AuditLoggingTab";

export default function SettingsAuditPage() {
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [loggingSaved, setLoggingSaved] = useState(false);
  const [activeTab, setActiveTab] = useState<"logging" | "activity">("logging");
  const [loggingConfig, setLoggingConfig] = useState<LoggingConfig>({ ...DEFAULT_LOGGING_CONFIG });
  const [activitySearch, setActivitySearch] = useState("");
  const [activityDays, setActivityDays] = useState(7);
  const [dateFrom, setDateFrom] = useState<Date | undefined>(subDays(new Date(), 7));
  const [dateTo, setDateTo] = useState<Date | undefined>(new Date());

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

  const computedDays = useMemo(() => {
    if (dateFrom && dateTo) {
      return Math.max(1, Math.ceil((dateTo.getTime() - dateFrom.getTime()) / 86400000));
    }
    return activityDays;
  }, [activityDays, dateFrom, dateTo]);

  const { data: activityData } = useQuery({
    queryKey: ["settings", "activity", computedDays],
    queryFn: () => fetchSettingsActivity(200, computedDays),
    enabled: isAdmin,
    staleTime: 20_000,
  });

  useEffect(() => {
    if (!currentConfig) return;
    const config = currentConfig as Record<string, unknown>;
    setLoggingConfig({
      ...DEFAULT_LOGGING_CONFIG,
      ...Object.fromEntries(LOGGING_KEYS.map((key) => [key, config[key] ?? DEFAULT_LOGGING_CONFIG[key]])),
    } as LoggingConfig);
  }, [currentConfig]);

  const updateLogging = useCallback((key: LoggingConfigKey, value: unknown) => {
    setLoggingConfig((prev) => ({ ...prev, [key]: value } as LoggingConfig));
    setLoggingSaved(false);
  }, []);

  const applyLoggingPreset = useCallback((preset: AuditLoggingPresetKey) => {
    setLoggingConfig({ ...AUDIT_LOGGING_PRESETS[preset] });
    setLoggingSaved(false);
  }, []);

  const handleSaveLogging = async () => {
    setSaving(true);
    try {
      await saveSettings({ ...loggingConfig });
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
        (event) =>
          event.username?.toLowerCase().includes(q) ||
          event.action?.toLowerCase().includes(q) ||
          (event.description || "").toLowerCase().includes(q) ||
          event.category?.toLowerCase().includes(q),
      );
    }
    if (dateFrom) {
      const from = startOfDay(dateFrom).getTime();
      filtered = filtered.filter((event) => new Date(event.timestamp || event.created_at || "").getTime() >= from);
    }
    if (dateTo) {
      const to = endOfDay(dateTo).getTime();
      filtered = filtered.filter((event) => new Date(event.timestamp || event.created_at || "").getTime() <= to);
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
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
          <Activity className="h-4 w-4 text-primary" />
        </div>
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-foreground">Журнал аудита</h1>
          <p className="text-sm leading-6 text-muted-foreground">Настройки и история действий</p>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as "logging" | "activity")} className="w-full">
        <TabsList className="grid h-auto w-full max-w-md grid-cols-2 gap-1 rounded-xl border border-border bg-card p-1 shadow-sm">
          <TabsTrigger value="logging" className="min-h-10 gap-2 rounded-sm px-4 py-2 text-sm font-semibold">
            <Eye className="h-4 w-4" />
            Логирование
          </TabsTrigger>
          <TabsTrigger value="activity" className="min-h-10 gap-2 rounded-sm px-4 py-2 text-sm font-semibold">
            <Activity className="h-4 w-4" />
            Журнал
            {filteredActivity.length > 0 && (
              <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-xs">
                {filteredActivity.length}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="logging" className="mt-4 space-y-4">
          <AuditLoggingTab
            loggingConfig={loggingConfig}
            saving={saving}
            loggingSaved={loggingSaved}
            onApplyPreset={applyLoggingPreset}
            onUpdateLogging={updateLogging}
            onSaveLogging={handleSaveLogging}
          />
        </TabsContent>

        <TabsContent value="activity" className="mt-4 space-y-4">
          <AuditActivityTab
            activitySearch={activitySearch}
            activityDays={activityDays}
            dateFrom={dateFrom}
            dateTo={dateTo}
            filteredActivity={filteredActivity}
            onActivitySearchChange={setActivitySearch}
            onActivityDaysChange={setActivityDays}
            onDateFromChange={setDateFrom}
            onDateToChange={setDateTo}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
