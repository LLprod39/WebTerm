import { type DragEvent, type ReactNode, useRef, useState } from "react";

import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface XTerminalDropZoneProps {
  onFilesDrop?: (files: File[]) => void;
  children: ReactNode;
}

function eventHasFiles(event: DragEvent<HTMLDivElement>) {
  return event.dataTransfer?.types?.includes("Files") ?? false;
}

export function XTerminalDropZone({ onFilesDrop, children }: XTerminalDropZoneProps) {
  const { lang } = useI18n();
  const dragDepthRef = useRef(0);
  const [isDragActive, setIsDragActive] = useState(false);

  return (
    <div
      className="relative h-full w-full min-h-[200px]"
      onDragEnter={(event) => {
        if (!onFilesDrop || !eventHasFiles(event)) return;
        event.preventDefault();
        dragDepthRef.current += 1;
        setIsDragActive(true);
      }}
      onDragOver={(event) => {
        if (!onFilesDrop || !eventHasFiles(event)) return;
        event.preventDefault();
      }}
      onDragLeave={(event) => {
        if (!onFilesDrop) return;
        event.preventDefault();
        dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
        if (dragDepthRef.current === 0) {
          setIsDragActive(false);
        }
      }}
      onDrop={(event) => {
        if (!onFilesDrop || !event.dataTransfer?.files?.length) return;
        event.preventDefault();
        dragDepthRef.current = 0;
        setIsDragActive(false);
        onFilesDrop(Array.from(event.dataTransfer.files));
      }}
    >
      {children}
      <div
        className={cn(
          "pointer-events-none absolute inset-0 z-20 flex items-center justify-center bg-primary/10 opacity-0 transition-opacity",
          isDragActive && "opacity-100",
        )}
      >
        <div className="rounded-xl border border-primary/30 bg-background/90 px-4 py-3 text-center shadow-lg backdrop-blur">
          <div className="text-sm font-semibold text-foreground">{localize(lang, "Загрузка файлов", "Upload files")}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {localize(
              lang,
              "Перетащите файлы сюда, чтобы отправить их в текущую удалённую папку.",
              "Drop files here to send them to the current remote folder.",
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
