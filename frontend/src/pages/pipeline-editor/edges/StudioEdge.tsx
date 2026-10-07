import {
  BaseEdge,
  EdgeLabelRenderer,
  MarkerType,
  getBezierPath,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";
import { Plus, Trash2 } from "lucide-react";

export type StudioEdgeData = {
  onInsert?: (edgeId: string, clientPosition: { x: number; y: number }) => void;
  onDelete?: (edgeId: string) => void;
  readOnly?: boolean;
};

export type StudioEdgeType = Edge<StudioEdgeData, "studio">;

export function StudioEdge({
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
}: EdgeProps<StudioEdgeType>) {
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
          strokeWidth: selected ? 2.4 : 2,
        }}
      />
      <EdgeLabelRenderer>
        <div
          className={`group pointer-events-auto absolute flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-1 nodrag nopan${
            selected ? " is-selected" : ""
          }`}
          style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
        >
          {label ? (
            <span className="rounded border border-border/70 bg-background/90 px-1.5 py-0.5 text-[10px] text-muted-foreground">
              {label}
            </span>
          ) : null}
          {!readOnly ? (
            <div
              className={`flex gap-0.5 rounded-md border border-border/80 bg-background/95 p-0.5 shadow-sm transition-opacity ${
                selected ? "opacity-100" : "opacity-0 group-hover:opacity-100"
              }`}
            >
              <button
                type="button"
                aria-label="Insert node"
                className="grid h-6 w-6 place-items-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                onClick={(event) => {
                  event.stopPropagation();
                  data?.onInsert?.(id, { x: event.clientX, y: event.clientY });
                }}
              >
                <Plus className="h-3 w-3" />
              </button>
              <button
                type="button"
                aria-label="Delete edge"
                className="grid h-6 w-6 place-items-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-destructive"
                onClick={(event) => {
                  event.stopPropagation();
                  data?.onDelete?.(id);
                }}
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ) : null}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

export const studioEdgeTypes = { studio: StudioEdge };

export const STUDIO_DEFAULT_EDGE_OPTIONS = {
  type: "studio" as const,
  animated: false,
  style: { strokeWidth: 2 },
  markerEnd: {
    type: MarkerType.ArrowClosed,
    width: 16,
    height: 16,
  },
};
