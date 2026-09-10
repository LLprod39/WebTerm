import { useMemo } from "react";
import { ArrowRight, ChevronDown, Trash2, X } from "lucide-react";
import type {
  NodeManifest,
  Schema,
  ServerOption,
  Values,
} from "@/api/automation";
import { Button, EmptyState, Field } from "@/components/ui";
import { SchemaFields } from "../shared";
import type { CanvasNode } from "../graph";
import { resolveCatalog } from "./catalog";

/**
 * Fields that most operators never touch on the first pass. They stay
 * available but folded under "Дополнительно" so the basic form fits on one
 * screen. Required fields are always shown in the main section.
 */
const ADVANCED_KEY =
  /^(retry_|.*_context_key$|permission_mode$|sudo_policy$|on_failure$|preflight_commands$|verification_commands$|max_iterations$|include_all_outputs$|manual_link_only$|skill_slugs$|mcp_server_ids$|agent_config_id$|allow_empty_content$|max_bytes$|retries$|body_contains$|headers$|extra_payload$|email_subject$|tg_chat_id$|telegram_message$|model$|system_prompt$|branch_mode$|merge_strategy$|verify$|lines$|limit$|max_depth$|max_files$|max_entries$|vacuum_|min_age_days$|max_age_hours$|include_logs$|expected_status$|timeout_seconds$|provider$|dry_run$|filter_text$|sections$)/;

function splitSchema(schema: Schema): { basic: Schema; advanced: Schema } {
  const required = new Set(schema.required ?? []);
  const basic: Record<string, Schema> = {};
  const advanced: Record<string, Schema> = {};
  for (const [key, field] of Object.entries(schema.properties ?? {})) {
    if (key === "label" || key === "arguments_text") continue;
    if (!required.has(key) && ADVANCED_KEY.test(key)) advanced[key] = field;
    else basic[key] = field;
  }
  return {
    basic: { ...schema, properties: basic },
    advanced: { ...schema, properties: advanced, required: [] },
  };
}

export function NodeSettings({
  mode,
  node,
  manifest,
  servers,
  issues,
  name,
  description,
  onName,
  onDescription,
  onChange,
  onDelete,
  onAddNext,
  onClose,
}: {
  mode: "node" | "process" | null;
  node?: CanvasNode;
  manifest?: NodeManifest;
  servers: ServerOption[];
  issues: string[];
  name: string;
  description: string;
  onName: (value: string) => void;
  onDescription: (value: string) => void;
  onChange: (data: Values) => void;
  onDelete: () => void;
  onAddNext?: () => void;
  onClose: () => void;
}) {
  const split = useMemo(
    () => (manifest ? splitSchema(manifest.input_schema) : null),
    [manifest],
  );

  if (!mode) return null;

  if (mode === "process") {
    return (
      <aside className="auto-node-settings" aria-label="Свойства процесса">
        <div className="auto-node-settings-head">
          <div>
            <h2>Свойства процесса</h2>
            <small>Название и описание рабочего процесса</small>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Закрыть"
            onClick={onClose}
          >
            <X size={16} />
          </Button>
        </div>
        <div className="auto-node-settings-body auto-form">
          <Field label="Название" htmlFor="editor-pipeline-name">
            <input
              id="editor-pipeline-name"
              value={name}
              onChange={(event) => onName(event.target.value)}
            />
          </Field>
          <Field label="Описание" htmlFor="editor-pipeline-description">
            <textarea
              id="editor-pipeline-description"
              value={description}
              onChange={(event) => onDescription(event.target.value)}
              placeholder="Что запускает процесс и какой результат ожидается"
            />
          </Field>
        </div>
        <div className="auto-node-settings-foot">
          <span />
          <Button variant="primary" onClick={onClose}>
            Готово
          </Button>
        </div>
      </aside>
    );
  }

  if (!node) return null;
  const catalog = resolveCatalog(node.data.backend.type, manifest);
  const Icon = catalog.icon;
  const trigger = node.data.backend.type.startsWith("trigger/");
  const hasAdvanced =
    split && Object.keys(split.advanced.properties ?? {}).length > 0;

  return (
    <aside className="auto-node-settings" aria-label="Свойства шага">
      <div className="auto-node-settings-head">
        <div className="auto-node-settings-title">
          <span className={`auto-node-picker-icon auto-step-${catalog.group}`}>
            <Icon size={17} strokeWidth={1.9} />
          </span>
          <div>
            <h2>{catalog.title}</h2>
            <small>{catalog.description}</small>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Закрыть"
          onClick={onClose}
        >
          <X size={16} />
        </Button>
      </div>
      <div className="auto-node-settings-body auto-form">
        <Field label="Название шага" htmlFor="node-label">
          <input
            id="node-label"
            value={String(node.data.backend.data.label ?? "")}
            onChange={(event) =>
              onChange({
                ...node.data.backend.data,
                label: event.target.value,
              })
            }
          />
        </Field>
        {issues.length > 0 && (
          <ul className="auto-node-issues">
            {issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        )}
        {manifest && split ? (
          <>
            {manifest.mutates_state && (
              <p className="notice notice-warning">
                Шаг изменяет состояние инфраструктуры.
                {manifest.supports_dry_run &&
                  " Для проверки без изменений включите «Проверка без изменений» в дополнительных настройках."}
              </p>
            )}
            <SchemaFields
              key={node.id}
              schema={split.basic}
              value={node.data.backend.data}
              onChange={onChange}
              servers={servers}
              prefix={node.id}
            />
            {hasAdvanced && (
              <details className="auto-node-advanced">
                <summary>
                  <ChevronDown size={14} aria-hidden />
                  Дополнительно
                  <span>
                    {Object.keys(split.advanced.properties ?? {}).length}
                  </span>
                </summary>
                <div className="auto-node-advanced-body">
                  <SchemaFields
                    key={`${node.id}-advanced`}
                    schema={split.advanced}
                    value={node.data.backend.data}
                    onChange={onChange}
                    servers={servers}
                    prefix={`${node.id}-adv`}
                  />
                </div>
              </details>
            )}
          </>
        ) : (
          <EmptyState
            title="Тип шага недоступен"
            description="Проверьте подключённые плагины. Существующие настройки сохранены."
          />
        )}
        <p className="auto-node-settings-type">
          <code>{node.data.backend.type}</code>
        </p>
      </div>
      <div className="auto-node-settings-foot">
        <Button
          variant="ghost"
          onClick={onDelete}
          aria-label="Удалить выбранный шаг"
        >
          <Trash2 size={14} />
          Удалить
        </Button>
        <div className="auto-node-settings-foot-actions">
          {onAddNext && (
            <Button onClick={onAddNext}>
              {trigger ? "Первый шаг" : "Следующий шаг"}
              <ArrowRight size={14} />
            </Button>
          )}
          <Button variant="primary" onClick={onClose}>
            Готово
          </Button>
        </div>
      </div>
    </aside>
  );
}
