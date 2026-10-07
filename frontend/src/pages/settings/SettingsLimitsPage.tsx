import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Cable, Clock, Gauge, RotateCcw, Save } from "lucide-react";

import { fetchAuthSession, fetchSettings, saveSettings, type SettingsConfig } from "@/api";
import { AgentLimitsCard } from "@/boardui/components/application/agent-limits/agent-limits-card";
import { DataGrid, type DataGridColumn } from "@/boardui/components/application/data-grid/data-grid";
import { DirectionProvider } from "@/boardui/components/foundations/direction/direction";
import { SettingsPageHeader } from "@/components/settings/SettingsPageHeader";
import { SettingsPageShell } from "@/components/settings/SettingsPageShell";
import { SettingsSectionCard as SectionCard } from "@/components/settings/SettingsSectionCard";
import { Button } from "@/components/ui/button";
import { QueryStateBlock } from "@/components/ui/page-shell";
import { localize, useI18n } from "@/lib/i18n";

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

type LimitRow = {
  key: LimitKey;
  label: string;
  description: string;
  value: number;
  min: number;
  max: number;
};

const RUN_LIMITS: LimitField[] = [
  { key: "agent_active_runs_per_user_limit", label: "Агенты на пользователя", description: "Одновременные запуски одного пользователя", max: 100 },
  { key: "agent_active_runs_global_limit", label: "Агенты на платформу", description: "Общее число одновременных запусков", max: 500 },
  { key: "agent_run_stale_seconds", label: "Зависание агента, сек.", description: "Когда запуск считать зависшим", max: 604800 },
  { key: "pipeline_active_runs_per_user_limit", label: "Сценарии на пользователя", description: "Одновременные сценарии одного пользователя", max: 100 },
  { key: "pipeline_active_runs_global_limit", label: "Сценарии на платформу", description: "Общее число одновременных сценариев", max: 500 },
  { key: "pipeline_run_stale_seconds", label: "Зависание сценария, сек.", description: "Когда сценарий считать зависшим", max: 604800 },
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

function fieldsToRows(fields: LimitField[], draft: Record<LimitKey, number>): LimitRow[] {
  return fields.map((field) => ({
    key: field.key,
    label: field.label,
    description: field.description,
    value: draft[field.key] ?? 0,
    min: field.min ?? 0,
    max: field.max ?? 1_000_000_000,
  }));
}

const LIMIT_COLUMNS: readonly DataGridColumn<LimitRow>[] = [
  { key: "label", header: "Параметр", width: 240, editable: false },
  { key: "description", header: "Описание", width: 320, editable: false },
  {
    key: "value",
    header: "Значение",
    width: 140,
    type: "number",
    editable: true,
    align: "end",
    min: 0,
    validate: (value, row) => {
      const num = typeof value === "number" ? value : Number(value);
      if (!Number.isFinite(num)) return "Число";
      if (num < row.min) return `≥ ${row.min}`;
      if (num > row.max) return `≤ ${row.max}`;
      return undefined;
    },
  },
];

function LimitsDataGrid({
  fields,
  draft,
  onRowsChange,
  label,
}: {
  fields: LimitField[];
  draft: Record<LimitKey, number>;
  onRowsChange: (rows: LimitRow[]) => void;
  label: string;
}) {
  const rows = useMemo(() => fieldsToRows(fields, draft), [draft, fields]);
  return (
    <DataGrid
      aria-label={label}
      data={rows}
      columns={LIMIT_COLUMNS}
      getRowId={(row) => row.key}
      onDataChange={onRowsChange}
      height={Math.min(396, 56 + rows.length * 40)}
      exportFileName={`${label}.csv`}
    />
  );
}

export default function SettingsLimitsPage() {
  const { lang } = useI18n();
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

  const applyRows = (rows: LimitRow[]) => {
    setDraft((prev) => {
      const next = { ...prev };
      for (const row of rows) {
        next[row.key] = Math.max(row.min, Math.min(row.max, Number(row.value) || 0));
      }
      return next;
    });
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

  const dailyTokens = draft.llm_daily_token_limit_per_user ?? 0;
  const agentUser = draft.agent_active_runs_per_user_limit ?? 0;
  const agentGlobal = draft.agent_active_runs_global_limit ?? 0;
  const sshUser = draft.ssh_terminal_sessions_per_user_limit ?? 0;

  if (authLoading) {
    return <QueryStateBlock loading>{null}</QueryStateBlock>;
  }

  if (!isAdmin) {
    return <Navigate to="/settings/ai" replace />;
  }

  return (
    <SettingsPageShell width="wide">
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
        <DirectionProvider locale={lang === "ru" ? "ru-RU" : "en-US"}>
          <div className="space-y-5">
            <AgentLimitsCard
              plan={localize(lang, "Платформа", "Platform")}
              planHref="/settings/ai"
              defaultExpanded
              context={{
                max: Math.max(dailyTokens || 250_000, 1),
                segments: [
                  {
                    label: localize(lang, "Дневной бюджет токенов", "Daily token budget"),
                    tokens: dailyTokens || 250_000,
                  },
                ],
              }}
              limits={[
                {
                  label: localize(lang, "Агенты / пользователь", "Agents / user"),
                  used: agentGlobal > 0 ? Math.min(1, agentUser / agentGlobal) : 0,
                  resets: localize(lang, "конфиг", "config"),
                },
                {
                  label: localize(lang, "SSH / пользователь", "SSH / user"),
                  used: Math.min(1, sshUser / Math.max(draft.ssh_terminal_sessions_global_limit || 1, 1)),
                  resets: localize(lang, "конфиг", "config"),
                },
              ]}
            />

            <SectionCard title="Запуски" icon={Bot} description="Агенты и сценарии">
              <LimitsDataGrid
                fields={RUN_LIMITS}
                draft={draft}
                onRowsChange={applyRows}
                label={localize(lang, "Лимиты запусков", "Run limits")}
              />
            </SectionCard>

            <SectionCard title="Сессии и модели" icon={Clock} description="SSH-терминалы и дневной бюджет токенов">
              <LimitsDataGrid
                fields={SESSION_LIMITS}
                draft={draft}
                onRowsChange={applyRows}
                label={localize(lang, "Лимиты сессий", "Session limits")}
              />
            </SectionCard>

            <SectionCard title="MCP" icon={Cable} description="Ожидание и повторы серверов инструментов">
              <LimitsDataGrid
                fields={MCP_LIMITS}
                draft={draft}
                onRowsChange={applyRows}
                label={localize(lang, "Лимиты MCP", "MCP limits")}
              />
            </SectionCard>
          </div>
        </DirectionProvider>
      </QueryStateBlock>
    </SettingsPageShell>
  );
}
