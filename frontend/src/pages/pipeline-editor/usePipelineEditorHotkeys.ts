import { useEffect } from "react";

export type PipelineEditorHotkeyHandlers = {
  undo: () => void;
  redo: () => void;
  onSave: () => void;
};

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable;
}

/**
 * Editor shortcuts for the studio pipeline canvas.
 *
 * - Ctrl/Cmd+Z → undo
 * - Ctrl/Cmd+Y or Ctrl/Cmd+Shift+Z → redo
 * - Ctrl/Cmd+S → save (`preventDefault`)
 *
 * Skipped when the event target is an input, textarea, or contenteditable.
 *
 * Integrator:
 * ```ts
 * usePipelineEditorHotkeys({
 *   undo: history.undo,
 *   redo: history.redo,
 *   onSave: () => saveMutation.mutate(...),
 * });
 * ```
 */
export function usePipelineEditorHotkeys({
  undo,
  redo,
  onSave,
}: PipelineEditorHotkeyHandlers) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target)) return;

      const meta = event.ctrlKey || event.metaKey;
      if (!meta) return;

      const key = event.key.toLowerCase();

      if (key === "z") {
        event.preventDefault();
        if (event.shiftKey) redo();
        else undo();
        return;
      }

      if (key === "y") {
        event.preventDefault();
        redo();
        return;
      }

      if (key === "s") {
        event.preventDefault();
        onSave();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [undo, redo, onSave]);
}
