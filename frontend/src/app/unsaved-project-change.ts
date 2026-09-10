import { useEffect } from "react";

const beforeProjectChange = "webterm:before-project-change";
const pendingProjectChange = "webterm:pending-project-change";

export function useUnsavedProjectChange(isDirty: boolean, pending = false) {
  useEffect(() => {
    if (!isDirty) return;
    const protectDraft = (event: Event) => event.preventDefault();
    window.addEventListener(beforeProjectChange, protectDraft);
    return () => window.removeEventListener(beforeProjectChange, protectDraft);
  }, [isDirty]);
  useEffect(() => {
    if (!pending) return;
    const protectSave = (event: Event) => event.preventDefault();
    window.addEventListener(pendingProjectChange, protectSave);
    return () => window.removeEventListener(pendingProjectChange, protectSave);
  }, [pending]);
}

export function hasUnsavedProjectChanges() {
  return !window.dispatchEvent(
    new Event(beforeProjectChange, { cancelable: true }),
  );
}

export function hasPendingProjectChanges() {
  return !window.dispatchEvent(
    new Event(pendingProjectChange, { cancelable: true }),
  );
}
