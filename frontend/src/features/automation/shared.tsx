import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import type {
  Json,
  Schema,
  Values,
  ServerOption,
  Validation,
} from "@/api/automation";
import { Button, Field, StatusBadge } from "@/components/ui";

const nodePlural = new Intl.PluralRules("ru");
export function formatNodeCount(count: number) {
  const form = nodePlural.select(count);
  return `${count} ${form === "one" ? "узел" : form === "few" ? "узла" : "узлов"}`;
}

export function KeyValues({
  value,
  onChange,
  label = "Переменные",
  secret = false,
}: {
  value: Values;
  onChange: (v: Values) => void;
  label?: string;
  secret?: boolean;
}) {
  const [newKey, setNewKey] = useState("");
  return (
    <fieldset className="auto-key-values">
      <legend>{label}</legend>
      {Object.entries(value).map(([key, val]) => (
        <div className="auto-kv-row" key={key}>
          <code>{key}</code>
          <ValueInput
            value={val}
            label={`${label}: ${key}`}
            secret={secret}
            onChange={(next) => onChange({ ...value, [key]: next })}
          />
          <Button
            size="icon"
            variant="ghost"
            aria-label={`Удалить ${key}`}
            onClick={() => {
              const next = { ...value };
              delete next[key];
              onChange(next);
            }}
          >
            <Trash2 size={14} />
          </Button>
        </div>
      ))}
      <div className="auto-kv-add">
        <input
          aria-label={`Имя: ${label}`}
          placeholder="Имя переменной"
          value={newKey}
          onChange={(e) => setNewKey(e.target.value)}
        />
        <Button
          size="sm"
          disabled={!newKey.trim() || newKey.trim() in value}
          onClick={() => {
            onChange({ ...value, [newKey.trim()]: "" });
            setNewKey("");
          }}
        >
          <Plus size={14} />
          Добавить
        </Button>
      </div>
    </fieldset>
  );
}
function ValueInput({
  value,
  onChange,
  label,
  secret = false,
}: {
  value: Json;
  onChange: (value: Json) => void;
  label: string;
  secret?: boolean;
}) {
  const kind =
    value === null ? "null" : Array.isArray(value) ? "array" : typeof value;
  return (
    <div className="auto-value-input">
      {!secret && (
        <select
          className="auto-value-type"
          aria-label={`Тип ${label}`}
          value={kind}
          onChange={(e) =>
            onChange(
              (
                {
                  string: "",
                  number: 0,
                  boolean: false,
                  array: [],
                  object: {},
                  null: null,
                } as Record<string, Json>
              )[e.target.value],
            )
          }
        >
          <option value="string">Текст</option>
          <option value="number">Число</option>
          <option value="boolean">Да / нет</option>
          <option value="array">Список</option>
          <option value="object">Группа</option>
          <option value="null">Пустое</option>
        </select>
      )}
      {Array.isArray(value) ? (
        <div className="auto-value-list">
          {value.map((item, index) => (
            <div className="auto-value-item" key={index}>
              <ValueInput
                label={`${label}, ${index + 1}`}
                value={item}
                onChange={(next) =>
                  onChange(value.map((v, i) => (i === index ? next : v)))
                }
              />
              <Button
                size="icon"
                variant="ghost"
                aria-label={`Удалить ${label}, ${index + 1}`}
                onClick={() => onChange(value.filter((_, i) => i !== index))}
              >
                <Trash2 size={12} />
              </Button>
            </div>
          ))}
          <Button size="sm" onClick={() => onChange([...value, ""])}>
            Добавить значение
          </Button>
        </div>
      ) : value && typeof value === "object" ? (
        <KeyValues value={value} label={label} onChange={onChange} />
      ) : typeof value === "boolean" ? (
        <label className="auto-check-row">
          <input
            type="checkbox"
            aria-label={label}
            checked={value}
            onChange={(e) => onChange(e.target.checked)}
          />
          {value ? "Да" : "Нет"}
        </label>
      ) : value === null ? (
        <span className="auto-muted">Значение не задано</span>
      ) : (
        <input
          aria-label={label}
          type={
            secret ? "password" : typeof value === "number" ? "number" : "text"
          }
          value={String(value ?? "")}
          onChange={(e) =>
            onChange(
              typeof value === "number"
                ? Number(e.target.value)
                : e.target.value,
            )
          }
        />
      )}
    </div>
  );
}
export function TargetPicker({
  servers,
  value,
  onChange,
}: {
  servers: ServerOption[];
  value: number[];
  onChange: (ids: number[]) => void;
}) {
  return (
    <fieldset className="auto-targets">
      <legend>Целевые серверы</legend>
      {servers.length === 0 ? (
        <p className="muted">Нет доступных серверов.</p>
      ) : (
        servers.map((s) => (
          <label className="auto-check-row" key={s.id}>
            <input
              type="checkbox"
              checked={value.includes(s.id)}
              onChange={(e) =>
                onChange(
                  e.target.checked
                    ? [...value, s.id]
                    : value.filter((x) => x !== s.id),
                )
              }
            />
            <span>
              <strong>{s.name}</strong>
              <small>{s.host}</small>
            </span>
          </label>
        ))
      )}
    </fieldset>
  );
}
const labels: Record<string, string> = {
  label: "Название узла",
  is_active: "Триггер включён",
  command: "Команда",
  prompt: "Запрос",
  system_prompt: "Системная инструкция",
  goal: "Цель",
  server_id: "Сервер",
  server_ids: "Доступные серверы",
  cron_expression: "Расписание cron",
  permission_mode: "Режим выполнения",
  sudo_policy: "Повышение привилегий",
  on_failure: "При ошибке",
  dry_run: "Проверка без изменений",
  preflight_commands: "Предварительные проверки",
  verification_commands: "Проверки результата",
  max_iterations: "Лимит итераций",
  retry_max_attempts: "Число попыток",
  retry_initial_delay_seconds: "Задержка повтора, сек",
  retry_backoff_multiplier: "Множитель задержки",
  retry_max_delay_seconds: "Максимальная задержка, сек",
  retry_non_idempotent: "Разрешить повтор действий с изменениями",
  arguments: "Аргументы инструмента",
  tool_name: "Имя инструмента",
  source_node_id: "Исходный узел",
  check_type: "Условие",
  check_value: "Значение",
  timeout_seconds: "Таймаут, сек",
  message: "Сообщение",
  subject: "Тема",
  url: "URL",
  method: "HTTP метод",
  path: "Путь",
  content: "Содержимое",
};
export function SchemaFields({
  schema,
  value,
  onChange,
  servers = [],
  prefix = "node",
}: {
  schema: Schema;
  value: Values;
  onChange: (v: Values) => void;
  servers?: ServerOption[];
  prefix?: string;
}) {
  return (
    <div className="auto-form">
      {Object.entries(schema.properties ?? {}).map(([key, field]) => {
        const id = `${prefix}-${key}`;
        const val = value[key] ?? field.default ?? "";
        const change = (next: Json) => onChange({ ...value, [key]: next });
        const label =
          (field.title || labels[key] || key.replaceAll("_", " ")) +
          (schema.required?.includes(key) ? " *" : "");
        if (key === "arguments_text") return null;
        if (field.type === "boolean")
          return (
            <label className="auto-check-row" key={key}>
              <input
                id={id}
                type="checkbox"
                checked={val === true || val === "true"}
                onChange={(e) => change(e.target.checked)}
              />
              <span>
                {label}
                {field.description && <small>{field.description}</small>}
              </span>
            </label>
          );
        if (key === "server_ids")
          return (
            <TargetPicker
              key={key}
              servers={servers}
              value={
                Array.isArray(val)
                  ? val.filter((x): x is number => typeof x === "number")
                  : []
              }
              onChange={change}
            />
          );
        if (field.type === "object" && field.properties)
          return (
            <fieldset key={key} className="auto-key-values">
              <legend>{label}</legend>
              <SchemaFields
                schema={field}
                value={
                  val && typeof val === "object" && !Array.isArray(val)
                    ? val
                    : {}
                }
                onChange={change}
                servers={servers}
                prefix={id}
              />
            </fieldset>
          );
        if (field.type === "array" && field.items?.type === "object")
          return (
            <Field key={key} label={label}>
              <ValueInput
                label={label}
                value={Array.isArray(val) ? val : []}
                onChange={change}
              />
            </Field>
          );
        if (field.type === "object")
          return (
            <KeyValues
              key={key}
              label={label}
              value={
                val && typeof val === "object" && !Array.isArray(val) ? val : {}
              }
              onChange={change}
            />
          );
        return (
          <Field
            key={key}
            label={label}
            htmlFor={id}
            description={field.description}
          >
            {key === "server_id" ? (
              <select
                id={id}
                value={String(val)}
                onChange={(e) =>
                  change(e.target.value ? Number(e.target.value) : "")
                }
              >
                <option value="">Из контекста</option>
                {servers.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            ) : field.enum ? (
              <select
                id={id}
                value={String(val)}
                onChange={(e) =>
                  change(
                    field.enum!.find(
                      (item) => String(item) === e.target.value,
                    ) ?? e.target.value,
                  )
                }
              >
                {!val && <option value="">Выберите…</option>}
                {field.enum.map((item) => (
                  <option key={String(item)} value={String(item)}>
                    {String(item)}
                  </option>
                ))}
              </select>
            ) : field.type === "array" ? (
              <textarea
                id={id}
                rows={3}
                value={Array.isArray(val) ? val.join("\n") : String(val)}
                placeholder="По одному значению на строку"
                onChange={(e) =>
                  change(
                    e.target.value
                      .split("\n")
                      .filter(Boolean)
                      .map((item) =>
                        field.items?.type === "integer" ? Number(item) : item,
                      ),
                  )
                }
              />
            ) : field.type === "integer" || field.type === "number" ? (
              <input
                id={id}
                type="number"
                min={field.minimum}
                max={field.maximum}
                value={typeof val === "number" ? val : String(val)}
                onChange={(e) =>
                  change(e.target.value === "" ? "" : Number(e.target.value))
                }
              />
            ) : /(command|prompt|goal|message|content|instructions)/.test(
                key,
              ) ? (
              <textarea
                id={id}
                rows={4}
                value={String(val)}
                onChange={(e) => change(e.target.value)}
              />
            ) : (
              <input
                id={id}
                value={String(val)}
                onChange={(e) => change(e.target.value)}
              />
            )}
          </Field>
        );
      })}
    </div>
  );
}
export function ValidationResult({
  value,
  onNode,
}: {
  value: Validation;
  onNode?: (id: string) => void;
}) {
  const ok =
    value.ok ??
    ["valid", "passed", "ready", "success"].includes(value.status ?? "");
  const issues = value.issues ?? [];
  return (
    <div className="auto-validation" role="status">
      <StatusBadge status={ok ? "success" : "warning"}>
        {ok ? "Проверки пройдены" : value.status || "Есть замечания"}
      </StatusBadge>
      {(value.errors ?? [])
        .filter((error) => !issues.some((issue) => issue.message === error))
        .map((err, i) => (
          <p key={i}>{err}</p>
        ))}
      {issues.map((issue, i) => (
        <div className="auto-issue" key={i}>
          <StatusBadge
            status={issue.severity === "error" ? "error" : "warning"}
          />
          <span>{issue.message || issue.code || "Проверьте конфигурацию"}</span>
          {issue.next_action && (
            <small className="muted">{issue.next_action}</small>
          )}
          {onNode &&
            [
              ...new Set([
                ...(issue.node_ids ?? []),
                ...(issue.node_id ? [issue.node_id] : []),
              ]),
            ].map((nodeId) => (
              <Button
                key={nodeId}
                size="sm"
                onClick={() => onNode(nodeId)}
                title={nodeId}
              >
                К узлу
              </Button>
            ))}
        </div>
      ))}
    </div>
  );
}
export function duration(seconds: number | null | undefined) {
  if (seconds == null) return "—";
  return seconds < 60
    ? `${Math.round(seconds)} сек`
    : `${Math.floor(seconds / 60)} мин ${Math.round(seconds % 60)} сек`;
}
export const activeRun = (status?: string) =>
  !!status &&
  ["pending", "queued", "running", "hibernating", "preparing"].includes(status);
