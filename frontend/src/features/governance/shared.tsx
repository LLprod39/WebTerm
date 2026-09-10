import { useId, useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { ApiError } from "@/api/client";
import { useSession } from "@/app/session";
import { EmptyState, Field, LoadingState } from "@/components/ui";
import type { FeatureChoice, PermissionMap } from "@/api/governance";

export const profileLabels: Record<string, string> = {
  pilot_user: "Пользователь",
  pilot_operator: "Оператор",
  server_only: "Только серверы",
  operator_server_only: "Серверный оператор",
  operator_studio_runner: "Оператор сценариев",
  team_admin_no_secrets: "Администратор команды",
  platform_admin: "Администратор платформы",
  admin_full: "Полный доступ",
  custom: "Индивидуальный доступ",
  reset_defaults: "Сбросить к настройкам по умолчанию",
};
export const featureLabels: Record<string, string> = {
  servers: "Серверы",
  dashboard: "Обзор",
  agents: "Агенты",
  chat: "Ассистент",
  automation: "Автоматизация",
  ai_connections_personal: "Личные AI-подключения",
  ai_connections_admin: "Управление AI-подключениями",
  studio: "Студия",
  studio_pipelines: "Сценарии",
  studio_runs: "Запуски сценариев",
  studio_agents: "Конфигурации агентов",
  studio_skills: "Навыки",
  studio_mcp: "MCP-серверы",
  studio_notifications: "Уведомления",
  kubernetes: "Kubernetes",
  kubernetes_admin_read: "Kubernetes: просмотр администратора",
  kubernetes_admin_write: "Kubernetes: изменения администратора",
  kubernetes_break_glass: "Kubernetes: аварийный доступ",
  kubernetes_secret_read: "Kubernetes: чтение секретов",
  mars: "Проекты MARS",
  settings: "Настройки платформы",
  orchestrator: "Оркестратор",
  knowledge_base: "База знаний",
  web_research: "Веб-исследования",
};
export const sourceLabels: Record<string, string> = {
  user_explicit: "Личное правило",
  group_explicit: "Правило группы",
  staff_default: "Роль администратора",
  default_allow: "Базовый доступ",
  default_deny: "Базовое ограничение",
  explicit_opt_in: "Требуется назначение",
  settings_opt_in: "Требуется назначение",
  deployment_disabled: "Отключено в развёртывании",
  staff_required: "Требуется администратор",
};
export function dateTime(value?: string | null) {
  return value
    ? new Intl.DateTimeFormat("ru-RU", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "—";
}
export function GovernanceGuard({
  children,
  staff = false,
  feature = "settings",
  ai = false,
}: {
  children: ReactNode;
  staff?: boolean;
  feature?: string;
  ai?: boolean;
}) {
  const { user, loading } = useSession();
  if (loading) return <LoadingState />;
  if (
    !user ||
    !user.features[feature] ||
    (staff && !user.is_staff) ||
    (ai && !user.can_manage_ai_routing)
  )
    return (
      <EmptyState
        title="Недостаточно прав"
        description="Доступ к этому разделу предоставляется администратором платформы."
        icon={<ShieldCheck size={24} />}
      />
    );
  return <>{children}</>;
}
export function FormField({
  label,
  children,
  description,
  error,
}: {
  label: string;
  children: (id: string) => ReactNode;
  description?: string;
  error?: string;
}) {
  const id = useId();
  return (
    <Field htmlFor={id} label={label} description={description} error={error}>
      {children(id)}
    </Field>
  );
}
export function CheckField({
  label,
  description,
  checked,
  onChange,
  disabled = false,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="gov-check">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
      />
      <span>
        {label}
        {description && <small>{description}</small>}
      </span>
    </label>
  );
}
export function useGovernanceMutation<T>(
  mutationFn: (data: T) => Promise<unknown>,
  onSuccess?: () => void,
) {
  const client = useQueryClient();
  const [message, setMessage] = useState("");
  const mutation = useMutation({
    mutationFn,
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["governance"] });
      await client.invalidateQueries({ queryKey: ["session"] });
      setMessage("Изменения сохранены.");
      onSuccess?.();
    },
  });
  return { ...mutation, message, clearMessage: () => setMessage("") };
}
export function fieldError(error: unknown, name: string) {
  if (
    !(error instanceof ApiError) ||
    !error.details ||
    typeof error.details !== "object"
  )
    return undefined;
  const details = error.details as {
    fields?: Record<string, unknown>;
    errors?: Record<string, unknown>;
  };
  const value = details.fields?.[name] ?? details.errors?.[name];
  return Array.isArray(value)
    ? value.join(", ")
    : typeof value === "string"
      ? value
      : undefined;
}
export function PermissionEditor({
  features,
  value,
  onChange,
  effective,
  sources,
}: {
  features: FeatureChoice[];
  value: PermissionMap;
  onChange: (value: PermissionMap) => void;
  effective?: Record<string, boolean>;
  sources?: Record<string, string>;
}) {
  return (
    <div className="gov-permission-list">
      {features.map((feature) => (
        <div className="gov-permission" key={feature.value}>
          <div>
            <strong>{featureLabels[feature.value] ?? feature.label}</strong>
            {sources && (
              <small>
                {sourceLabels[sources[feature.value]] ?? sources[feature.value]}
                {effective
                  ? ` · ${effective[feature.value] ? "Разрешено" : "Запрещено"}`
                  : ""}
              </small>
            )}
          </div>
          <select
            aria-label={`Доступ: ${featureLabels[feature.value] ?? feature.label}`}
            value={
              value[feature.value] == null
                ? "inherit"
                : value[feature.value]
                  ? "allow"
                  : "deny"
            }
            onChange={(e) =>
              onChange({
                ...value,
                [feature.value]:
                  e.target.value === "inherit"
                    ? null
                    : e.target.value === "allow",
              })
            }
          >
            <option value="inherit">Наследовать</option>
            <option value="allow">Разрешить</option>
            <option value="deny">Запретить</option>
          </select>
        </div>
      ))}
    </div>
  );
}
export function UnsavedClose({
  dirty,
  onClose,
}: {
  dirty: boolean;
  onClose: () => void;
}) {
  return (
    <button
      type="button"
      className="btn btn-secondary btn-md"
      onClick={() => {
        if (!dirty || window.confirm("Закрыть без сохранения изменений?"))
          onClose();
      }}
    >
      Отмена
    </button>
  );
}
