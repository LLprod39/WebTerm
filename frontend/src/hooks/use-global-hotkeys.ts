import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

type GlobalHotkeyHandlers = {
  onOpenCommandPalette?: () => void;
  onOpenCheatsheet?: () => void;
  onToggleAssistant?: () => void;
};

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return Boolean(target.closest("[contenteditable='true'], [role='textbox']"));
}

/**
 * Global operator hotkeys:
 * - Ctrl/Cmd+K → command palette
 * - g then d/s/a/c → navigate dashboard/servers/agents/chat
 * - ? → cheatsheet
 * - Ctrl/Cmd+. → assistant drawer
 */
export function useGlobalHotkeys(handlers: GlobalHotkeyHandlers = {}) {
  const navigate = useNavigate();
  const pendingG = useRef(false);
  const gTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    const clearPendingG = () => {
      pendingG.current = false;
      if (gTimer.current) {
        clearTimeout(gTimer.current);
        gTimer.current = null;
      }
    };

    const onKeyDown = (event: KeyboardEvent) => {
      const meta = event.metaKey || event.ctrlKey;
      const key = event.key;

      // Ctrl/Cmd+K — palette (works even in inputs except pure password fields)
      if (meta && (key === "k" || key === "K")) {
        event.preventDefault();
        handlersRef.current.onOpenCommandPalette?.();
        clearPendingG();
        return;
      }

      // Ctrl/Cmd+. — assistant
      if (meta && key === ".") {
        event.preventDefault();
        handlersRef.current.onToggleAssistant?.();
        clearPendingG();
        return;
      }

      if (isEditableTarget(event.target)) {
        clearPendingG();
        return;
      }

      // ? — cheatsheet
      if (key === "?" || (key === "/" && event.shiftKey)) {
        event.preventDefault();
        handlersRef.current.onOpenCheatsheet?.();
        clearPendingG();
        return;
      }

      // Chord: g then letter
      if (pendingG.current) {
        event.preventDefault();
        clearPendingG();
        const map: Record<string, string> = {
          d: "/dashboard",
          s: "/servers",
          a: "/agents",
          c: "/chat",
          m: "/monitoring",
          k: "/kubernetes",
          t: "/studio",
        };
        const path = map[key.toLowerCase()];
        if (path) navigate(path);
        return;
      }

      if (key === "g" || key === "G") {
        if (event.metaKey || event.ctrlKey || event.altKey) return;
        pendingG.current = true;
        gTimer.current = setTimeout(clearPendingG, 900);
        return;
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      clearPendingG();
    };
  }, [navigate]);
}
