import type { Dispatch, SetStateAction } from "react";
import { KeyRound, Pencil, ShieldCheck, Trash2, Users as UsersIcon } from "lucide-react";

import type { AccessUser } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, StatusBadge } from "@/components/ui/page-shell";
import { InlineAlert } from "@/components/system/InlineAlert";
import { ACCESS_PROFILE_OPTIONS, ACCESS_UI_TEXT, getAccessProfileLabel } from "@/lib/accessUiText";
import { toggleId } from "./accessUserPermissions";
import {
  FieldLabel,
  GroupPicker,
  PermissionModeField,
  PermissionSummary,
  SELECT_CLASS,
  UserAvatar,
} from "./SettingsUsersShared";
import type { AccessFeatureOption, AccessGroupOption, UserEditDraft } from "./settingsUsersTypes";
import type { UserValidationResult } from "./userValidation";

type AsyncAction = () => boolean | Promise<boolean>;
type AsyncUserAction = (user: AccessUser) => void | Promise<void>;

export type UserDirectoryProps = {
  lang: "en" | "ru";
  users: AccessUser[];
  groups: AccessGroupOption[];
  features: AccessFeatureOption[];
  saving: boolean;
  editingId: number | null;
  editing: UserEditDraft;
  editValidation: UserValidationResult;
  onStartEdit: (user: AccessUser) => void;
  onCancelEdit: () => void;
  onSaveEdit: AsyncAction;
  onRemoveUser: AsyncUserAction;
  onResetPassword: AsyncUserAction;
  onEditingChange: Dispatch<SetStateAction<UserEditDraft>>;
};

function UserEditSheet({
  lang,
  user,
  draft,
  groups,
  features,
  saving,
  validation,
  onEditingChange,
  onSaveEdit,
  onCancelEdit,
}: {
  lang: "en" | "ru";
  user: AccessUser | null;
  draft: UserEditDraft;
  groups: AccessGroupOption[];
  features: AccessFeatureOption[];
  saving: boolean;
  validation: UserValidationResult;
  onEditingChange: Dispatch<SetStateAction<UserEditDraft>>;
  onSaveEdit: AsyncAction;
  onCancelEdit: () => void;
}) {
  const copy = ACCESS_UI_TEXT[lang].users;
  const common = ACCESS_UI_TEXT[lang].common;
  const selectedGroups = draft.groups || [];
  const showFieldErrors = Boolean(draft.username || draft.email);

  return (
    <Sheet open={Boolean(user)} onOpenChange={(open) => !open && !saving && onCancelEdit()}>
      <SheetContent className="w-full overflow-y-auto p-0 sm:max-w-2xl">
        <SheetHeader className="border-b border-border/70 px-6 py-5 pr-14">
          <SheetTitle className="flex items-center gap-2 text-base">
            <ShieldCheck className="h-4 w-4 text-primary" />
            {copy.editAction}
          </SheetTitle>
          <SheetDescription>
            {user ? `${user.username} · ${user.email || common.noEmail}` : copy.explicitOverridesHint}
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-6 px-6 py-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <FieldLabel htmlFor="edit-user-username">{copy.username}</FieldLabel>
              <Input
                id="edit-user-username"
                name="username"
                autoComplete="username"
                spellCheck={false}
                value={draft.username || ""}
                onChange={(event) => onEditingChange((state) => ({ ...state, username: event.target.value }))}
                className="h-10 bg-secondary/20 border-border/60"
                aria-invalid={Boolean(showFieldErrors && validation.errors.username)}
                aria-describedby={showFieldErrors && validation.errors.username ? "edit-user-username-error" : undefined}
              />
              {showFieldErrors && validation.errors.username ? (
                <p id="edit-user-username-error" className="mt-1 text-xs text-destructive">{validation.errors.username}</p>
              ) : null}
            </div>
            <div>
              <FieldLabel htmlFor="edit-user-email">{copy.email}</FieldLabel>
              <Input
                id="edit-user-email"
                name="email"
                type="email"
                autoComplete="email"
                spellCheck={false}
                value={draft.email || ""}
                onChange={(event) => onEditingChange((state) => ({ ...state, email: event.target.value }))}
                className="h-10 bg-secondary/20 border-border/60"
                aria-invalid={Boolean(showFieldErrors && validation.errors.email)}
                aria-describedby={showFieldErrors && validation.errors.email ? "edit-user-email-error" : undefined}
              />
              {showFieldErrors && validation.errors.email ? (
                <p id="edit-user-email-error" className="mt-1 text-xs text-destructive">{validation.errors.email}</p>
              ) : null}
            </div>
            <div>
              <FieldLabel htmlFor="edit-user-profile">{common.profile}</FieldLabel>
              <Select
                value={draft.access_profile || "custom"}
                onValueChange={(value) => onEditingChange((state) => ({ ...state, access_profile: value }))}
              >
                <SelectTrigger id="edit-user-profile" className={SELECT_CLASS} aria-label={common.profile}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ACCESS_PROFILE_OPTIONS.map((profile) => (
                    <SelectItem key={profile} value={profile}>{getAccessProfileLabel(lang, profile)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end gap-6 rounded-lg border border-border/40 bg-secondary/10 px-4 py-3">
              <label className="flex cursor-pointer select-none items-center gap-2.5 text-sm text-foreground/80">
                <Switch checked={!!draft.is_staff} onCheckedChange={(value) => onEditingChange((state) => ({ ...state, is_staff: value }))} />
                {common.staff}
              </label>
              <label className="flex cursor-pointer select-none items-center gap-2.5 text-sm text-foreground/80">
                <Switch checked={!!draft.is_active} onCheckedChange={(value) => onEditingChange((state) => ({ ...state, is_active: value }))} />
                {common.active}
              </label>
            </div>
            {draft.is_staff ? (
              <div className="sm:col-span-2">
                <InlineAlert
                  tone="warning"
                  description={lang === "ru"
                    ? "Этот флаг даёт широкие права. Безопаснее выбрать профиль без секретов или задать явные запреты."
                    : "Staff receives broad default access. For a pilot, prefer a no-secrets profile or explicit denies."}
                />
              </div>
            ) : null}
          </div>

          <section>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{common.groups}</div>
            <GroupPicker
              groups={groups}
              selectedGroupIds={selectedGroups}
              onToggle={(groupId) =>
                onEditingChange((state) => ({
                  ...state,
                  groups: toggleId(state.groups || [], groupId),
                }))
              }
            />
          </section>

          <section>
            <div className="mb-1.5 text-xs font-semibold text-muted-foreground/80">{copy.explicitOverrides}</div>
            <div className="mb-3 text-xs text-muted-foreground">{copy.explicitOverridesHint}</div>
            <div className="grid gap-2 sm:grid-cols-2">
              {features.map((feature) => (
                <PermissionModeField
                  key={feature.value}
                  lang={lang}
                  label={feature.label}
                  mode={draft.permission_modes?.[feature.value] || "inherit"}
                  source={user?.permission_sources?.[feature.value]}
                  effective={user?.effective_permissions?.[feature.value]}
                  onChange={(value) =>
                    onEditingChange((state) => ({
                      ...state,
                      permission_modes: {
                        ...(state.permission_modes || {}),
                        [feature.value]: value,
                      },
                    }))
                  }
                />
              ))}
            </div>
          </section>

          {!validation.isValid ? <InlineAlert tone="warning" description={validation.summary} /> : null}
        </div>

        <SheetFooter className="sticky bottom-0 gap-2 border-t border-border/70 bg-card/95 px-6 py-4 backdrop-blur">
          <Button className="h-10" onClick={() => void onSaveEdit()} disabled={saving || !validation.isValid}>
            {saving ? common.saving : common.save}
          </Button>
          <Button className="h-10" variant="outline" onClick={onCancelEdit} disabled={saving}>
            {common.cancel}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function UserActions({
  lang,
  user,
  onStartEdit,
  onRemoveUser,
  onResetPassword,
}: {
  lang: "en" | "ru";
  user: AccessUser;
  onStartEdit: (user: AccessUser) => void;
  onRemoveUser: AsyncUserAction;
  onResetPassword: AsyncUserAction;
}) {
  const copy = ACCESS_UI_TEXT[lang].users;
  const common = ACCESS_UI_TEXT[lang].common;

  return (
    <div className="flex items-center justify-end gap-1">
      <Button size="icon" variant="ghost" className="h-9 w-9" onClick={() => onStartEdit(user)} aria-label={copy.editAction} title={copy.editAction}>
        <Pencil className="h-3.5 w-3.5" />
      </Button>
      <Button size="icon" variant="ghost" className="h-9 w-9" onClick={() => void onResetPassword(user)} aria-label={common.password} title={common.password}>
        <KeyRound className="h-3.5 w-3.5" />
      </Button>
      <Button
        size="icon"
        variant="ghost"
        className="h-9 w-9 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
        onClick={() => void onRemoveUser(user)}
        aria-label={common.delete}
        title={common.delete}
      >
        <Trash2 className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

export function UserDirectory(props: UserDirectoryProps) {
  const {
    lang,
    users,
    groups,
    features,
    saving,
    editingId,
    editing,
    editValidation,
    onStartEdit,
    onCancelEdit,
    onSaveEdit,
    onRemoveUser,
    onResetPassword,
    onEditingChange,
  } = props;
  const copy = ACCESS_UI_TEXT[lang].users;
  const common = ACCESS_UI_TEXT[lang].common;
  const editingUser = users.find((user) => user.id === editingId) || null;

  if (users.length === 0) {
    return (
      <EmptyState
        icon={<UsersIcon className="h-6 w-6" />}
        title={lang === "ru" ? "Пользователей пока нет" : "No users yet"}
        description={lang === "ru" ? "Создайте первый аккаунт через кнопку сверху." : "Create the first account from the top action."}
      />
    );
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{copy.username}</TableHead>
            <TableHead>{common.profile}</TableHead>
            <TableHead>{common.groups}</TableHead>
            <TableHead>{copy.effectiveAccess}</TableHead>
            <TableHead className="w-32 text-right">{common.toggle}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.map((user) => (
            <TableRow key={user.id} data-state={editingId === user.id ? "selected" : undefined}>
              <TableCell>
                <div className="flex items-center gap-3">
                  <UserAvatar name={user.username} active={user.is_active} />
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-foreground">{user.username}</span>
                      {!user.is_active ? <StatusBadge label={common.inactive} tone="warning" /> : null}
                      {user.is_staff ? <StatusBadge label={common.staff} tone="info" dot={false} /> : null}
                    </div>
                    <div className="mt-0.5 truncate text-xs text-muted-foreground">{user.email || common.noEmail}</div>
                  </div>
                </div>
              </TableCell>
              <TableCell>
                <StatusBadge label={getAccessProfileLabel(lang, user.access_profile || "custom")} dot={false} />
              </TableCell>
              <TableCell className="max-w-[220px]">
                {(user.groups || []).length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {user.groups?.map((group) => (
                      <span key={group.id} className="rounded-md bg-secondary/50 px-2 py-0.5 text-xs text-muted-foreground">
                        {group.name}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-xs text-muted-foreground">{common.none}</span>
                )}
              </TableCell>
              <TableCell className="min-w-[260px]">
                {user.effective_permissions && Object.keys(user.effective_permissions).length > 0 ? (
                  <PermissionSummary
                    lang={lang}
                    entries={Object.entries(user.effective_permissions || {})}
                    features={features}
                    title=""
                  />
                ) : (
                  <span className="text-xs text-muted-foreground">{common.none}</span>
                )}
              </TableCell>
              <TableCell>
                <UserActions
                  lang={lang}
                  user={user}
                  onStartEdit={onStartEdit}
                  onRemoveUser={onRemoveUser}
                  onResetPassword={onResetPassword}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <UserEditSheet
        lang={lang}
        user={editingUser}
        draft={editing}
        groups={groups}
        features={features}
        saving={saving}
        validation={editValidation}
        onEditingChange={onEditingChange}
        onSaveEdit={onSaveEdit}
        onCancelEdit={onCancelEdit}
      />
    </>
  );
}
