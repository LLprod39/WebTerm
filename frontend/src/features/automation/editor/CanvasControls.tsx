import {
  LayoutDashboard,
  LocateFixed,
  Map as MapIcon,
  Maximize2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useReactFlow } from "@xyflow/react";
import { Button } from "@/components/ui";

export function CanvasControls({
  showMinimap,
  onToggleMinimap,
  onLayout,
}: {
  showMinimap: boolean;
  onToggleMinimap: () => void;
  onLayout: () => void;
}) {
  const { zoomIn, zoomOut, fitView, setViewport, getViewport } = useReactFlow();

  return (
    <div className="auto-canvas-controls" role="toolbar" aria-label="Холст">
      <Button
        size="icon"
        variant="ghost"
        aria-label="Увеличить"
        onClick={() => zoomIn({ duration: 180 })}
      >
        <ZoomIn size={15} />
      </Button>
      <Button
        size="icon"
        variant="ghost"
        aria-label="Уменьшить"
        onClick={() => zoomOut({ duration: 180 })}
      >
        <ZoomOut size={15} />
      </Button>
      <Button
        size="icon"
        variant="ghost"
        aria-label="Вписать в экран"
        onClick={() => fitView({ padding: 0.2, duration: 220 })}
      >
        <Maximize2 size={15} />
      </Button>
      <Button
        size="icon"
        variant="ghost"
        aria-label="Масштаб 100%"
        onClick={() => {
          const { x, y } = getViewport();
          void setViewport({ x, y, zoom: 1 }, { duration: 180 });
        }}
      >
        <LocateFixed size={15} />
      </Button>
      <Button
        size="icon"
        variant="ghost"
        aria-label="Разложить поток"
        onClick={onLayout}
      >
        <LayoutDashboard size={15} />
      </Button>
      <Button
        size="icon"
        variant="ghost"
        aria-label={showMinimap ? "Скрыть миникарту" : "Показать миникарту"}
        aria-pressed={showMinimap}
        onClick={onToggleMinimap}
      >
        <MapIcon size={15} />
      </Button>
    </div>
  );
}
