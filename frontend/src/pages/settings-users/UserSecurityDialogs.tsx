import { useEffect, useMemo, useState } from "react";
import { Copy, Eye, EyeOff, KeyRound, RefreshCw } from "lucide-react";

import type { AccessUser } from "@/lib/api";
import { ACCESS_UI_TEXT, formatAccessText } from "@/lib/accessUiText";
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
import { InlineAlert } from "@/components/system/InlineAlert";

type Lang = "en" | "ru";

function generatePassword() {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%+=?";
  const bytes = new Uint32Array(18);
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => chars[value % chars.length]).join("");
}

export function ResetPasswordDialog({
  lang,
  user,
  open,
  saving,
  onOpenChange,
  onSubmit,
}: {
  lang: Lang;
  user: AccessUser | null;
  open: boolean;
  saving: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (password: string) => void | Promise<void>;
}) {
  const copy = ACCESS_UI_TEXT[lang].users;
  const common = ACCESS_UI_TEXT[lang].common;
  const [mode, setMode] = useState<"generate" | "manual">("generate");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) return;
    setMode("generate");
    setPassword(generatePassword());
    setVisible(false);
    setCopied(false);
  }, [open, user?.id]);

  const checks = useMemo(() => {
    const lower = /[a-z]/.test(password);
    const upper = /[A-Z]/.test(password);
    const digit = /\d/.test(password);
    const symbol = /[^A-Za-z0-9]/.test(password);
    const username = user?.username.toLowerCase() || "";
    return [
      { label: copy.passwordRuleLength, ok: password.length >= 12 },
      { label: copy.passwordRuleComplexity, ok: [lower, upper, digit, symbol].filter(Boolean).length >= 3 },
      { label: copy.passwordRuleUsername, ok: Boolean(password) && (!username || !password.toLowerCase().includes(username)) },
    ];
  }, [copy.passwordRuleComplexity, copy.passwordRuleLength, copy.passwordRuleUsername, password, user?.username]);

  const canSubmit = checks.every((check) => check.ok);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg rounded-xl" closeLabel={common.cancel}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-warning" />
            {copy.resetPasswordTitle}
          </DialogTitle>
          <DialogDescription>
            {formatAccessText(copy.resetPasswordDescription, { name: user?.username || "" })}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="grid grid-cols-2 gap-2 rounded-lg border border-border/70 bg-secondary/20 p-1">
            <Button type="button" variant={mode === "generate" ? "secondary" : "ghost"} onClick={() => {
              setMode("generate");
              setPassword(generatePassword());
            }}>
              {copy.generatePassword}
            </Button>
            <Button type="button" variant={mode === "manual" ? "secondary" : "ghost"} onClick={() => {
              setMode("manual");
              setPassword("");
            }}>
              {copy.manualPassword}
            </Button>
          </div>

          <div className="space-y-2">
            <Label htmlFor="reset-password-value" className="text-sm">
              {copy.newPassword}
            </Label>
            <div className="flex gap-2">
              <Input
                id="reset-password-value"
                type={visible ? "text" : "password"}
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                  setCopied(false);
                }}
                autoComplete="new-password"
                disabled={saving}
              />
              <Button type="button" variant="outline" size="icon" onClick={() => setVisible((value) => !value)} aria-label={visible ? copy.hidePassword : copy.showPassword}>
                {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={() => {
                  if (!password) return;
                  void navigator.clipboard?.writeText(password);
                  setCopied(true);
                }}
                aria-label={copy.copyPassword}
              >
                <Copy className="h-4 w-4" />
              </Button>
              {mode === "generate" ? (
                <Button type="button" variant="outline" size="icon" onClick={() => setPassword(generatePassword())} aria-label={copy.regeneratePassword}>
                  <RefreshCw className="h-4 w-4" />
                </Button>
              ) : null}
            </div>
          </div>

          <div className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-3">
            <div className="text-sm font-semibold text-foreground">{copy.passwordPolicy}</div>
            <div className="mt-2 grid gap-1.5">
              {checks.map((check) => (
                <div key={check.label} className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span className={check.ok ? "text-success" : "text-muted-foreground"}>{check.ok ? "OK" : "-"}</span>
                  <span>{check.label}</span>
                </div>
              ))}
            </div>
          </div>

          {copied ? <InlineAlert tone="success" description={copy.passwordCopied} /> : null}
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            {common.cancel}
          </Button>
          <Button type="button" onClick={() => void onSubmit(password)} disabled={saving || !canSubmit}>
            {saving ? common.saving : copy.resetPasswordAction}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
