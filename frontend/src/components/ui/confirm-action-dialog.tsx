import { ConfirmDialog } from "@/components/system/ConfirmDialog";

/**
 * Thin adapter kept for backwards compatibility. The single source of truth for
 * confirm/destructive dialogs is `ConfirmDialog` in `@/components/system/ConfirmDialog`.
 * Prefer importing `ConfirmDialog` / `DeleteDialog` directly in new code.
 */
export function ConfirmActionDialog({
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = true,
  ...rest
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void | Promise<void>;
  destructive?: boolean;
  contentClassName?: string;
}) {
  return (
    <ConfirmDialog
      {...rest}
      confirmLabel={confirmLabel}
      cancelLabel={cancelLabel}
      tone={destructive ? "destructive" : "default"}
    />
  );
}
