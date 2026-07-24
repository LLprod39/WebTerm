import { Loader2, Shield } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { UnsavedChangesDialog } from "@/components/system/ConfirmDialog";

import type { FileEditorController } from "./useFileEditorController";

type DialogsSlice = Pick<
  FileEditorController,
  | "t"
  | "sudoPrompt"
  | "setSudoPrompt"
  | "sudoPassword"
  | "setSudoPassword"
  | "sudoBusy"
  | "submitSudoPrompt"
  | "confirmCloseOpen"
  | "setConfirmCloseOpen"
  | "closeWindow"
>;

export function FileEditorSudoDialog({
  t,
  sudoPrompt,
  setSudoPrompt,
  sudoPassword,
  setSudoPassword,
  sudoBusy,
  submitSudoPrompt,
}: DialogsSlice) {
  return (
    <Dialog
      open={Boolean(sudoPrompt)}
      onOpenChange={(next) => {
        if (!next) {
          setSudoPrompt(null);
          setSudoPassword("");
        }
      }}
    >
      <DialogContent className="z-[90] max-w-md" closeLabel={t("editor.cancel")}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-amber-400" />
            {t("editor.sudoTitle")}
          </DialogTitle>
          <DialogDescription>
            {t("editor.sudoDescription")}
            {sudoPrompt?.path ? (
              <span className="mt-2 block font-mono text-xs text-foreground/80">{sudoPrompt.path}</span>
            ) : null}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <label className="block text-xs font-medium text-muted-foreground" htmlFor="editor-sudo-password">
            {t("editor.sudoPassword")}
          </label>
          <Input
            id="editor-sudo-password"
            type="password"
            autoComplete="current-password"
            value={sudoPassword}
            onChange={(e) => setSudoPassword(e.target.value)}
            placeholder={t("editor.sudoPasswordPlaceholder")}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void submitSudoPrompt();
              }
            }}
            autoFocus
          />
        </DialogBody>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            disabled={sudoBusy}
            onClick={() => {
              setSudoPrompt(null);
              setSudoPassword("");
            }}
          >
            {t("editor.cancel")}
          </Button>
          <Button type="button" disabled={sudoBusy} onClick={() => void submitSudoPrompt()}>
            {sudoBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Shield className="mr-2 h-4 w-4" />}
            {sudoPassword ? t("editor.sudoSubmit") : t("editor.sudoRetryStored")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function FileEditorUnsavedDialog({
  t,
  confirmCloseOpen,
  setConfirmCloseOpen,
  closeWindow,
}: DialogsSlice) {
  return (
    <UnsavedChangesDialog
      open={confirmCloseOpen}
      onOpenChange={setConfirmCloseOpen}
      title={t("editor.unsavedTitle")}
      description={t("editor.unsavedWarn")}
      confirmLabel={t("editor.discardChanges")}
      cancelLabel={t("editor.cancel")}
      onConfirm={() => {
        setConfirmCloseOpen(false);
        closeWindow();
      }}
    />
  );
}
