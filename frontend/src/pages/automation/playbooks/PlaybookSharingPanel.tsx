import { useState } from "react";
import { Loader2, Share2, Trash2, UserRoundCog, UsersRound } from "lucide-react";

import type {
  PlaybookShare,
  PlaybookShareCapabilities,
  PlaybookSharePrincipalType,
  PlaybookShareRole,
} from "@/api/playbooks";
import { ConfirmDialog } from "@/components/system/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { PlaybookWorkspaceVersioningController } from "./usePlaybookWorkspaceVersioning";

interface PlaybookSharingPanelProps {
  lang: string;
  workspace: PlaybookWorkspaceVersioningController;
}

const ROLE_CAPABILITIES: Record<PlaybookShareRole, PlaybookShareCapabilities> = {
  viewer: { can_view: true, can_edit: false, can_validate: false, can_publish: false, can_run: false, can_export: false, can_manage_shares: false },
  editor: { can_view: true, can_edit: true, can_validate: true, can_publish: false, can_run: false, can_export: true, can_manage_shares: false },
  operator: { can_view: true, can_edit: false, can_validate: true, can_publish: false, can_run: true, can_export: true, can_manage_shares: false },
  manager: { can_view: true, can_edit: true, can_validate: true, can_publish: true, can_run: true, can_export: true, can_manage_shares: true },
};

export function PlaybookSharingPanel({ lang, workspace }: PlaybookSharingPanelProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const [open, setOpen] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<PlaybookShare | null>(null);
  const [principalType, setPrincipalType] = useState<PlaybookSharePrincipalType>("user");
  const [principalId, setPrincipalId] = useState("");
  const [role, setRole] = useState<PlaybookShareRole>("viewer");
  const [capabilities, setCapabilities] = useState<PlaybookShareCapabilities>(ROLE_CAPABILITIES.viewer);
  const [expiresAt, setExpiresAt] = useState("");
  const [formError, setFormError] = useState("");

  if (!workspace.sharesAccessible || !workspace.capabilities.can_share) return null;

  const changeRole = (nextRole: PlaybookShareRole) => {
    setRole(nextRole);
    setCapabilities({ ...ROLE_CAPABILITIES[nextRole] });
  };

  const openForm = () => {
    setPrincipalType("user");
    setPrincipalId("");
    changeRole("viewer");
    setExpiresAt("");
    setFormError("");
    setOpen(true);
  };

  const save = async () => {
    setFormError("");
    const parsedId = Number(principalId);
    if (principalType !== "workspace" && (!Number.isInteger(parsedId) || parsedId <= 0)) {
      setFormError(tr("Укажите корректный ID пользователя или группы.", "Enter a valid user or group ID."));
      return;
    }
    const saved = await workspace.saveShare({
      principal_type: principalType,
      ...(principalType === "workspace" ? {} : { principal_id: parsedId }),
      role,
      capabilities,
      expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
    });
    if (saved) setOpen(false);
  };

  const capabilityLabels: Array<[keyof PlaybookShareCapabilities, string]> = [
    ["can_view", tr("Просмотр", "View")],
    ["can_edit", tr("Редактирование", "Edit")],
    ["can_validate", tr("Проверка", "Validate")],
    ["can_publish", tr("Публикация", "Publish")],
    ["can_run", tr("Запуск", "Run")],
    ["can_export", tr("Экспорт", "Export")],
    ["can_manage_shares", tr("Управление доступом", "Manage access")],
  ];

  return (
    <section className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1" aria-labelledby="sharing-panel-title">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <div className="flex items-center gap-2">
            <Share2 className="h-4 w-4 text-primary" />
            <h3 id="sharing-panel-title" className="text-sm font-semibold text-foreground">
              {tr("Доступ к playbook", "Playbook access")}
            </h3>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {tr("Назначайте роли пользователям, группам или всему workspace.", "Grant roles to users, groups, or the entire workspace.")}
          </p>
        </div>
        <Button size="sm" variant="outline" className="gap-1.5" onClick={openForm}>
          <UserRoundCog className="h-3.5 w-3.5" />
          {tr("Добавить доступ", "Add access")}
        </Button>
      </div>

      <div className="divide-y divide-border">
        {workspace.shares.length ? (
          workspace.shares.map((share) => {
            const revoked = Boolean(share.revoked_at);
            return (
              <div key={share.id} className={`flex flex-wrap items-center gap-3 px-4 py-3 ${revoked ? "opacity-50" : ""}`}>
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-0 text-muted-foreground">
                  <UsersRound className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-foreground">{share.principal.label}</span>
                    <span className="rounded-sm bg-secondary px-1.5 py-0.5 text-2xs text-muted-foreground">{share.role}</span>
                    {revoked ? <span className="text-2xs text-destructive">{tr("Отозван", "Revoked")}</span> : null}
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {share.principal.type}{share.principal.id ? ` #${share.principal.id}` : ""}
                    {share.expires_at ? ` · ${tr("до", "until")} ${new Date(share.expires_at).toLocaleString()}` : ""}
                  </p>
                  <p className="mt-1 text-2xs text-muted-foreground">
                    {Object.entries(share.capabilities).filter(([, value]) => value).map(([key]) => key.replace(/^can_/, "")).join(" · ")}
                  </p>
                </div>
                {!revoked ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 text-destructive hover:text-destructive"
                    aria-label={tr(`Отозвать доступ ${share.principal.label}`, `Revoke access for ${share.principal.label}`)}
                    onClick={() => setRevokeTarget(share)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                ) : null}
              </div>
            );
          })
        ) : (
          <div className="px-4 py-6 text-center text-sm text-muted-foreground">{tr("Явных grants пока нет", "No explicit grants yet")}</div>
        )}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-xl" closeLabel={tr("Закрыть", "Close")}>
          <DialogHeader>
            <DialogTitle>{tr("Добавить или обновить доступ", "Add or update access")}</DialogTitle>
            <DialogDescription>
              {tr("Повторный grant тому же principal обновит его роль.", "Granting the same principal again updates its role.")}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="max-h-[70vh] space-y-4 overflow-auto">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="share-principal-type">{tr("Кому", "Principal")}</Label>
                <Select value={principalType} onValueChange={(value) => setPrincipalType(value as PlaybookSharePrincipalType)}>
                  <SelectTrigger id="share-principal-type" aria-label={tr("Кому предоставить доступ", "Access principal")} className="h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="user">{tr("Пользователь", "User")}</SelectItem>
                    <SelectItem value="group">{tr("Группа", "Group")}</SelectItem>
                    <SelectItem value="workspace">{tr("Вся рабочая область", "Entire workspace")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="share-principal-id">{tr("ID пользователя/группы", "User/group ID")}</Label>
                <Input id="share-principal-id" type="number" min={1} value={principalId} disabled={principalType === "workspace"} onChange={(event) => setPrincipalId(event.target.value)} placeholder={principalType === "workspace" ? "—" : "42"} />
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="share-role">{tr("Роль", "Role")}</Label>
                <Select value={role} onValueChange={(value) => changeRole(value as PlaybookShareRole)}>
                  <SelectTrigger id="share-role" aria-label={tr("Роль доступа", "Access role")} className="h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="viewer">{tr("Наблюдатель", "Viewer")}</SelectItem>
                    <SelectItem value="editor">{tr("Редактор", "Editor")}</SelectItem>
                    <SelectItem value="operator">{tr("Оператор", "Operator")}</SelectItem>
                    <SelectItem value="manager">{tr("Менеджер", "Manager")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="share-expires">{tr("Истекает (необязательно)", "Expires (optional)")}</Label>
                <Input id="share-expires" type="datetime-local" value={expiresAt} onChange={(event) => setExpiresAt(event.target.value)} />
              </div>
            </div>
            <fieldset className="rounded-sm border border-border p-3">
              <legend className="px-1 text-xs font-medium text-foreground">{tr("Capabilities", "Capabilities")}</legend>
              <div className="grid gap-2 sm:grid-cols-2">
                {capabilityLabels.map(([key, label]) => (
                  <label key={key} className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Checkbox
                      checked={capabilities[key]}
                      onCheckedChange={(checked) => setCapabilities((current) => ({ ...current, [key]: checked === true }))}
                    />
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>
            {formError ? <p role="alert" className="text-xs text-destructive">{formError}</p> : null}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>{tr("Отмена", "Cancel")}</Button>
            <Button disabled={workspace.shareBusy} onClick={() => void save()}>
              {workspace.shareBusy ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : null}
              {tr("Сохранить доступ", "Save access")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(revokeTarget)}
        onOpenChange={(next) => !next && setRevokeTarget(null)}
        title={tr("Отозвать доступ?", "Revoke access?")}
        description={revokeTarget ? tr(`Доступ для «${revokeTarget.principal.label}» будет отозван.`, `Access for “${revokeTarget.principal.label}” will be revoked.`) : ""}
        confirmLabel={tr("Отозвать", "Revoke")}
        cancelLabel={tr("Отмена", "Cancel")}
        tone="destructive"
        onConfirm={async () => {
          if (revokeTarget) await workspace.removeShare(revokeTarget.id);
          setRevokeTarget(null);
        }}
      />
    </section>
  );
}
