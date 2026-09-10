import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Copy, Plus, Settings2, ShieldCheck, Trash2 } from "lucide-react";
import { StatusBadge } from "@/components/ui";
import type { CanvasNode } from "../../graph";
import {
  displayLabel,
  handleLabel,
  resolveCatalog,
  summarizeNode,
} from "../catalog";

function StepNode({ data, selected, id }: NodeProps<CanvasNode>) {
  const trigger = data.backend.type.startsWith("trigger/");
  const catalog = resolveCatalog(data.backend.type);
  const Icon = catalog.icon;
  const label = displayLabel(data.backend.type, data.backend.data);
  const handles = data.handles.length ? data.handles : ["out"];
  const multi = handles.length > 1;
  const connected = data.connectedHandles ?? [];
  // A node with no outgoing links shows its "+" persistently; once at least
  // one branch is wired the remaining ones only appear on hover/selection.
  const quiet = connected.length > 0;
  const issues = data.issueCount ?? 0;
  const actions = data.actions;
  const editing = !data.runView;
  const summary =
    data.summary ?? summarizeNode(data.backend.type, data.backend.data);
  const active = data.backend.data.is_active === true;

  const addButton = (handle: string) => (
    <button
      type="button"
      className={`auto-step-add nodrag nopan${quiet ? " quiet" : ""}`}
      aria-label={`Добавить шаг после ${handleLabel(handle)}`}
      title="Добавить следующий шаг"
      onClick={(event) => {
        event.stopPropagation();
        actions?.onAddOutput?.(id, handle);
      }}
    >
      <Plus size={12} strokeWidth={2.5} />
    </button>
  );

  return (
    <div
      className={[
        "auto-step",
        "auto-node",
        `auto-step-${catalog.group}`,
        selected ? "selected" : "",
        data.runView ? "run-view" : "",
        multi ? "auto-step-multi" : "",
        trigger && editing && !active ? "auto-step-off" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-run-status={data.runView ? data.status || "unreported" : undefined}
    >
      {editing && (
        <div className="auto-step-toolbar nodrag nopan">
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

      <div className="auto-step-card">
        <div className="auto-step-body">
          <span className="auto-step-icon" aria-hidden>
            <Icon size={17} strokeWidth={1.9} />
          </span>
          <div className="auto-step-text">
            <div className="auto-step-title">
              <strong title={label}>{label}</strong>
              {editing && data.approval && (
                <span
                  className="auto-step-flag"
                  title="Требует согласования перед выполнением"
                >
                  <ShieldCheck size={11} />
                </span>
              )}
            </div>
            <small className="auto-step-kind">{catalog.title}</small>
            {editing && summary && (
              <span className="auto-step-summary" title={summary}>
                {summary}
              </span>
            )}
            {editing && !summary && issues > 0 && (
              <span className="auto-step-summary auto-step-summary-empty">
                Не настроен
              </span>
            )}
          </div>
          {editing && issues > 0 && (
            <span
              className="auto-step-issue"
              title={`Незаполненных полей: ${issues}`}
            >
              {issues}
            </span>
          )}
          {editing && trigger && (
            <span
              className={`auto-step-power${active ? " on" : ""}`}
              title={active ? "Триггер включён" : "Триггер выключен"}
            />
          )}
        </div>

        {multi && (
          <ul className="auto-step-ports">
            {handles.map((handle) => (
              <li key={handle} className="auto-step-port">
                <span>{handleLabel(handle)}</span>
                <Handle
                  id={handle}
                  type="source"
                  position={Position.Right}
                  className="auto-step-handle auto-step-handle-out"
                />
                {editing && !connected.includes(handle) && addButton(handle)}
              </li>
            ))}
          </ul>
        )}

        {data.runView &&
          (data.status ? (
            <span className="auto-step-status">
              <StatusBadge status={data.status} />
            </span>
          ) : (
            <span className="auto-step-status auto-node-unreported">
              Нет результата
            </span>
          ))}
      </div>

      {!multi && (
        <>
          <Handle
            id={handles[0]}
            type="source"
            position={Position.Right}
            className="auto-step-handle auto-step-handle-out"
          />
          {editing && !connected.includes(handles[0]) && (
            <span className="auto-step-tail">{addButton(handles[0])}</span>
          )}
        </>
      )}

      {editing && data.ghost && (
        <button
          type="button"
          className="auto-step-ghost nodrag nopan"
          onClick={(event) => {
            event.stopPropagation();
            actions?.onAddOutput?.(id, handles[0]);
          }}
        >
          <span className="auto-step-ghost-icon" aria-hidden>
            <Plus size={16} />
          </span>
          <span>
            <strong>Добавить первый шаг</strong>
            <small>или нажмите Tab</small>
          </span>
        </button>
      )}
    </div>
  );
}

export const pipelineNodeTypes = { workflow: StepNode };
