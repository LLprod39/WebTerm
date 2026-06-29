import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Cable, Clock, Gauge, RotateCcw, Save } from "lucide-react";

import { fetchAuthSession, fetchSettings, saveSettings, type SettingsConfig } from "@/api";
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
  { key: "agent_active_runs_per_user_limit", label: "Agent runs / user", description: "Активные agent runs на пользователя", max: 100 },
  { key: "agent_active_runs_global_limit", label: "Agent runs global", description: "Активные agent runs на платформу", max: 500 },
  { key: "agent_run_stale_seconds", label: "Agent stale seconds", description: "Когда agent run считается зависшим", max: 604800 },
  { key: "pipeline_active_runs_per_user_limit", label: "Pipeline runs / user", description: "Активные pipeline runs на пользователя", max: 100 },
  { key: "pipeline_active_runs_global_limit", label: "Pipeline runs global", description: "Активные pipeline runs на платформу", max: 500 },
  { key: "pipeline_run_stale_seconds", label: "Pipeline stale seconds", description: "Когда pipeline run считается зависшим", max: 604800 },
];

const SESSION_LIMITS: LimitField[] = [
  { key: "ssh_terminal_sessions_per_user_limit", label: "SSH sessions / user", description: "Активные terminal-сессии на пользователя", max: 100 },
  { key: "ssh_terminal_sessions_global_limit", label: "SSH sessions global", description: "Активные terminal-сессии на платформу", max: 1000 },
  { key: "ssh_terminal_session_stale_seconds", label: "SSH stale seconds", description: "Когда terminal-сессия считается зависшей", max: 86400 },
  { key: "llm_daily_token_limit_per_user", label: "LLM daily tokens / user", description: "0 отключает дневной бюджет", max: 50000000 },
];

const MCP_LIMITS: LimitField[] = [
  { key: "mcp_stdio_initialize_timeout_seconds", label: "stdio initialize", description: "Timeout запуска stdio MCP", min: 1, max: 600 },
  { key: "mcp_stdio_request_timeout_seconds", label: "stdio request", description: "Timeout обычного stdio request", min: 1, max: 600 },
  { key: "mcp_stdio_tool_call_timeout_seconds", label: "stdio tool call", description: "Timeout stdio tool call", min: 1, max: 3600 },
  { key: "mcp_process_terminate_timeout_seconds", label: "process terminate", description: "Graceful stop timeout", min: 1, max: 60 },
  { key: "mcp_http_connect_timeout_seconds", label: "HTTP connect", description: "Timeout подключения HTTP MCP", min: 1, max: 300 },
  { key: "mcp_http_request_timeout_seconds", label: "HTTP request", description: "Timeout HTTP request/list", min: 1, max: 600 },
  { key: "mcp_http_tool_call_timeout_seconds", label: "HTTP tool call", description: "Timeout HTTP tool call", min: 1, max: 3600 },
  { key: "mcp_http_retry_attempts", label: "HTTP retry attempts", description: "Количество попыток HTTP MCP", max: 10 },
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
    <div className="min-w-0 space-y-2 rounded-lg border border-border/60 bg-background/50 p-3">
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
    <div className="space-y-6 pb-10">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-secondary text-foreground">
            <Gauge className="h-4 w-4" />
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight text-foreground">Лимиты и бюджеты</h1>
            <p className="text-xs text-muted-foreground">Soft limits для пилота и защиты от зависших запусков.</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={resetDraft} disabled={saving}>
            <RotateCcw className="h-4 w-4" />
            Сбросить
          </Button>
          <Button size="sm" onClick={() => void saveDraft()} disabled={saving}>
            <Save className="h-4 w-4" />
            {saving ? "Сохранение" : saved ? "Сохранено" : "Сохранить"}
          </Button>
        </div>
      </div>

      <QueryStateBlock
        loading={isLoading}
        error={error || (!isLoading && !settingsData?.success ? new Error("Не удалось загрузить настройки") : undefined)}
        errorText="Не удалось загрузить лимиты"
        onRetry={() => queryClient.invalidateQueries({ queryKey: ["settings", "config"] })}
      >
        <div className="space-y-4">
          <SectionCard title="Runs" icon={Bot} description="Agent и Studio pipeline ограничения">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {RUN_LIMITS.map((field) => (
                <LimitInput key={field.key} field={field} value={draft[field.key] ?? 0} onChange={updateField} />
              ))}
            </div>
          </SectionCard>

          <SectionCard title="Sessions & LLM" icon={Clock} description="SSH terminal sessions и дневной token budget">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {SESSION_LIMITS.map((field) => (
                <LimitInput key={field.key} field={field} value={draft[field.key] ?? 0} onChange={updateField} />
              ))}
            </div>
          </SectionCard>

          <SectionCard title="MCP" icon={Cable} description="Timeouts и retry для external tool servers">
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
