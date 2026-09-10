import { useEffect, useRef } from "react";
import { useBeforeUnload, useBlocker } from "react-router-dom";

const dirtyEditors = new Set<symbol>();
const message =
  "Есть несохранённые изменения. Перейти и отменить эти изменения?";
export function confirmDiscardEdits() {
  return dirtyEditors.size === 0 || window.confirm(message);
}
export function useUnsavedEditsBlocker(dirty: boolean) {
  const id = useRef(Symbol("editor"));
  useEffect(() => {
    const key = id.current;
    if (dirty) dirtyEditors.add(key);
    else dirtyEditors.delete(key);
    return () => {
      dirtyEditors.delete(key);
    };
  }, [dirty]);
  useBeforeUnload((event) => {
    if (dirty) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  return useBlocker(dirty);
}
export function useUnsavedEdits(dirty: boolean) {
  const blocker = useUnsavedEditsBlocker(dirty);
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm(message)) blocker.proceed();
    else blocker.reset();
  }, [blocker]);
}
