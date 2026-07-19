import type { ReactNode } from "react";

import { localize } from "@/lib/i18n";
import { notify } from "@/lib/notify";

type UndoOptions = {
  title: ReactNode;
  description?: ReactNode;
  undoLabel?: string;
  durationMs?: number;
  lang?: "ru" | "en";
  /** Called when the toast expires without undo. */
  onCommit: () => void | Promise<void>;
  /** Called if the user clicks Undo (before commit). */
  onUndo?: () => void | Promise<void>;
};

const pending = new Map<string | number, ReturnType<typeof setTimeout>>();

/**
 * Show a toast with Undo. The destructive work runs only after the timeout
 * (or immediately if duration is 0). Clicking Undo cancels the scheduled commit.
 */
export function notifyWithUndo({
  title,
  description,
  undoLabel,
  durationMs = 5000,
  lang = "ru",
  onCommit,
  onUndo,
}: UndoOptions) {
  const id = `undo-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  let committed = false;
  let undone = false;

  const commit = async () => {
    if (committed || undone) return;
    committed = true;
    pending.delete(id);
    await onCommit();
  };

  const timer = setTimeout(() => {
    void commit();
  }, durationMs);
  pending.set(id, timer);

  const label = undoLabel ?? localize(lang, "Отменить", "Undo");

  const toastId = notify.show({
    title,
    description,
    duration: durationMs,
    action: {
      label,
      onClick: () => {
        if (committed || undone) return;
        undone = true;
        const t = pending.get(id);
        if (t) clearTimeout(t);
        pending.delete(id);
        notify.dismiss(toastId);
        void onUndo?.();
      },
    },
  });

  return {
    id,
    cancel: () => {
      if (committed || undone) return;
      undone = true;
      const t = pending.get(id);
      if (t) clearTimeout(t);
      pending.delete(id);
      notify.dismiss(toastId);
    },
  };
}
