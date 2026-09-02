import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  MarkerType,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";
import { Plus, Trash2 } from "lucide-react";

export type StepEdgeData = {
  onInsert?: (edgeId: string) => void;
  onDelete?: (edgeId: string) => void;
  readOnly?: boolean;
};

export type StepEdgeType = Edge<StepEdgeData, "step">;

export function StepEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  label,
  data,
  selected,
}: EdgeProps<StepEdgeType>) {
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });
  const readOnly = data?.readOnly;

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={{
          ...style,
          strokeWidth: selected ? 2.4 : 1.8,
        }}
      />
      <EdgeLabelRenderer>
        <div
          className={`auto-edge-label${selected ? " selected" : ""}`}
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
          }}
        >
          {label ? <span className="auto-edge-branch">{label}</span> : null}
          {!readOnly && (
            <div className="auto-edge-toolbar">
              <button
                type="button"
                aria-label="Вставить шаг"
                onClick={(event) => {
                  event.stopPropagation();
                  data?.onInsert?.(id);
                }}
              >
                <Plus size={12} />
              </button>
              <button
                type="button"
                aria-label="Удалить связь"
                onClick={(event) => {
                  event.stopPropagation();
                  data?.onDelete?.(id);
                }}
              >
                <Trash2 size={12} />
              </button>
            </div>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

export const pipelineEdgeTypes = { step: StepEdge };

export const DEFAULT_EDGE_OPTIONS = {
  type: "step" as const,
  animated: false,
  style: { strokeWidth: 1.8 },
  markerEnd: {
    type: MarkerType.ArrowClosed,
    width: 16,
    height: 16,
  },
};
