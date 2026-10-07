import { useEffect, useRef } from "react";

export type PipelineEditorHotkeyHandlers = {
  undo: () => void;
  redo: () => void;
  onSave: () => void;
};

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || Boolean(target.isContentEditable);
}

/**
 * Editor shortcuts for the studio pipeline canvas.
 *
 * - Ctrl/Cmd+Z → undo
 * - Ctrl/Cmd+Y or Ctrl/Cmd+Shift+Z → redo
 * - Ctrl/Cmd+S → save (`preventDefault`)
 *
 * Skipped when the event target is an input, textarea, or contenteditable.
 * Handlers are read from refs so the window listener is not reattached every render.
 */
export function usePipelineEditorHotkeys({
  undo,
  redo,
  onSave,
}: PipelineEditorHotkeyHandlers) {
  const handlersRef = useRef({ undo, redo, onSave });
  handlersRef.current = { undo, redo, onSave };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target)) return;

      const meta = event.ctrlKey || event.metaKey;
      if (!meta) return;

      const key = event.key.toLowerCase();
      const { undo: doUndo, redo: doRedo, onSave: doSave } = handlersRef.current;

      if (key === "z") {
        event.preventDefault();
        if (event.shiftKey) doRedo();
        else doUndo();
        return;
      }

      if (key === "y") {
        event.preventDefault();
        doRedo();
        return;
      }

      if (key === "s") {
        event.preventDefault();
        doSave();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
