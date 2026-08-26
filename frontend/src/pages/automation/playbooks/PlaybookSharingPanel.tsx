import { useDeferredValue, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, Copy, Loader2, Search, Share2, Trash2, UserRound, UserRoundCog, UsersRound } from "lucide-react";

import {
  searchPlaybookShareCandidates,
  type PlaybookShare,
  type PlaybookShareCapabilities,
  type PlaybookShareRole,
} from "@/api/playbooks";
import { ConfirmDialog } from "@/components/system/ConfirmDialog";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { notify } from "@/lib/notify";
import type { PlaybookWorkspaceVersioningController } from "./usePlaybookWorkspaceVersioning";

interface PlaybookSharingPanelProps {
  lang: string;
  playbookId: number;
  workspace: PlaybookWorkspaceVersioningController;
}

const ROLE_CAPABILITIES: Record<PlaybookShareRole, PlaybookShareCapabilities> = {
  viewer: { can_view: true, can_edit: false, can_validate: false, can_publish: false, can_run: false, can_export: false, can_manage_shares: false },
  editor: { can_view: true, can_edit: true, can_validate: true, can_publish: false, can_run: true, can_export: true, can_manage_shares: false },
  operator: { can_view: true, can_edit: false, can_validate: true, can_publish: false, can_run: true, can_export: true, can_manage_shares: false },
  manager: { can_view: true, can_edit: true, can_validate: true, can_publish: true, can_run: true, can_export: true, can_manage_shares: true },
};

type AssignableRole = Extract<PlaybookShareRole, "operator" | "editor">;

export function PlaybookSharingPanel({ lang, playbookId, workspace }: PlaybookSharingPanelProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const [open, setOpen] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<PlaybookShare | null>(null);
  const [principalId, setPrincipalId] = useState<number | null>(null);
  const [recipientQuery, setRecipientQuery] = useState("");
  const deferredRecipientQuery = useDeferredValue(recipientQuery);
  const [linkCopied, setLinkCopied] = useState(false);
  const [role, setRole] = useState<AssignableRole>("operator");
  const [expiresAt, setExpiresAt] = useState("");
  const [formError, setFormError] = useState("");
  const candidatesQuery = useQuery({
    queryKey: ["playbook-share-candidates", playbookId, deferredRecipientQuery],
    queryFn: () => searchPlaybookShareCandidates(playbookId, deferredRecipientQuery),
    enabled: open && deferredRecipientQuery.trim().length > 0,
    staleTime: 30_000,
    retry: false,
  });
  const candidates = (candidatesQuery.data?.items || []).filter((item) => item.type === "user");

  if (!workspace.sharesAccessible || !workspace.capabilities.can_share) return null;

  const changeRole = (nextRole: AssignableRole) => {
    setRole(nextRole);
  };

  const openForm = () => {
    setPrincipalId(null);
    setRecipientQuery("");
    changeRole("operator");
    setExpiresAt("");
    setFormError("");
    setOpen(true);
  };

  const save = async () => {
    setFormError("");
    if (!principalId) {
      setFormError(tr("Выберите пользователя из результатов поиска.", "Select a user from the search results."));
      return;
    }
    const saved = await workspace.saveShare({
      principal_type: "user",
      principal_id: principalId,
      role,
      capabilities: ROLE_CAPABILITIES[role],
      expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
    });
    if (saved) setOpen(false);
  };

  const roleDescription = {
    operator: tr("Просмотр, проверка, запуск и экспорт", "View, validate, run, and export"),
    editor: tr("Использование проекта и редактирование рабочей копии", "Use the project and edit its working copy"),
  }[role];
  const shareRoleLabel = (shareRole: PlaybookShareRole) => ({
    operator: tr("Использование", "Use"),
    editor: tr("Использование + редактирование", "Use + edit"),
    viewer: tr("Только просмотр", "View only"),
    manager: tr("Полный доступ", "Full access"),
  })[shareRole];
  const shareRoleDescription = (shareRole: PlaybookShareRole) => ({
    operator: tr("Проверка, запуск и экспорт", "Validate, run, and export"),
    editor: tr("Запуск, редактирование, проверка и экспорт", "Run, edit, validate, and export"),
    viewer: tr("Просмотр опубликованного содержимого (старый уровень)", "View published content (legacy level)"),
    manager: tr("Полный доступ, включая публикацию и управление доступом (старый уровень)", "Full access, including publish and access management (legacy level)"),
  })[shareRole];
  const copyLink = async () => {
    const url = new URL(`/automation/playbooks/${playbookId}`, window.location.origin).toString();
    try {
      await navigator.clipboard.writeText(url);
      setLinkCopied(true);
      setFormError("");
      window.setTimeout(() => setLinkCopied(false), 1600);
    } catch {
      setLinkCopied(false);
      notify.error({ title: tr("Не удалось скопировать внутреннюю ссылку", "Could not copy the internal link") });
    }
  };

  return (
    <section className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1" aria-labelledby="sharing-panel-title">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <div className="flex items-center gap-2">
            <Share2 className="h-4 w-4 text-primary" />
            <h3 id="sharing-panel-title" className="text-sm font-semibold text-foreground">
              {tr("Доступ к проекту", "Project access")}
            </h3>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {tr("Выберите пользователя и один из двух уровней доступа.", "Choose a user and one of two access levels.")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" className="gap-1.5" onClick={() => void copyLink()}>
            {linkCopied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
             {linkCopied ? tr("Ссылка скопирована", "Link copied") : tr("Копировать внутреннюю ссылку", "Copy internal link")}
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5" onClick={openForm}>
            <UserRoundCog className="h-3.5 w-3.5" />
            {tr("Добавить доступ", "Add access")}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-surface-0/35 px-4 py-2 text-xs text-muted-foreground">
        <span>{tr("Ссылка открывается только после входа и не даёт публичного доступа.", "The link requires sign-in and does not grant public access.")}</span>
        <a href="/settings/users" className="font-medium text-primary hover:underline">
          {tr("Управлять пользователями", "Manage users")}
        </a>
      </div>

      <div className="divide-y divide-border">
        {workspace.shares.length ? (
          workspace.shares.map((share) => {
            const revoked = Boolean(share.revoked_at);
            return (
              <div key={share.id} className={`flex flex-wrap items-center gap-3 px-4 py-3 ${revoked ? "opacity-50" : ""}`}>
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-0 text-muted-foreground">
                  {share.principal.type === "group" ? <UsersRound className="h-4 w-4" /> : <UserRound className="h-4 w-4" />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-foreground">{share.principal.label}</span>
                    <span className="rounded-sm bg-secondary px-1.5 py-0.5 text-2xs text-muted-foreground">{shareRoleLabel(share.role)}</span>
                    {revoked ? <span className="text-2xs text-destructive">{tr("Отозван", "Revoked")}</span> : null}
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {share.principal.type === "group" ? tr("Старая групповая выдача", "Legacy group grant") : tr("Пользователь", "User")}
                    {share.expires_at ? ` · ${tr("до", "until")} ${new Date(share.expires_at).toLocaleString()}` : ""}
                  </p>
                  <p className="mt-1 text-2xs text-muted-foreground">{shareRoleDescription(share.role)}</p>
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
          <div className="px-4 py-6 text-center text-sm text-muted-foreground">{tr("Доступ пока никому не выдан", "No access has been granted yet")}</div>
        )}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-xl" closeLabel={tr("Закрыть", "Close")}>
          <DialogHeader>
            <DialogTitle>{tr("Добавить или обновить доступ", "Add or update access")}</DialogTitle>
            <DialogDescription>
              {tr("Если доступ уже выдан, его уровень будет обновлён.", "If access already exists, its level will be updated.")}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="max-h-[70vh] space-y-4 overflow-auto">
            <div className="relative space-y-1.5">
              <Label htmlFor="share-principal-id">{tr("Пользователь", "User")}</Label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="share-principal-id"
                  aria-label={tr("Поиск пользователя", "Search user")}
                  className="pl-9"
                  value={recipientQuery}
                  onChange={(event) => {
                    const value = event.target.value;
                    setRecipientQuery(value);
                    setPrincipalId(null);
                  }}
                  placeholder={tr("Начните вводить имя", "Start typing a name")}
                />
              </div>
              {recipientQuery.trim() && !principalId ? (
                <div role="listbox" aria-label={tr("Найденные пользователи", "User search results")} className="absolute z-30 mt-1 max-h-44 w-full overflow-auto rounded-sm border border-border bg-popover p-1 shadow-elev-2">
                  {candidatesQuery.isPending ? (
                    <p className="flex items-center gap-2 px-2 py-2 text-xs text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" />{tr("Ищем…", "Searching…")}</p>
                  ) : candidates.length ? candidates.map((candidate) => (
                    <button
                      key={`${candidate.type}:${candidate.id}`}
                      type="button"
                      role="option"
                      aria-selected={principalId === candidate.id}
                      className="flex w-full items-center justify-between gap-2 rounded-sm px-2 py-2 text-left text-xs hover:bg-secondary"
                      onClick={() => { setPrincipalId(candidate.id); setRecipientQuery(candidate.label); }}
                    >
                      <span className="min-w-0 truncate font-medium text-foreground">{candidate.label}</span>
                      {candidate.secondary ? <span className="shrink-0 text-muted-foreground">{candidate.secondary}</span> : null}
                    </button>
                  )) : (
                    <p className="px-2 py-2 text-xs text-muted-foreground">{tr("Ничего не найдено", "No matches")}</p>
                  )}
                </div>
              ) : null}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="share-role">{tr("Уровень доступа", "Access level")}</Label>
                <Select value={role} onValueChange={(value) => changeRole(value as AssignableRole)}>
                  <SelectTrigger id="share-role" aria-label={tr("Уровень доступа", "Access level")} className="h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="operator">{tr("Использование", "Use")}</SelectItem>
                    <SelectItem value="editor">{tr("Использование + редактирование", "Use + edit")}</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">{roleDescription}</p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="share-expires">{tr("Истекает (необязательно)", "Expires (optional)")}</Label>
                <Input id="share-expires" type="datetime-local" value={expiresAt} onChange={(event) => setExpiresAt(event.target.value)} />
              </div>
            </div>
            {formError ? <p role="alert" className="text-xs text-destructive">{formError}</p> : null}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>{tr("Отмена", "Cancel")}</Button>
            <Button disabled={workspace.shareBusy || !principalId} onClick={() => void save()}>
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
