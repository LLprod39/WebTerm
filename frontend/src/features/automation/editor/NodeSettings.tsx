import { Trash2, X } from "lucide-react";
import type { NodeManifest, ServerOption, Values } from "@/api/automation";
import { Button, EmptyState, Field } from "@/components/ui";
import { SchemaFields } from "../shared";
import type { CanvasNode } from "../graph";
import { resolveCatalog } from "./catalog";

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
  onClose: () => void;
}) {
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
            />
          </Field>
          <p className="muted text-sm">
            Поток идёт слева направо. Правая точка — выход, левая — вход. Кнопка
            «+» на узле добавляет следующий шаг.
          </p>
        </div>
        <div className="auto-node-settings-foot">
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

  return (
    <aside className="auto-node-settings" aria-label="Свойства шага">
      <div className="auto-node-settings-head">
        <div className="auto-node-settings-title">
          <span className={`auto-node-picker-icon auto-step-${catalog.group}`}>
            <Icon size={18} />
          </span>
          <div>
            <h2>{catalog.title}</h2>
            <small>{node.data.backend.type}</small>
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
        {manifest ? (
          <>
            <p className="auto-muted">{manifest.purpose}</p>
            {manifest.mutates_state && (
              <p className="notice notice-warning">
                Этот шаг изменяет состояние инфраструктуры.
              </p>
            )}
            <SchemaFields
              key={node.id}
              schema={manifest.input_schema}
              value={node.data.backend.data}
              onChange={onChange}
              servers={servers}
              prefix={node.id}
            />
          </>
        ) : (
          <EmptyState
            title="Тип шага недоступен"
            description="Проверьте подключённые плагины. Существующие настройки сохранены."
          />
        )}
      </div>
      <div className="auto-node-settings-foot">
        <Button
          variant="ghost"
          onClick={onDelete}
          aria-label="Удалить выбранный шаг"
        >
          <Trash2 size={14} />
          Удалить шаг
        </Button>
        <Button variant="primary" onClick={onClose}>
          Готово
        </Button>
      </div>
    </aside>
  );
}
