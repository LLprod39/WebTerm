import type { ChangeEvent, Dispatch, SetStateAction } from "react";
import { ShieldCheck, Upload } from "lucide-react";

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
import { Textarea } from "@/components/ui/textarea";
import type { FrontendGroup, FrontendServer } from "@/lib/api";

import type { ServerForm } from "./types";

interface ServerFormDialogProps {
  editingServer: FrontendServer | null;
  form: ServerForm;
  handlePrivateKeyFile: (event: ChangeEvent<HTMLInputElement>) => void;
  manageableGroups: FrontendGroup[];
  onSave: () => void;
  open: boolean;
  saving: boolean;
  setDialogOpen: (open: boolean) => void;
  setForm: Dispatch<SetStateAction<ServerForm>>;
  sudoPasswordRequired: boolean;
  t: (key: string) => string;
}

export function ServerFormDialog({
  editingServer,
  form,
  handlePrivateKeyFile,
  manageableGroups,
  onSave,
  open,
  saving,
  setDialogOpen,
  setForm,
  sudoPasswordRequired,
  t,
}: ServerFormDialogProps) {
  return (
    <Dialog open={open} onOpenChange={setDialogOpen}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] max-w-2xl flex-col sm:max-h-[90vh]">
        <DialogHeader>
          <DialogTitle>{editingServer ? t("srv.edit_server") : t("srv.create_server")}</DialogTitle>
          <DialogDescription>{t("srv.server_settings")}</DialogDescription>
        </DialogHeader>

        <DialogBody className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 pb-6 sm:px-6">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-1.5 md:col-span-2">
              <Label className="text-xs text-muted-foreground">{t("srv.name")} *</Label>
              <Input
                placeholder="e.g. prod-web-01"
                value={form.name}
                onChange={(event) => setForm((state) => ({ ...state, name: event.target.value }))}
                className="bg-secondary/50"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.host")} *</Label>
              <Input
                placeholder="192.168.1.10"
                value={form.host}
                onChange={(event) => setForm((state) => ({ ...state, host: event.target.value }))}
                className="bg-secondary/50"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.port")}</Label>
              <Input
                type="number"
                value={form.port}
                onChange={(event) => setForm((state) => ({ ...state, port: Number(event.target.value) || 22 }))}
                className="bg-secondary/50"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.username")} *</Label>
              <Input
                placeholder="ubuntu"
                value={form.username}
                onChange={(event) => setForm((state) => ({ ...state, username: event.target.value }))}
                className="bg-secondary/50"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.server_type")}</Label>
              <select
                value={form.server_type}
                onChange={() => setForm((state) => ({ ...state, server_type: "ssh" }))}
                className="flex h-10 w-full rounded-md border border-input bg-secondary/50 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="ssh">SSH</option>
              </select>
            </div>
          </div>

          <div className="space-y-4 border-t border-border pt-4">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.auth_method")}</Label>
              <div className="flex gap-2">
                {(["password", "key", "key_password"] as const).map((method) => (
                  <button
                    key={method}
                    type="button"
                    onClick={() => setForm((state) => ({ ...state, auth_method: method }))}
                    className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                      form.auth_method === method
                        ? "border-primary bg-primary/15 text-primary"
                        : "border-border bg-secondary/50 text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {method === "password" ? t("srv.auth_password") : method === "key" ? t("srv.auth_key") : t("srv.auth_key_password")}
                  </button>
                ))}
              </div>
            </div>

            {form.auth_method !== "password" ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <Label className="text-xs text-muted-foreground">{t("srv.private_key")}</Label>
                  <label className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border border-border bg-secondary/50 px-2.5 text-xs font-medium text-foreground transition-colors hover:bg-secondary">
                    <Upload className="h-3.5 w-3.5" />
                    {t("srv.private_key_upload")}
                    <input
                      type="file"
                      accept=".key,.pem,.ppk,.txt,text/plain,application/x-pem-file"
                      className="sr-only"
                      onChange={handlePrivateKeyFile}
                    />
                  </label>
                </div>
                <Textarea
                  value={form.ssh_private_key}
                  onChange={(event) => setForm((state) => ({ ...state, ssh_private_key: event.target.value }))}
                  placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
                  className="min-h-28 bg-secondary/50 font-mono text-xs"
                  spellCheck={false}
                />
                <p className="text-xs text-muted-foreground">
                  {form.key_path && !form.ssh_private_key.trim()
                    ? t("srv.private_key_saved_hint")
                    : t("srv.private_key_hint")}
                </p>
              </div>
            ) : null}
            {form.auth_method !== "key" ? (
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{t("srv.password")}</Label>
                <Input
                  type="password"
                  placeholder={editingServer ? t("srv.keep_password_placeholder") : ""}
                  value={form.password}
                  onChange={(event) => setForm((state) => ({ ...state, password: event.target.value }))}
                  className="bg-secondary/50"
                />
              </div>
            ) : null}
          </div>

          <div className="space-y-4 border-t border-border pt-4">
            <div className="flex items-start gap-2">
              <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-secondary text-muted-foreground">
                <ShieldCheck className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <Label className="text-xs text-muted-foreground">{t("srv.sudo_auth")}</Label>
                <p className="mt-1 text-xs text-muted-foreground">{t("srv.sudo_auth_hint")}</p>
              </div>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {(["none", "nopasswd", "stored_password"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setForm((state) => ({ ...state, sudo_auth_mode: mode }))}
                  className={`min-h-10 rounded-md border px-3 py-2 text-left text-xs font-medium transition-colors ${
                    form.sudo_auth_mode === mode
                      ? "border-primary bg-primary/15 text-primary"
                      : "border-border bg-secondary/50 text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {mode === "none" ? t("srv.sudo_none") : mode === "nopasswd" ? t("srv.sudo_nopasswd") : t("srv.sudo_stored")}
                </button>
              ))}
            </div>
            {form.sudo_auth_mode === "stored_password" ? (
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{t("srv.sudo_password")}</Label>
                <Input
                  type="password"
                  placeholder={editingServer?.has_saved_sudo_password ? t("srv.keep_sudo_password_placeholder") : ""}
                  value={form.sudo_password}
                  onChange={(event) => setForm((state) => ({ ...state, sudo_password: event.target.value }))}
                  className="bg-secondary/50"
                />
                <p className="text-xs text-muted-foreground">{t("srv.sudo_password_hint")}</p>
              </div>
            ) : null}
          </div>

          <div className="grid grid-cols-1 gap-4 border-t border-border pt-4 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.groups")}</Label>
              <select
                value={form.group_id ?? ""}
                onChange={(event) => setForm((state) => ({ ...state, group_id: event.target.value ? Number(event.target.value) : null }))}
                className="flex h-10 w-full rounded-md border border-input bg-secondary/50 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">{t("srv.no_group")}</option>
                {manageableGroups.map((group) => (
                  <option key={group.id ?? group.name} value={group.id ?? ""}>
                    {group.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">{t("srv.tags")}</Label>
              <Input
                placeholder="web, production"
                value={form.tags}
                onChange={(event) => setForm((state) => ({ ...state, tags: event.target.value }))}
                className="bg-secondary/50"
              />
            </div>
            <div className="space-y-1.5 md:col-span-2">
              <Label className="text-xs text-muted-foreground">{t("srv.notes")}</Label>
              <Input
                placeholder="..."
                value={form.notes}
                onChange={(event) => setForm((state) => ({ ...state, notes: event.target.value }))}
                className="bg-secondary/50"
              />
            </div>
          </div>
        </DialogBody>

        <DialogFooter className="shrink-0 px-4 sm:px-6">
          <Button variant="outline" size="sm" onClick={() => setDialogOpen(false)}>
            {t("srv.cancel")}
          </Button>
          <Button
            size="sm"
            onClick={onSave}
            disabled={
              saving ||
              !form.name ||
              !form.host ||
              !form.username ||
              (form.auth_method !== "password" && !form.key_path && !form.ssh_private_key.trim()) ||
              sudoPasswordRequired
            }
          >
            {saving ? t("srv.saving") : editingServer ? t("srv.update") : t("srv.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
