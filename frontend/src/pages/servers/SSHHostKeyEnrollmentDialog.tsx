import { useEffect, useState } from "react";
import { ShieldCheck, TriangleAlert } from "lucide-react";

import { AsyncButton } from "@/components/system/AsyncButton";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import type { SSHHostKeyEnrollmentTarget } from "./types";

export function SSHHostKeyEnrollmentDialog({
  busy,
  onClose,
  onConfirm,
  open,
  t,
  target,
}: {
  busy: boolean;
  onClose: () => void;
  onConfirm: (fingerprint: string) => void | Promise<void>;
  open: boolean;
  t: (key: string) => string;
  target: SSHHostKeyEnrollmentTarget | null;
}) {
  const [confirmation, setConfirmation] = useState("");

  useEffect(() => {
    setConfirmation("");
  }, [target?.fingerprintSha256]);

  const fingerprint = target?.fingerprintSha256 || "";
  const matches = Boolean(fingerprint) && confirmation.trim() === fingerprint;

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !busy) onClose();
      }}
    >
      <DialogContent className="max-w-xl" closeLabel={t("srv.cancel")}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {target?.isRotation ? (
              <TriangleAlert className="h-4 w-4 text-warning" aria-hidden />
            ) : (
              <ShieldCheck className="h-4 w-4 text-primary" aria-hidden />
            )}
            {target?.isRotation ? t("srv.host_key_rotation_title") : t("srv.host_key_enrollment_title")}
          </DialogTitle>
          <DialogDescription>
            {target?.isRotation
              ? t("srv.host_key_rotation_description")
              : t("srv.host_key_enrollment_description")}
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <div className="rounded-lg border border-border bg-surface-1 p-4">
            <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
              <span>{target?.serverName}</span>
              <span>{target?.algorithm || "SSH"}</span>
            </div>
            <code className="mt-3 block break-all rounded-md bg-background px-3 py-2 font-mono text-sm text-foreground">
              {fingerprint}
            </code>
          </div>

          {target?.isRotation && target.trustedFingerprints.length > 0 ? (
            <div className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-xs leading-5 text-foreground">
              <p className="font-semibold">{t("srv.host_key_previous")}</p>
              {target.trustedFingerprints.map((item) => (
                <code key={item} className="mt-1 block break-all font-mono text-muted-foreground">
                  {item}
                </code>
              ))}
            </div>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="ssh-host-key-confirmation">{t("srv.host_key_confirmation_label")}</Label>
            <Input
              id="ssh-host-key-confirmation"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              placeholder="SHA256:..."
              autoComplete="off"
              spellCheck={false}
              className="font-mono text-sm"
            />
            <p className="text-xs leading-5 text-muted-foreground">{t("srv.host_key_confirmation_hint")}</p>
          </div>
        </DialogBody>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {t("srv.cancel")}
          </Button>
          <AsyncButton
            onClick={() => void onConfirm(confirmation.trim())}
            disabled={!matches}
            loading={busy}
            loadingLabel={t("srv.testing_connection")}
          >
            {target?.isRotation ? t("srv.host_key_replace_and_test") : t("srv.host_key_trust_and_test")}
          </AsyncButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
