import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight,
  CheckCircle2,
  RefreshCw,
  Save,
  ShieldCheck,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { governanceApi, type SettingsResponse } from "@/api/governance";
import {
  Button,
  ConfirmDialog,
  ErrorState,
  Feedback,
  JsonDetails,
  LoadingState,
  Metric,
  PageHeader,
  Panel,
  StatusBadge,
} from "@/components/ui";
import { useSession } from "@/app/session";
import {
  CheckField,
  FormField,
  GovernanceGuard,
  profileLabels,
  useGovernanceMutation,
} from "./shared";

type SettingValue = string | number | boolean | null;
interface SettingField {
  key: string;
  label: string;
  description?: string;
  type?: "number" | "toggle" | "select" | "url";
  options?: { value: string; label: string }[];
  min?: number;
  max?: number;
}
const auditFields: SettingField[] = [
  {
    key: "log_auth_events",
    label: "Вход и выход пользователей",
    type: "toggle",
  },
  { key: "log_server_changes", label: "Изменения серверов", type: "toggle" },
  { key: "log_settings_changes", label: "Изменения настроек", type: "toggle" },
  { key: "log_terminal_commands", label: "Команды терминала", type: "toggle" },
  { key: "log_file_operations", label: "Файловые операции", type: "toggle" },
  { key: "log_ai_assistant", label: "Запросы ассистента", type: "toggle" },
  { key: "log_agent_runs", label: "Запуски агентов", type: "toggle" },
  { key: "log_pipeline_runs", label: "Запуски сценариев", type: "toggle" },
  { key: "log_mcp_calls", label: "Вызовы MCP", type: "toggle" },
  { key: "log_http_requests", label: "HTTP-запросы", type: "toggle" },
  {
    key: "retention_days",
    label: "Хранить события, дней",
    type: "number",
    min: 1,
    max: 3650,
  },
  {
    key: "export_format",
    label: "Формат экспорта по умолчанию",
    type: "select",
    options: ["json", "csv", "syslog"].map((value) => ({
      value,
      label: value.toUpperCase(),
    })),
  },
];
const identityFields: SettingField[] = [
  {
    key: "domain_auth_enabled",
    label: "Доменная авторизация",
    description: "Вход по доверенному заголовку от корпоративного прокси.",
    type: "toggle",
  },
  {
    key: "domain_auth_header",
    label: "Заголовок идентификатора",
    description: "Должен совпадать с конфигурацией доверенного прокси.",
  },
  {
    key: "domain_auth_auto_create",
    label: "Создавать учётные записи при первом входе",
    type: "toggle",
  },
  {
    key: "domain_auth_lowercase_usernames",
    label: "Приводить логины к нижнему регистру",
    type: "toggle",
  },
  {
    key: "domain_auth_default_profile",
    label: "Профиль новых доменных пользователей",
    type: "select",
    options: Object.entries(profileLabels)
      .filter(([value]) => !["custom", "reset_defaults"].includes(value))
      .map(([value, label]) => ({ value, label })),
  },
];
const limitFields: SettingField[] = [
  {
    key: "agent_active_runs_per_user_limit",
    label: "Агенты: запусков на пользователя",
    max: 100,
  },
  {
    key: "agent_active_runs_global_limit",
    label: "Агенты: запусков во всей системе",
    max: 500,
  },
  {
    key: "agent_run_stale_seconds",
    label: "Агенты: порог устаревания, секунд",
    max: 604800,
  },
  {
    key: "pipeline_active_runs_per_user_limit",
    label: "Сценарии: запусков на пользователя",
    max: 100,
  },
  {
    key: "pipeline_active_runs_global_limit",
    label: "Сценарии: запусков во всей системе",
    max: 500,
  },
  {
    key: "pipeline_run_stale_seconds",
    label: "Сценарии: порог устаревания, секунд",
    max: 604800,
  },
  {
    key: "ssh_terminal_sessions_per_user_limit",
    label: "SSH: сессий на пользователя",
    max: 100,
  },
  {
    key: "ssh_terminal_sessions_global_limit",
    label: "SSH: сессий во всей системе",
    max: 1000,
  },
  {
    key: "ssh_terminal_session_stale_seconds",
    label: "SSH: порог устаревания сессии, секунд",
    max: 86400,
  },
  {
    key: "llm_daily_token_limit_per_user",
    label: "AI: токенов на пользователя в сутки",
    max: 50000000,
    description: "0 — дневной лимит не задан.",
  },
  {
    key: "mcp_stdio_initialize_timeout_seconds",
    label: "MCP stdio: инициализация, секунд",
    min: 1,
    max: 600,
  },
  {
    key: "mcp_stdio_request_timeout_seconds",
    label: "MCP stdio: запрос, секунд",
    min: 1,
    max: 600,
  },
  {
    key: "mcp_stdio_tool_call_timeout_seconds",
    label: "MCP stdio: вызов инструмента, секунд",
    min: 1,
    max: 3600,
  },
  {
    key: "mcp_process_terminate_timeout_seconds",
    label: "MCP: завершение процесса, секунд",
    min: 1,
    max: 60,
  },
  {
    key: "mcp_http_connect_timeout_seconds",
    label: "MCP HTTP: подключение, секунд",
    min: 1,
    max: 300,
  },
  {
    key: "mcp_http_request_timeout_seconds",
    label: "MCP HTTP: запрос, секунд",
    min: 1,
    max: 600,
  },
  {
    key: "mcp_http_tool_call_timeout_seconds",
    label: "MCP HTTP: вызов инструмента, секунд",
    min: 1,
    max: 3600,
  },
  {
    key: "mcp_http_retry_attempts",
    label: "MCP HTTP: повторных попыток",
    max: 10,
  },
  {
    key: "mcp_runner_request_timeout_seconds",
    label: "MCP runner: запрос, секунд",
    min: 1,
    max: 3600,
  },
].map((field) => ({ ...field, type: "number" as const, min: field.min ?? 0 }));
const providers = ["gemini", "grok", "openai", "claude", "ollama"];
const providerOptions = [
  { value: "auto", label: "Автоматически" },
  ...providers.map((value) => ({
    value,
    label:
      {
        gemini: "Google Gemini",
        grok: "xAI Grok",
        openai: "OpenAI",
        claude: "Anthropic Claude",
        ollama: "Ollama",
      }[value] ?? value,
  })),
];

function SettingsField({
  field,
  value,
  onChange,
  disabled = false,
}: {
  field: SettingField;
  value: SettingValue;
  onChange: (value: SettingValue) => void;
  disabled?: boolean;
}) {
  if (field.type === "toggle")
    return (
      <CheckField
        label={field.label}
        description={field.description}
        checked={!!value}
        disabled={disabled}
        onChange={onChange}
      />
    );
  return (
    <FormField label={field.label} description={field.description}>
      {(id) =>
        field.type === "select" ? (
          <select
            id={id}
            value={String(value ?? "")}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
          >
            {!field.options?.some(
              (option) => option.value === String(value ?? ""),
            ) && (
              <option value={String(value ?? "")}>
                {String(value || "Не задано")}
              </option>
            )}
            {field.options?.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            id={id}
            type={
              field.type === "number"
                ? "number"
                : field.type === "url"
                  ? "url"
                  : "text"
            }
            value={String(value ?? "")}
            min={field.min}
            max={field.max}
            step={field.type === "number" ? 1 : undefined}
            required={field.type === "number"}
            onChange={(e) =>
              onChange(
                field.type === "number"
                  ? e.target.value === ""
                    ? null
                    : Number(e.target.value)
                  : e.target.value,
              )
            }
            disabled={disabled}
          />
        )
      }
    </FormField>
  );
}

function SettingsForm({
  data,
  kind,
}: {
  data: SettingsResponse;
  kind: "general" | "identity" | "limits";
}) {
  const [draft, setDraft] = useState<Record<string, SettingValue>>({});
  const [confirm, setConfirm] = useState(false);
  const [saved, setSaved] = useState("");
  const fields =
    kind === "general"
      ? auditFields
      : kind === "identity"
        ? identityFields
        : limitFields;
  const mutation = useGovernanceMutation(
    () => api.post("/api/settings/", draft),
    () => {
      setDraft({});
      setConfirm(false);
      setSaved("Настройки сохранены и перечитаны с сервера.");
    },
  );
  const invalid = fields.some(
    (field) => field.type === "number" && draft[field.key] === null,
  );
  const value = (key: string) =>
    key in draft ? draft[key] : (data.config[key] ?? null);
  const update = (key: string, next: SettingValue) => {
    setSaved("");
    setDraft((current) => ({ ...current, [key]: next }));
  };
  const title =
    kind === "general"
      ? "Журналирование и хранение"
      : kind === "identity"
        ? "Корпоративный вход"
        : "Лимиты и таймауты";
  return (
    <>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (kind === "identity") setConfirm(true);
          else mutation.mutate();
        }}
      >
        <Feedback error={mutation.error} success={saved} />
        <Panel
          title={title}
          description={
            kind === "limits"
              ? "Ограничения конкурентных операций и времени ожидания. Значения применяются к новым операциям."
              : kind === "identity"
                ? "Управление входом через доверенный корпоративный прокси."
                : "Определите состав журнала и срок хранения событий."
          }
          actions={
            <Button
              variant="primary"
              type="submit"
              disabled={!Object.keys(draft).length || invalid}
              loading={mutation.isPending}
            >
              <Save size={15} />
              Сохранить
            </Button>
          }
        >
          <fieldset
            disabled={mutation.isPending}
            className={
              kind === "general" ? "gov-settings-fields" : "gov-form-grid"
            }
          >
            {fields.map((field) => (
              <SettingsField
                key={field.key}
                field={field}
                value={value(field.key)}
                onChange={(next) => update(field.key, next)}
              />
            ))}
          </fieldset>
          {Object.keys(draft).length > 0 && (
            <div className="gov-unsaved" role="status">
              <span>{Object.keys(draft).length} несохранённых изменений</span>
              <Button variant="ghost" size="sm" onClick={() => setDraft({})}>
                Отменить изменения
              </Button>
            </div>
          )}
        </Panel>
      </form>
      {kind === "identity" && (
        <Panel
          title="LDAP"
          description="Параметры каталога задаются в конфигурации развёртывания и применяются при запуске сервера."
          actions={
            <StatusBadge status={data.ldap_status.severity}>
              {data.ldap_status.enabled ? "Включён" : "Отключён"}
            </StatusBadge>
          }
        >
          <div className="gov-definition-grid">
            {[
              ["Модуль аутентификации", data.ldap_status.backend_loaded],
              ["Сервер каталога", data.ldap_status.server_configured],
              ["База поиска", data.ldap_status.search_base_configured],
              [
                "Учётная запись подключения",
                data.ldap_status.bind_dn_configured,
              ],
              ["Пароль подключения", data.ldap_status.bind_password_configured],
              ["StartTLS", data.ldap_status.start_tls],
              [
                "Сертификат центра сертификации",
                data.ldap_status.ca_cert_configured,
              ],
            ].map(([label, configured]) => (
              <div key={String(label)}>
                <span>{label}</span>
                <StatusBadge status={configured ? "ready" : "disabled"}>
                  {configured ? "Настроено" : "Не задано"}
                </StatusBadge>
              </div>
            ))}
          </div>
          {data.ldap_status.missing.length > 0 && (
            <div className="notice notice-warning">
              Нужно настроить: {data.ldap_status.missing.join(", ")}.
            </div>
          )}
          {data.ldap_status.ignore_cert && (
            <div className="notice notice-warning">
              Проверка сертификата LDAP отключена в конфигурации сервера.
            </div>
          )}
        </Panel>
      )}
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Изменить корпоративный вход?"
        description="Новые параметры затронут последующие входы пользователей. Проверьте соответствие доверенному прокси и наличие локальной административной учётной записи."
        pending={mutation.isPending}
        confirmLabel="Применить настройки"
        onConfirm={() => mutation.mutate()}
      />
    </>
  );
}
function ConfigContent({ kind }: { kind: "general" | "identity" | "limits" }) {
  const query = useQuery({
    queryKey: ["governance", "settings"],
    queryFn: ({ signal }) => governanceApi.settings(signal),
  });
  return (
    <>
      <PageHeader
        eyebrow="Настройки платформы"
        title={
          kind === "general"
            ? "Общие настройки"
            : kind === "identity"
              ? "Корпоративный вход"
              : "Лимиты выполнения"
        }
        description={
          kind === "general"
            ? "Хранение событий, журналирование и параметры платформы."
            : kind === "identity"
              ? "Доменная авторизация и состояние подключения к LDAP."
              : "Предсказуемое потребление ресурсов для пользователей и команд."
        }
        actions={
          <Button
            onClick={() => void query.refetch()}
            loading={query.isFetching}
          >
            <RefreshCw size={15} />
            Обновить
          </Button>
        }
      />
      {kind === "general" && (
        <nav className="gov-settings-links">
          <Link to="/settings/identity">
            Корпоративный вход <ArrowUpRight size={15} />
          </Link>
          <Link to="/settings/limits">
            Лимиты выполнения <ArrowUpRight size={15} />
          </Link>
          <Link to="/settings/readiness">
            Готовность платформы <ArrowUpRight size={15} />
          </Link>
        </nav>
      )}
      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <SettingsForm data={query.data} kind={kind} />
      )}
    </>
  );
}
export function GeneralSettingsPage() {
  return (
    <GovernanceGuard staff>
      <ConfigContent kind="general" />
    </GovernanceGuard>
  );
}
export function IdentitySettingsPage() {
  return (
    <GovernanceGuard staff>
      <ConfigContent kind="identity" />
    </GovernanceGuard>
  );
}
export function LimitsSettingsPage() {
  return (
    <GovernanceGuard staff>
      <ConfigContent kind="limits" />
    </GovernanceGuard>
  );
}

export function PlatformAiSettings() {
  const { user } = useSession();
  const query = useQuery({
    queryKey: ["governance", "settings"],
    queryFn: ({ signal }) => governanceApi.settings(signal),
  });
  if (!user?.can_manage_ai_routing)
    return (
      <GovernanceGuard ai>
        <></>
      </GovernanceGuard>
    );
  return query.isPending ? (
    <LoadingState />
  ) : query.error ? (
    <ErrorState error={query.error} retry={() => void query.refetch()} />
  ) : (
    <PlatformAiForm data={query.data} />
  );
}
function PlatformAiForm({ data }: { data: SettingsResponse }) {
  const [draft, setDraft] = useState<Record<string, SettingValue>>({});
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [clearKey, setClearKey] = useState<string | null>(null);
  const [selectedProvider, setSelectedProvider] = useState("openai");
  const query = useQuery({
    queryKey: ["governance", "models"],
    queryFn: ({ signal }) =>
      api.get<Record<string, unknown>>("/api/models/", signal),
  });
  const save = useGovernanceMutation(
    () =>
      api.post("/api/settings/", {
        ...draft,
        api_keys: Object.fromEntries(
          Object.entries(keys).filter(([, value]) => value.trim()),
        ),
      }),
    () => {
      setDraft({});
      setKeys({});
    },
  );
  const clear = useGovernanceMutation(
    (provider: string) =>
      api.post("/api/settings/", { clear_api_keys: [provider] }),
    () => setClearKey(null),
  );
  const refresh = useGovernanceMutation((provider: string) =>
    api.post("/api/models/refresh/", { provider }),
  );
  const value = (key: string) =>
    key in draft ? draft[key] : (data.config[key] ?? null);
  const update = (key: string, next: SettingValue) =>
    setDraft((current) => ({ ...current, [key]: next }));
  const models = (provider: string) => {
    const raw = query.data?.[provider];
    return Array.isArray(raw)
      ? raw
          .map((model) =>
            typeof model === "string"
              ? model
              : typeof model === "object" && model
                ? String(
                    (model as Record<string, unknown>).id ??
                      (model as Record<string, unknown>).name ??
                      "",
                  )
                : "",
          )
          .filter(Boolean)
      : [];
  };
  return (
    <>
      <Feedback
        error={save.error ?? clear.error ?? refresh.error}
        success={save.message || clear.message || refresh.message}
      />
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <Panel
          title="Назначение моделей"
          description="Операционные разделы используют централизованные настройки."
          actions={
            <Button
              variant="primary"
              type="submit"
              loading={save.isPending}
              disabled={
                !Object.keys(draft).length && !Object.values(keys).some(Boolean)
              }
            >
              <Save size={15} />
              Сохранить
            </Button>
          }
        >
          <fieldset className="gov-form-grid" disabled={save.isPending}>
            {[
              { role: "chat", label: "Ассистент" },
              { role: "agent", label: "Агенты" },
              { role: "orchestrator", label: "Оркестратор" },
            ].map(({ role, label }) => (
              <div key={role} className="gov-model-purpose">
                <h3>{label}</h3>
                <SettingsField
                  field={{
                    key: `${role}_llm_provider`,
                    label: "Провайдер",
                    type: "select",
                    options: [
                      { value: "", label: "Наследовать внутренний провайдер" },
                      ...providerOptions,
                    ],
                  }}
                  value={value(`${role}_llm_provider`)}
                  onChange={(next) => update(`${role}_llm_provider`, next)}
                />
                <FormField
                  label="Модель"
                  description="Пустое значение использует модель провайдера по умолчанию."
                >
                  {(id) => (
                    <>
                      <input
                        id={id}
                        list={`${id}-models`}
                        value={String(value(`${role}_llm_model`) ?? "")}
                        onChange={(e) =>
                          update(`${role}_llm_model`, e.target.value)
                        }
                      />
                      <datalist id={`${id}-models`}>
                        {models(
                          String(
                            value(`${role}_llm_provider`) ||
                              value("internal_llm_provider"),
                          ),
                        ).map((model) => (
                          <option key={model} value={model} />
                        ))}
                      </datalist>
                    </>
                  )}
                </FormField>
              </div>
            ))}
            <SettingsField
              field={{
                key: "default_provider",
                label: "Провайдер по умолчанию",
                type: "select",
                options: providerOptions,
              }}
              value={value("default_provider")}
              onChange={(next) => update("default_provider", next)}
            />
            <SettingsField
              field={{
                key: "internal_llm_provider",
                label: "Внутренние операции",
                type: "select",
                options: providerOptions,
              }}
              value={value("internal_llm_provider")}
              onChange={(next) => update("internal_llm_provider", next)}
            />
            <SettingsField
              field={{
                key: "openai_reasoning_effort",
                label: "Глубина рассуждений OpenAI",
                type: "select",
                options: [
                  "none",
                  "minimal",
                  "low",
                  "medium",
                  "high",
                  "xhigh",
                ].map((option) => ({ value: option, label: option })),
              }}
              value={value("openai_reasoning_effort")}
              onChange={(next) => update("openai_reasoning_effort", next)}
            />
          </fieldset>
        </Panel>
        <Panel
          title="Провайдеры и ключи"
          description="Сохранённые ключи недоступны для чтения. Новый ключ заменяет текущий."
        >
          <div className="gov-provider-tabs">
            {providers.map((provider) => (
              <Button
                key={provider}
                variant={
                  selectedProvider === provider ? "primary" : "secondary"
                }
                onClick={() => setSelectedProvider(provider)}
              >
                {
                  providerOptions.find((option) => option.value === provider)
                    ?.label
                }
              </Button>
            ))}
          </div>
          <div className="gov-form">
            <CheckField
              label="Провайдер включён"
              checked={!!value(`${selectedProvider}_enabled`)}
              onChange={(next) => update(`${selectedProvider}_enabled`, next)}
            />
            <div className="gov-row-actions">
              <StatusBadge
                status={
                  data.api_keys[`${selectedProvider}_set`]
                    ? "ready"
                    : "disabled"
                }
              >
                {data.api_keys[`${selectedProvider}_set`]
                  ? "Ключ / подключение настроены"
                  : "Не настроен"}
              </StatusBadge>
              <Button
                size="sm"
                onClick={() => refresh.mutate(selectedProvider)}
                loading={refresh.isPending}
              >
                <RefreshCw size={14} />
                Обновить каталог моделей
              </Button>
              {data.api_keys[`${selectedProvider}_set`] && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setClearKey(selectedProvider)}
                >
                  Удалить сохранённый ключ
                </Button>
              )}
            </div>
            <FormField
              label="Новый API-ключ"
              description="Поле очищается после успешного сохранения. Пустое поле сохраняет текущий ключ."
            >
              {(id) => (
                <input
                  id={id}
                  type="password"
                  autoComplete="new-password"
                  value={keys[selectedProvider] ?? ""}
                  onChange={(e) =>
                    setKeys((current) => ({
                      ...current,
                      [selectedProvider]: e.target.value,
                    }))
                  }
                />
              )}
            </FormField>
            <div className="gov-form-grid">
              <FormField label="Модель чата по умолчанию">
                {(id) => (
                  <>
                    <input
                      id={id}
                      list={`${id}-models`}
                      value={String(
                        value(`chat_model_${selectedProvider}`) ?? "",
                      )}
                      onChange={(e) =>
                        update(`chat_model_${selectedProvider}`, e.target.value)
                      }
                    />
                    <datalist id={`${id}-models`}>
                      {models(selectedProvider).map((model) => (
                        <option key={model} value={model} />
                      ))}
                    </datalist>
                  </>
                )}
              </FormField>
              {selectedProvider !== "claude" && (
                <FormField label="Модель агентов по умолчанию">
                  {(id) => (
                    <input
                      id={id}
                      value={String(
                        value(`agent_model_${selectedProvider}`) ?? "",
                      )}
                      onChange={(e) =>
                        update(
                          `agent_model_${selectedProvider}`,
                          e.target.value,
                        )
                      }
                    />
                  )}
                </FormField>
              )}
            </div>
            {selectedProvider === "ollama" && (
              <div className="gov-form-grid">
                {[
                  {
                    key: "ollama_base_url",
                    label: "Адрес локального Ollama",
                    type: "url" as const,
                  },
                  {
                    key: "ollama_cloud_base_url",
                    label: "Адрес облачного Ollama",
                    type: "url" as const,
                  },
                  {
                    key: "ollama_runtime_mode",
                    label: "Режим выполнения",
                    type: "select" as const,
                    options: ["auto", "local", "cloud"].map((option) => ({
                      value: option,
                      label: option,
                    })),
                  },
                  {
                    key: "ollama_cloud_enabled",
                    label: "Облачный Ollama включён",
                    type: "toggle" as const,
                  },
                  {
                    key: "ollama_think_mode",
                    label: "Рассуждения Ollama",
                    type: "select" as const,
                    options: ["", "off", "on", "low", "medium", "high"].map(
                      (option) => ({
                        value: option,
                        label: option || "По умолчанию",
                      }),
                    ),
                  },
                ].map((field) => (
                  <SettingsField
                    key={field.key}
                    field={field}
                    value={value(field.key)}
                    onChange={(next) => update(field.key, next)}
                  />
                ))}
              </div>
            )}
            {query.error && (
              <ErrorState
                error={query.error}
                retry={() => void query.refetch()}
              />
            )}
          </div>
        </Panel>
      </form>
      <ConfirmDialog
        open={!!clearKey}
        onOpenChange={(open) => {
          if (!open) setClearKey(null);
        }}
        title="Удалить API-ключ?"
        description={`Сохранённый ключ ${clearKey} будет удалён. Если ключ задан в окружении сервера, он продолжит использоваться.`}
        pending={clear.isPending}
        onConfirm={() => clearKey && clear.mutate(clearKey)}
        confirmLabel="Удалить ключ"
      />
    </>
  );
}

function ReadinessContent() {
  const query = useQuery({
    queryKey: ["governance", "readiness"],
    queryFn: ({ signal }) => governanceApi.readiness(signal),
    staleTime: 30000,
  });
  return (
    <>
      <PageHeader
        eyebrow="Настройки платформы"
        title="Готовность платформы"
        description="Проверка обязательных сервисов, конфигурации и рабочих процессов."
        actions={
          <Button
            onClick={() => void query.refetch()}
            loading={query.isFetching}
          >
            <RefreshCw size={15} />
            Проверить снова
          </Button>
        }
      />
      {query.isPending ? (
        <LoadingState label="Проверяем компоненты платформы…" />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <>
          <div className="gov-metrics">
            <Metric
              label="Готовы"
              value={query.data.summary.ready}
              icon={<CheckCircle2 size={17} />}
            />
            <Metric
              label="Требуют внимания"
              value={query.data.summary.warning}
            />
            <Metric label="Ошибки" value={query.data.summary.error} />
            <Metric label="Всего проверок" value={query.data.summary.total} />
          </div>
          <Panel
            title="Результаты проверок"
            actions={<StatusBadge status={query.data.status} />}
          >
            <div className="gov-readiness-list">
              {query.data.checks.map((check) => (
                <article key={check.key} className="gov-readiness">
                  <div>
                    <ShieldCheck size={20} />
                    <div>
                      <h3>{check.title}</h3>
                      <p>{check.message}</p>
                    </div>
                    <StatusBadge status={check.severity} />
                  </div>
                  {Object.keys(check.details).length > 0 && (
                    <JsonDetails
                      data={check.details}
                      label="Подробнее о проверке"
                    />
                  )}
                </article>
              ))}
            </div>
          </Panel>
        </>
      )}
    </>
  );
}
export function ReadinessPage() {
  return (
    <GovernanceGuard staff>
      <ReadinessContent />
    </GovernanceGuard>
  );
}
