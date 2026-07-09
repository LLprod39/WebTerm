import type { ChangeEvent, Dispatch, ReactNode, SetStateAction } from "react";
import { KeyRound, Network, ShieldCheck, Server, Upload } from "lucide-react";

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { FrontendGroup, FrontendServer } from "@/lib/api";

import type { ServerForm } from "./types";
import type { ServerValidationResult } from "./serverValidation";

interface ServerFormDialogProps {
  editingServer: FrontendServer | null;
  form: ServerForm;
  formValidation: ServerValidationResult;
  handlePrivateKeyFile: (event: ChangeEvent<HTMLInputElement>) => void;
  manageableGroups: FrontendGroup[];
  onSave: () => void;
  onSaveAndTest: () => void | Promise<void>;
  onTestConnection: (server: FrontendServer) => void | Promise<void>;
  open: boolean;
  saving: boolean;
  setDialogOpen: (open: boolean) => void;
  setForm: Dispatch<SetStateAction<ServerForm>>;
  t: (key: string) => string;
  testingConnection: boolean;
}

function DialogSection({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("border-t border-border/50 py-5 first:border-t-0 first:pt-0 last:pb-0", className)}>
      <div className="mb-4 min-w-0">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        {description ? <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}

function FieldLabel({
  children,
  required = false,
  htmlFor,
}: {
  children: ReactNode;
  required?: boolean;
  htmlFor?: string;
}) {
  return (
    <Label htmlFor={htmlFor} className="text-[13px] font-medium leading-[18px] text-muted-foreground">
      {children}
      {required ? <span className="ml-1 text-warning">*</span> : null}
    </Label>
  );
}

function ChoiceButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "min-h-10 rounded-lg border px-3 py-2 text-left text-sm font-medium leading-5 transition-colors",
        active
          ? "border-primary bg-primary/12 text-primary"
          : "border-border/60 text-muted-foreground hover:border-border-strong hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

export function ServerFormDialog({
  editingServer,
  form,
  formValidation,
  handlePrivateKeyFile,
  manageableGroups,
  onSave,
  onSaveAndTest,
  onTestConnection,
  open,
  saving,
  setDialogOpen,
  setForm,
  t,
  testingConnection,
}: ServerFormDialogProps) {
  const disabledReason = formValidation.summary;
  const groupsWithId = manageableGroups.filter((group): group is FrontendGroup & { id: number } => group.id !== null);
  const showFieldErrors = Boolean(form.name || form.host || form.username || form.ssh_private_key || form.sudo_password);

  return (
    <Dialog open={open} onOpenChange={setDialogOpen}>
      <DialogContent className="flex max-h-[calc(100dvh-1rem)] max-w-[680px] flex-col rounded-xl sm:max-h-[92vh]">
        <DialogHeader>
          <DialogTitle>{editingServer ? t("srv.edit_server") : t("srv.create_server")}</DialogTitle>
          <DialogDescription>{t("srv.server_settings")}</DialogDescription>
        </DialogHeader>

        <DialogBody className="min-h-0 flex-1 overflow-y-auto px-4 py-0 sm:px-6">
          <DialogSection
            title={t("srv.connection_section")}
            description={t("srv.connection_section_desc")}
            icon={<Server className="h-4 w-4" />}
          >
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="space-y-2 md:col-span-2">
                <FieldLabel htmlFor="server-name" required>{t("srv.name")}</FieldLabel>
                <Input
                  id="server-name"
                  placeholder={t("srv.name_placeholder")}
                  value={form.name}
                  onChange={(event) => setForm((state) => ({ ...state, name: event.target.value }))}
                  aria-invalid={Boolean(showFieldErrors && formValidation.errors.name)}
                  aria-describedby={showFieldErrors && formValidation.errors.name ? "server-name-error" : undefined}
                />
                {showFieldErrors && formValidation.errors.name ? (
                  <p id="server-name-error" className="text-xs text-destructive">{formValidation.errors.name}</p>
                ) : null}
              </div>
              <div className="space-y-2">
                <FieldLabel htmlFor="server-host" required>{t("srv.host")}</FieldLabel>
                <Input
                  id="server-host"
                  placeholder={t("srv.host_placeholder")}
                  value={form.host}
                  onChange={(event) => setForm((state) => ({ ...state, host: event.target.value }))}
                  aria-invalid={Boolean(showFieldErrors && formValidation.errors.host)}
                  aria-describedby={showFieldErrors && formValidation.errors.host ? "server-host-error" : undefined}
                />
                {showFieldErrors && formValidation.errors.host ? (
                  <p id="server-host-error" className="text-xs text-destructive">{formValidation.errors.host}</p>
                ) : null}
              </div>
              <div className="space-y-2">
                <FieldLabel htmlFor="server-port">{t("srv.port")}</FieldLabel>
                <Input
                  id="server-port"
                  type="number"
                  min={1}
                  max={65535}
                  value={form.port}
                  onChange={(event) => setForm((state) => ({ ...state, port: Number(event.target.value) || 22 }))}
                  aria-invalid={Boolean(formValidation.errors.port)}
                  aria-describedby={formValidation.errors.port ? "server-port-error" : undefined}
                />
                {formValidation.errors.port ? (
                  <p id="server-port-error" className="text-xs text-destructive">{formValidation.errors.port}</p>
                ) : null}
              </div>
              <div className="space-y-2">
                <FieldLabel htmlFor="server-username" required>{t("srv.username")}</FieldLabel>
                <Input
                  id="server-username"
                  placeholder={t("srv.username_placeholder")}
                  value={form.username}
                  onChange={(event) => setForm((state) => ({ ...state, username: event.target.value }))}
                  aria-invalid={Boolean(showFieldErrors && formValidation.errors.username)}
                  aria-describedby={showFieldErrors && formValidation.errors.username ? "server-username-error" : undefined}
                />
                {showFieldErrors && formValidation.errors.username ? (
                  <p id="server-username-error" className="text-xs text-destructive">{formValidation.errors.username}</p>
                ) : null}
              </div>
              <div className="space-y-2">
                <FieldLabel>{t("srv.server_type")}</FieldLabel>
                <Select value={form.server_type} disabled>
                  <SelectTrigger aria-label={t("srv.server_type")} className="h-10 bg-secondary/45">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ssh">{t("srv.server_type_ssh")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </DialogSection>

          <DialogSection
            title={t("srv.auth_section")}
            description={t("srv.auth_section_desc")}
            icon={<KeyRound className="h-4 w-4" />}
          >
            <div className="space-y-4">
              <div className="space-y-2">
                <FieldLabel>{t("srv.auth_method")}</FieldLabel>
                <div className="grid gap-2 sm:grid-cols-3">
                  {(["password", "key", "key_password"] as const).map((method) => (
                    <ChoiceButton
                      key={method}
                      active={form.auth_method === method}
                      onClick={() => setForm((state) => ({ ...state, auth_method: method }))}
                    >
                      {method === "password"
                        ? t("srv.auth_password")
                        : method === "key"
                          ? t("srv.auth_key")
                          : t("srv.auth_key_password")}
                    </ChoiceButton>
                  ))}
                </div>
              </div>

              {form.auth_method !== "password" ? (
                <div className="space-y-2">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <FieldLabel required>{t("srv.private_key")}</FieldLabel>
                    <label className="inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-lg border border-border/80 bg-secondary/55 px-3 text-sm font-medium text-foreground transition-colors hover:border-border-strong hover:bg-secondary">
                      <Upload className="h-4 w-4" />
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
                    className="min-h-32 bg-card/70 font-mono text-xs leading-5"
                    spellCheck={false}
                    aria-invalid={Boolean(showFieldErrors && formValidation.errors.ssh_private_key)}
                    aria-describedby={showFieldErrors && formValidation.errors.ssh_private_key ? "server-private-key-error" : undefined}
                  />
                  {showFieldErrors && formValidation.errors.ssh_private_key ? (
                    <p id="server-private-key-error" className="text-xs text-destructive">{formValidation.errors.ssh_private_key}</p>
                  ) : null}
                  <p className="text-xs leading-5 text-muted-foreground">
                    {form.key_path && !form.ssh_private_key.trim()
                      ? t("srv.private_key_saved_hint")
                      : t("srv.private_key_hint")}
                  </p>
                </div>
              ) : null}
              {form.auth_method !== "key" ? (
                <div className="space-y-2">
                  <FieldLabel htmlFor="server-password">{t("srv.password")}</FieldLabel>
                  <Input
                    id="server-password"
                    type="password"
                    placeholder={editingServer ? t("srv.keep_password_placeholder") : ""}
                    value={form.password}
                    onChange={(event) => setForm((state) => ({ ...state, password: event.target.value }))}
                  />
                </div>
              ) : null}
            </div>
          </DialogSection>

          <DialogSection
            title={t("srv.access_section")}
            description={t("srv.access_section_desc")}
            icon={<ShieldCheck className="h-4 w-4" />}
          >
            <div className="space-y-4">
              <div className="space-y-2">
                <FieldLabel>{t("srv.sudo_auth")}</FieldLabel>
                <p className="text-sm leading-5 text-muted-foreground">{t("srv.sudo_auth_hint")}</p>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                  {(["none", "nopasswd", "stored_password"] as const).map((mode) => (
                    <ChoiceButton
                      key={mode}
                      active={form.sudo_auth_mode === mode}
                      onClick={() => setForm((state) => ({ ...state, sudo_auth_mode: mode }))}
                    >
                      {mode === "none"
                        ? t("srv.sudo_none")
                        : mode === "nopasswd"
                          ? t("srv.sudo_nopasswd")
                          : t("srv.sudo_stored")}
                    </ChoiceButton>
                  ))}
                </div>
              </div>
              {form.sudo_auth_mode === "stored_password" ? (
                <div className="space-y-2">
                  <FieldLabel htmlFor="server-sudo-password" required>{t("srv.sudo_password")}</FieldLabel>
                  <Input
                    id="server-sudo-password"
                    type="password"
                    placeholder={editingServer?.has_saved_sudo_password ? t("srv.keep_sudo_password_placeholder") : ""}
                    value={form.sudo_password}
                    onChange={(event) => setForm((state) => ({ ...state, sudo_password: event.target.value }))}
                    aria-invalid={Boolean(showFieldErrors && formValidation.errors.sudo_password)}
                    aria-describedby={showFieldErrors && formValidation.errors.sudo_password ? "server-sudo-password-error" : undefined}
                  />
                  {showFieldErrors && formValidation.errors.sudo_password ? (
                    <p id="server-sudo-password-error" className="text-xs text-destructive">{formValidation.errors.sudo_password}</p>
                  ) : null}
                  <p className="text-xs leading-5 text-muted-foreground">{t("srv.sudo_password_hint")}</p>
                </div>
              ) : null}
            </div>
          </DialogSection>

          <DialogSection
            title={t("srv.organization_section")}
            description={t("srv.organization_section_desc")}
            icon={<Network className="h-4 w-4" />}
          >
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <FieldLabel>{t("srv.groups")}</FieldLabel>
                <Select
                  value={form.group_id === null ? "__none__" : String(form.group_id)}
                  onValueChange={(value) =>
                    setForm((state) => ({ ...state, group_id: value === "__none__" ? null : Number(value) }))
                  }
                >
                  <SelectTrigger aria-label={t("srv.groups")} className="h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">{t("srv.no_group")}</SelectItem>
                    {groupsWithId.map((group) => (
                      <SelectItem key={group.id} value={String(group.id)}>
                        {group.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <FieldLabel htmlFor="server-tags">{t("srv.tags")}</FieldLabel>
                <Input
                  id="server-tags"
                  placeholder={t("srv.tags_placeholder")}
                  value={form.tags}
                  onChange={(event) => setForm((state) => ({ ...state, tags: event.target.value }))}
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <FieldLabel htmlFor="server-notes">{t("srv.notes")}</FieldLabel>
                <Input
                  id="server-notes"
                  placeholder={t("srv.notes_placeholder")}
                  value={form.notes}
                  onChange={(event) => setForm((state) => ({ ...state, notes: event.target.value }))}
                />
              </div>
            </div>
          </DialogSection>

        </DialogBody>

        <DialogFooter className="shrink-0 items-center gap-3 px-4 sm:px-6">
          <Button variant="ghost" onClick={() => setDialogOpen(false)}>
            {t("srv.cancel")}
          </Button>
          {disabledReason ? (
            <p className="min-w-0 flex-1 text-xs leading-5 text-warning sm:px-2">{disabledReason}</p>
          ) : (
            <div className="hidden flex-1 sm:block" />
          )}
          {editingServer ? (
            <AsyncButton
              variant="secondary"
              loading={testingConnection}
              loadingLabel={t("srv.testing_connection")}
              onClick={() => void onTestConnection(editingServer)}
              disabled={saving}
            >
              {t("srv.test_connection")}
            </AsyncButton>
          ) : null}
          <AsyncButton
            variant="secondary"
            onClick={onSaveAndTest}
            loading={saving || testingConnection}
            loadingLabel={testingConnection ? t("srv.testing_connection") : t("srv.saving")}
            disabled={Boolean(disabledReason)}
            title={disabledReason || undefined}
          >
            {t("srv.save_and_test")}
          </AsyncButton>
          <AsyncButton
            onClick={onSave}
            loading={saving}
            loadingLabel={t("srv.saving")}
            disabled={Boolean(disabledReason)}
            title={disabledReason || undefined}
          >
            {editingServer ? t("srv.update") : t("srv.create")}
          </AsyncButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
