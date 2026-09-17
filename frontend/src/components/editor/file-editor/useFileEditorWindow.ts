import { useCallback, useRef, useState } from "react";

import { DEFAULT_RECT, type WindowMode } from "./types";

export function useFileEditorWindow() {
  const [mode, setMode] = useState<WindowMode>("normal");
  const [rect, setRect] = useState(DEFAULT_RECT);
  const dragRef = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null);
  const resizeRef = useRef<{
    startX: number;
    startY: number;
    origW: number;
    origH: number;
    origX: number;
    origY: number;
  } | null>(null);
  const windowRef = useRef<HTMLDivElement>(null);

  /* ---- drag title bar ---- */
  // Drag/resize read start geometry only from refs so a null ref or a
  // stale setState closure cannot crash the whole Terminal page (white screen).
  const onDragStart = useCallback(
    (e: React.MouseEvent) => {
      if (mode === "maximized") return;
      const target = e.target as HTMLElement | null;
      if (target?.closest("button, input, a, [role='button'], [data-no-drag]")) return;

      e.preventDefault();
      e.stopPropagation();
      dragRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        origX: rect.x,
        origY: rect.y,
      };

      const onMove = (ev: MouseEvent) => {
        const drag = dragRef.current;
        if (!drag) return;
        const dx = ev.clientX - drag.startX;
        const dy = ev.clientY - drag.startY;
        const maxX = Math.max(0, window.innerWidth - 120);
        const maxY = Math.max(0, window.innerHeight - 48);
        try {
          setRect((r) => ({
            ...r,
            x: Math.min(maxX, Math.max(-r.w + 120, drag.origX + dx)),
            y: Math.min(maxY, Math.max(0, drag.origY + dy)),
          }));
        } catch {
          // never let drag update take down the tree
        }
      };
      const onUp = () => {
        dragRef.current = null;
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        window.removeEventListener("blur", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
      window.addEventListener("blur", onUp);
    },
    [mode, rect.x, rect.y],
  );

  /* ---- resize ---- */
  const onResizeStart = useCallback(
    (e: React.MouseEvent) => {
      if (mode === "maximized") return;
      e.preventDefault();
      e.stopPropagation();
      resizeRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        origW: rect.w,
        origH: rect.h,
        origX: rect.x,
        origY: rect.y,
      };

      const onMove = (ev: MouseEvent) => {
        const resize = resizeRef.current;
        if (!resize) return;
        const dx = ev.clientX - resize.startX;
        const dy = ev.clientY - resize.startY;
        try {
          setRect((r) => ({
            ...r,
            w: Math.max(480, resize.origW + dx),
            h: Math.max(300, resize.origH + dy),
          }));
        } catch {
          // never let resize update take down the tree
        }
      };
      const onUp = () => {
        resizeRef.current = null;
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        window.removeEventListener("blur", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
      window.addEventListener("blur", onUp);
    },
    [mode, rect.w, rect.h, rect.x, rect.y],
  );

  const toggleMaximize = useCallback(() => {
    setMode((m) => (m === "maximized" ? "normal" : "maximized"));
  }, []);

  return {
    mode,
    setMode,
    rect,
    windowRef,
    onDragStart,
    onResizeStart,
    toggleMaximize,
  };
}
