import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";

import type { PlaybooksView, PlaybooksWorkspaceProps } from "./types";

interface NavigationArgs {
  initialView: PlaybooksWorkspaceProps["initialView"];
  onViewChange: PlaybooksWorkspaceProps["onViewChange"];
  editorDirty: boolean;
  setSaveError: Dispatch<SetStateAction<string | null>>;
  tr: (ru: string, en: string) => string;
}

export function usePlaybooksWorkspaceNavigation({
  initialView,
  onViewChange,
  editorDirty,
  setSaveError,
  tr,
}: NavigationArgs) {
  const pendingRouteViewRef = useRef<string | null>(null);
  const [view, setViewState] = useState<PlaybooksView>(() => initialView || { mode: "catalog" });

  const setView = useCallback((next: PlaybooksView) => {
    setViewState(next);
    if (onViewChange) pendingRouteViewRef.current = JSON.stringify(next);
    onViewChange?.(next);
  }, [onViewChange]);

  useEffect(() => {
    if (!initialView) return;
    const nextKey = JSON.stringify(initialView);
    if (pendingRouteViewRef.current) {
      if (pendingRouteViewRef.current === nextKey) {
        pendingRouteViewRef.current = null;
        setViewState((current) => (JSON.stringify(current) === nextKey ? current : initialView));
      }
      return;
    }
    if (JSON.stringify(view) === nextKey) return;
    if (
      view.mode === "edit" &&
      editorDirty &&
      !window.confirm(
        tr(
          "Есть несохранённые изменения. Выйти без сохранения?",
          "You have unsaved changes. Leave without saving?",
        ),
      )
    ) {
      if (onViewChange) {
        pendingRouteViewRef.current = JSON.stringify(view);
        onViewChange(view, { replace: true });
      }
      return;
    }
    setSaveError(null);
    setViewState(initialView);
  }, [editorDirty, initialView, onViewChange, setSaveError, tr, view]);

  useEffect(() => {
    if (view.mode !== "edit" || !editorDirty) return;
    const guardUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", guardUnload);
    return () => window.removeEventListener("beforeunload", guardUnload);
  }, [editorDirty, view.mode]);

  return { view, setView };
}
