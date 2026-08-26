import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Cable, Clock, Gauge, RotateCcw, Save } from "lucide-react";

import { fetchAuthSession, fetchSettings, saveSettings, type SettingsConfig } from "@/api";
import { SettingsPageHeader } from "@/components/settings/SettingsPageHeader";
import { SettingsSectionCard as SectionCard } from "@/components/settings/SettingsSectionCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { QueryStateBlock } from "@/components/ui/page-shell";

type LimitKey =
  | "agent_active_runs_per_user_limit"
  | "agent_active_runs_global_limit"
  | "agent_run_stale_seconds"
  | "pipeline_active_runs_per_user_limit"
  | "pipeline_active_runs_global_limit"
  | "pipeline_run_stale_seconds"
  | "ssh_terminal_sessions_per_user_limit"
  | "ssh_terminal_sessions_global_limit"
  | "ssh_terminal_session_stale_seconds"
  | "llm_daily_token_limit_per_user"
  | "mcp_stdio_initialize_timeout_seconds"
  | "mcp_stdio_request_timeout_seconds"
  | "mcp_stdio_tool_call_timeout_seconds"
  | "mcp_process_terminate_timeout_seconds"
  | "mcp_http_connect_timeout_seconds"
  | "mcp_http_request_timeout_seconds"
  | "mcp_http_tool_call_timeout_seconds"
  | "mcp_http_retry_attempts";

type LimitField = {
  key: LimitKey;
  label: string;
  description: string;
  min?: number;
  max?: number;
};

const RUN_LIMITS: LimitField[] = [
  { key: "agent_active_runs_per_user_limit", label: "Агенты на пользователя", description: "Одновременные запуски одного пользователя", max: 100 },
  { key: "agent_active_runs_global_limit", label: "Агенты на платформу", description: "Общее число одновременных запусков", max: 500 },
  { key: "agent_run_stale_seconds", label: "Зависание агента, сек.", description: "Когда запуск считать зависшим", max: 604800 },
  { key: "pipeline_active_runs_per_user_limit", label: "Сценарии на пользователя", description: "Одновременные сценарии одного пользователя", max: 100 },
  { key: "pipeline_active_runs_global_limit", label: "Сценарии на платформу", description: "Общее число одновременных сценариев", max: 500 },
  { key: "pipeline_run_stale_seconds", label: "Зависание сценария, сек.", description: "Когда выполнение считать зависшим", max: 604800 },
];

const SESSION_LIMITS: LimitField[] = [
  { key: "ssh_terminal_sessions_per_user_limit", label: "SSH-сессии на пользователя", description: "Одновременные терминалы одного пользователя", max: 100 },
  { key: "ssh_terminal_sessions_global_limit", label: "SSH-сессии на платформу", description: "Общее число открытых терминалов", max: 1000 },
  { key: "ssh_terminal_session_stale_seconds", label: "Зависание SSH-сессии, сек.", description: "Когда сессию считать зависшей", max: 86400 },
  { key: "llm_daily_token_limit_per_user", label: "Токены в день на пользователя", description: "0 — без дневного ограничения", max: 50000000 },
];

const MCP_LIMITS: LimitField[] = [
  { key: "mcp_stdio_initialize_timeout_seconds", label: "stdio: запуск, сек.", description: "Ожидание запуска MCP-сервера", min: 1, max: 600 },
  { key: "mcp_stdio_request_timeout_seconds", label: "stdio: запрос, сек.", description: "Ожидание обычного запроса", min: 1, max: 600 },
  { key: "mcp_stdio_tool_call_timeout_seconds", label: "stdio: инструмент, сек.", description: "Ожидание вызова инструмента", min: 1, max: 3600 },
  { key: "mcp_process_terminate_timeout_seconds", label: "stdio: остановка, сек.", description: "Ожидание корректной остановки", min: 1, max: 60 },
  { key: "mcp_http_connect_timeout_seconds", label: "HTTP: подключение, сек.", description: "Ожидание подключения к MCP", min: 1, max: 300 },
  { key: "mcp_http_request_timeout_seconds", label: "HTTP: запрос, сек.", description: "Ожидание запроса или списка", min: 1, max: 600 },
  { key: "mcp_http_tool_call_timeout_seconds", label: "HTTP: инструмент, сек.", description: "Ожидание вызова инструмента", min: 1, max: 3600 },
  { key: "mcp_http_retry_attempts", label: "HTTP: повторы", description: "Число повторных запросов", max: 10 },
];

const ALL_FIELDS = [...RUN_LIMITS, ...SESSION_LIMITS, ...MCP_LIMITS];

function valueFromConfig(config: SettingsConfig | undefined, key: LimitKey, fallback = 0) {
  const raw = config?.[key];
  return typeof raw === "number" && Number.isFinite(raw) ? raw : fallback;
}

function LimitInput({
  field,
  value,
  onChange,
}: {
  field: LimitField;
  value: number;
  onChange: (key: LimitKey, value: number) => void;
}) {
  return (
    <div className="min-w-0 space-y-2 rounded-sm border border-border bg-surface-0 p-3">
      <div className="min-w-0">
        <Label htmlFor={field.key} className="text-xs font-semibold text-foreground">
          {field.label}
        </Label>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{field.description}</p>
      </div>
      <Input
        id={field.key}
        type="number"
        min={field.min ?? 0}
        max={field.max}
        value={value}
        onChange={(event) => onChange(field.key, Number(event.target.value || 0))}
      />
    </div>
  );
}

export default function SettingsLimitsPage() {
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [draft, setDraft] = useState<Record<LimitKey, number>>({} as Record<LimitKey, number>);

  const { data: authData, isLoading: authLoading } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const isAdmin = authData?.user?.is_staff ?? false;

  const { data: settingsData, isLoading, error } = useQuery({
    queryKey: ["settings", "config"],
    queryFn: fetchSettings,
    enabled: isAdmin,
    staleTime: 30_000,
  });

  const config = settingsData?.config;
  const initialDraft = useMemo(() => {
    return Object.fromEntries(ALL_FIELDS.map((field) => [field.key, valueFromConfig(config, field.key)])) as Record<LimitKey, number>;
  }, [config]);

  useEffect(() => {
    if (!config) return;
    setDraft(initialDraft);
    setSaved(false);
  }, [config, initialDraft]);

  const updateField = (key: LimitKey, value: number) => {
    setDraft((prev) => ({ ...prev, [key]: Math.max(0, value) }));
    setSaved(false);
  };

  const resetDraft = () => {
    setDraft(initialDraft);
    setSaved(false);
  };

  const saveDraft = async () => {
    setSaving(true);
    try {
      await saveSettings(draft);
      await queryClient.invalidateQueries({ queryKey: ["settings", "config"] });
      await queryClient.invalidateQueries({ queryKey: ["settings", "readiness"] });
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

  if (authLoading) {
    return <QueryStateBlock loading>{null}</QueryStateBlock>;
  }

  if (!isAdmin) {
    return <Navigate to="/settings/ai" replace />;
  }

  return (
    <div className="space-y-5 pb-10">
      <SettingsPageHeader
        icon={Gauge}
        title="Лимиты и бюджеты"
        description="Ограничения для агентов, сценариев, SSH и MCP."
        actions={
          <>
            <Button variant="outline" size="sm" className="gap-1.5" onClick={resetDraft} disabled={saving}>
              <RotateCcw className="h-4 w-4" />
              Сбросить
            </Button>
            <Button size="sm" className="gap-1.5 shadow-elev-1" onClick={() => void saveDraft()} disabled={saving}>
              <Save className="h-4 w-4" />
              {saving ? "Сохранение…" : saved ? "Сохранено" : "Сохранить"}
            </Button>
          </>
        }
      />

      <QueryStateBlock
        loading={isLoading}
        error={error || (!isLoading && !settingsData?.success ? new Error("Не удалось загрузить настройки") : undefined)}
        errorText="Не удалось загрузить лимиты"
        onRetry={() => queryClient.invalidateQueries({ queryKey: ["settings", "config"] })}
      >
        <div className="space-y-4">
          <SectionCard title="Запуски" icon={Bot} description="Агенты и сценарии">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {RUN_LIMITS.map((field) => (
                <LimitInput key={field.key} field={field} value={draft[field.key] ?? 0} onChange={updateField} />
              ))}
            </div>
          </SectionCard>

          <SectionCard title="Сессии и модели" icon={Clock} description="SSH-терминалы и дневной бюджет токенов">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {SESSION_LIMITS.map((field) => (
                <LimitInput key={field.key} field={field} value={draft[field.key] ?? 0} onChange={updateField} />
              ))}
            </div>
          </SectionCard>

          <SectionCard title="MCP" icon={Cable} description="Ожидание и повторы серверов инструментов">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {MCP_LIMITS.map((field) => (
                <LimitInput key={field.key} field={field} value={draft[field.key] ?? 0} onChange={updateField} />
              ))}
            </div>
          </SectionCard>
        </div>
      </QueryStateBlock>
    </div>
  );
}
