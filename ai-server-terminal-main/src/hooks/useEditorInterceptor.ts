/**
 * Hook managing the GUI file editor modal state.
 *
 * Provides `handleWsEvent` to react to `editor_intercept` events
 * from the SSH consumer, and `openEditor` for the toolbar button.
 */

import { useCallback, useState } from "react";

export interface EditorInterceptorState {
  isOpen: boolean;
  serverId: number | null;
  filePath: string | null;
}

export function useEditorInterceptor() {
  const [state, setState] = useState<EditorInterceptorState>({
    isOpen: false,
    serverId: null,
    filePath: null,
  });

  /** Open the editor for a given server + file path (toolbar button). */
  const openEditor = useCallback((serverId: number, filePath?: string) => {
    setState({
      isOpen: true,
      serverId,
      filePath: filePath ?? null,
    });
  }, []);

  /** Open editor for a remote absolute path (terminal file link click). */
  const openFileAtPath = useCallback((serverId: number, filePath: string) => {
    const path = String(filePath || "").trim();
    if (!path) return;
    setState({ isOpen: true, serverId, filePath: path });
  }, []);

  /** Close the editor modal. */
  const closeEditor = useCallback(() => {
    setState({ isOpen: false, serverId: null, filePath: null });
  }, []);

  /**
   * Handle a WS event payload — returns true if it was consumed
   * (editor_intercept), false otherwise.
   */
  const handleWsEvent = useCallback(
    (serverId: number, payload: Record<string, unknown>): boolean => {
      if (String(payload.type || "") !== "editor_intercept") return false;
      const path = String(payload.path || "");
      if (!path) return false;
      setState({ isOpen: true, serverId, filePath: path });
      return true;
    },
    [],
  );

  return { editorState: state, openEditor, openFileAtPath, closeEditor, handleWsEvent } as const;
}
