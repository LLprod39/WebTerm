import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Copy, Plus, Settings2, Trash2 } from "lucide-react";
import { StatusBadge } from "@/components/ui";
import type { CanvasNode } from "../../graph";
import { resolveCatalog } from "../catalog";

function StepNode({ data, selected, id }: NodeProps<CanvasNode>) {
  const trigger = data.backend.type.startsWith("trigger/");
  const catalog = resolveCatalog(data.backend.type);
  const Icon = catalog.icon;
  const label = String(
    data.backend.data.label || catalog.title || data.backend.type,
  );
  const handles = data.handles.length ? data.handles : ["out"];
  const connected = data.connectedHandles ?? [];
  const issues = data.issueCount ?? 0;
  const actions = data.actions;

  return (
    <div
      className={`auto-step auto-step-${catalog.group}${selected ? " selected" : ""}${data.runView ? " run-view" : ""}`}
      data-run-status={data.runView ? data.status || "unreported" : undefined}
    >
      {!data.runView && (
        <div className="auto-step-toolbar">
          <button
            type="button"
            aria-label="Настроить шаг"
            onClick={(event) => {
              event.stopPropagation();
              actions?.onConfigure?.(id);
            }}
          >
            <Settings2 size={13} />
          </button>
          <button
            type="button"
            aria-label="Дублировать шаг"
            onClick={(event) => {
              event.stopPropagation();
              actions?.onDuplicate?.(id);
            }}
          >
            <Copy size={13} />
          </button>
          <button
            type="button"
            aria-label="Удалить шаг"
            onClick={(event) => {
              event.stopPropagation();
              actions?.onDelete?.(id);
            }}
          >
            <Trash2 size={13} />
          </button>
        </div>
      )}

      {!trigger && (
        <Handle
          type="target"
          position={Position.Left}
          className="auto-step-handle auto-step-handle-in"
        />
      )}

      <div className="auto-step-tile" title={catalog.description}>
        <Icon size={28} strokeWidth={1.6} />
        {issues > 0 && !data.runView && (
          <span className="auto-step-issue" title="Есть незаполненные поля">
            !
          </span>
        )}
        {data.status ? (
          <span className="auto-step-status">
            <StatusBadge status={data.status} />
          </span>
        ) : data.runView ? (
          <span className="auto-step-status auto-node-unreported">
            Нет результата
          </span>
        ) : null}
        {!data.runView && trigger && (
          <span className="auto-step-status">
            <StatusBadge
              status={data.backend.data.is_active ? "active" : "disabled"}
            />
          </span>
        )}
      </div>

      <div className="auto-step-label">
        <strong>{label}</strong>
        <small>{catalog.title}</small>
      </div>

      {handles.map((handle, index) => {
        const top = `${((index + 1) * 100) / (handles.length + 1)}%`;
        const isConnected = connected.includes(handle);
        return (
          <span key={handle} className="auto-step-out-wrap" style={{ top }}>
            {handles.length > 1 && (
              <span className="auto-step-handle-label">{handle}</span>
            )}
            <Handle
              id={handle}
              type="source"
              position={Position.Right}
              className="auto-step-handle auto-step-handle-out"
            />
            {!data.runView && !isConnected && (
              <button
                type="button"
                className="auto-step-add"
                aria-label={`Добавить шаг после ${handle}`}
                onClick={(event) => {
                  event.stopPropagation();
                  actions?.onAddOutput?.(id, handle);
                }}
              >
                <Plus size={12} strokeWidth={2.5} />
              </button>
            )}
          </span>
        );
      })}
    </div>
  );
}

export const pipelineNodeTypes = { workflow: StepNode };
