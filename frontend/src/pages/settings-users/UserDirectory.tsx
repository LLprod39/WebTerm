import type { Dispatch, SetStateAction } from "react";
import { ChevronUp, KeyRound, Pencil, Trash2, Users as UsersIcon } from "lucide-react";

import type { AccessUser } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { EmptyState, StatusBadge } from "@/components/ui/page-shell";
import { ACCESS_UI_TEXT, getAccessProfileLabel } from "@/lib/accessUiText";
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

type AsyncAction = () => void | Promise<void>;
type AsyncUserAction = (user: AccessUser) => void | Promise<void>;

export type UserDirectoryProps = {
  lang: "en" | "ru";
  users: AccessUser[];
  groups: AccessGroupOption[];
  features: AccessFeatureOption[];
  saving: boolean;
  editingId: number | null;
  editing: UserEditDraft;
  onStartEdit: (user: AccessUser) => void;
  onCancelEdit: () => void;
  onSaveEdit: AsyncAction;
  onRemoveUser: AsyncUserAction;
  onResetPassword: AsyncUserAction;
  onEditingChange: Dispatch<SetStateAction<UserEditDraft>>;
};

function UserEditPanel({
  lang,
  user,
  draft,
  groups,
  features,
  saving,
  onEditingChange,
  onSaveEdit,
  onCancelEdit,
}: {
  lang: "en" | "ru";
  user: AccessUser;
  draft: UserEditDraft;
  groups: AccessGroupOption[];
  features: AccessFeatureOption[];
  saving: boolean;
  onEditingChange: Dispatch<SetStateAction<UserEditDraft>>;
  onSaveEdit: AsyncAction;
  onCancelEdit: () => void;
}) {
  const copy = ACCESS_UI_TEXT[lang].users;
  const common = ACCESS_UI_TEXT[lang].common;
  const selectedGroups = draft.groups || [];

  return (
    <div className="space-y-5 border-t border-primary/15 px-4 pb-5 pt-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <FieldLabel htmlFor={`user-username-${user.id}`}>{copy.username}</FieldLabel>
          <Input
            id={`user-username-${user.id}`}
            name="username"
            autoComplete="username"
            spellCheck={false}
            value={draft.username || ""}
            onChange={(event) => onEditingChange((state) => ({ ...state, username: event.target.value }))}
            className="h-10 bg-secondary/20 border-border/60"
          />
        </div>
        <div>
          <FieldLabel htmlFor={`user-email-${user.id}`}>{copy.email}</FieldLabel>
          <Input
            id={`user-email-${user.id}`}
            name="email"
            type="email"
            autoComplete="email"
            spellCheck={false}
            value={draft.email || ""}
            onChange={(event) => onEditingChange((state) => ({ ...state, email: event.target.value }))}
            className="h-10 bg-secondary/20 border-border/60"
          />
        </div>
        <div>
          <FieldLabel htmlFor={`user-profile-${user.id}`}>{common.profile}</FieldLabel>
          <select
            id={`user-profile-${user.id}`}
            value={draft.access_profile || "custom"}
            onChange={(event) => onEditingChange((state) => ({ ...state, access_profile: event.target.value }))}
            className={SELECT_CLASS}
            aria-label={common.profile}
          >
            <option value="server_only">{getAccessProfileLabel(lang, "server_only")}</option>
            <option value="admin_full">{getAccessProfileLabel(lang, "admin_full")}</option>
            <option value="custom">{getAccessProfileLabel(lang, "custom")}</option>
            <option value="reset_defaults">{getAccessProfileLabel(lang, "reset_defaults")}</option>
          </select>
        </div>
      </div>

      <div className="flex flex-wrap gap-6">
        <label className="flex cursor-pointer select-none items-center gap-2.5 text-sm text-foreground/80">
          <Switch checked={!!draft.is_staff} onCheckedChange={(value) => onEditingChange((state) => ({ ...state, is_staff: value }))} />
          {common.staff}
        </label>
        <label className="flex cursor-pointer select-none items-center gap-2.5 text-sm text-foreground/80">
          <Switch checked={!!draft.is_active} onCheckedChange={(value) => onEditingChange((state) => ({ ...state, is_active: value }))} />
          {common.active}
        </label>
      </div>

      <div>
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">{common.groups}</div>
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
      </div>

      <div>
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">{copy.explicitOverrides}</div>
        <div className="mb-3 text-xs text-muted-foreground/50">{copy.explicitOverridesHint}</div>
        <div className="grid gap-2 sm:grid-cols-2">
          {features.map((feature) => (
            <PermissionModeField
              key={feature.value}
              lang={lang}
              label={feature.label}
              mode={draft.permission_modes?.[feature.value] || "inherit"}
              source={user.permission_sources?.[feature.value]}
              effective={user.effective_permissions?.[feature.value]}
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
      </div>

      <div className="flex gap-2 pt-2">
        <Button className="h-10" onClick={() => void onSaveEdit()} disabled={saving}>
          {saving ? common.saving : common.save}
        </Button>
        <Button className="h-10" variant="ghost" onClick={onCancelEdit} disabled={saving}>
          {common.cancel}
        </Button>
      </div>
    </div>
  );
}

function UserCard({
  lang,
  user,
  isEditing,
  draft,
  groups,
  features,
  saving,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onRemoveUser,
  onResetPassword,
  onEditingChange,
}: Omit<UserDirectoryProps, "users" | "editingId" | "editing"> & {
  user: AccessUser;
  isEditing: boolean;
  draft: UserEditDraft;
}) {
  const copy = ACCESS_UI_TEXT[lang].users;
  const common = ACCESS_UI_TEXT[lang].common;

  return (
    <div
      className={`rounded-xl border transition-all duration-200 ${
        isEditing
          ? "border-primary/30 bg-primary/[0.03] shadow-sm"
          : "border-border/60 bg-card hover:bg-secondary/20 hover:border-border"
      }`}
    >
      <div className="flex items-center gap-3 px-4 py-3.5">
        <UserAvatar name={user.username} active={user.is_active} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[15px] font-semibold text-foreground">{user.username}</span>
            <StatusBadge label={getAccessProfileLabel(lang, user.access_profile || "custom")} dot={false} />
            {!user.is_active && <StatusBadge label={common.inactive} tone="warning" />}
            {user.is_staff && <StatusBadge label={common.staff} tone="info" dot={false} />}
          </div>
          <div className="mt-0.5 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground/60">
            <span>{user.email || common.noEmail}</span>
            {(user.groups || []).length > 0 && (
              <span>
                {common.groups}: {user.groups?.map((group) => group.name).join(", ")}
              </span>
            )}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <button
            onClick={() => (isEditing ? onCancelEdit() : onStartEdit(user))}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground/60 transition-colors hover:bg-secondary/40 hover:text-foreground"
            aria-label={isEditing ? common.cancel : copy.editAction}
            title={isEditing ? common.cancel : copy.editAction}
          >
            {isEditing ? <ChevronUp className="h-4 w-4" /> : <Pencil className="h-3.5 w-3.5" />}
          </button>
          <button
            onClick={() => void onResetPassword(user)}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground/60 transition-colors hover:bg-secondary/40 hover:text-foreground"
            aria-label={common.password}
            title={common.password}
          >
            <KeyRound className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => void onRemoveUser(user)}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground/60 transition-colors hover:bg-red-500/10 hover:text-red-400"
            aria-label={common.delete}
            title={common.delete}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {!isEditing && user.effective_permissions && Object.keys(user.effective_permissions).length > 0 && (
        <div className="border-t border-border/40 px-4 py-2.5">
          <PermissionSummary
            lang={lang}
            entries={Object.entries(user.effective_permissions || {})}
            features={features}
            title={copy.effectiveAccess}
          />
        </div>
      )}

      {isEditing && (
        <UserEditPanel
          lang={lang}
          user={user}
          draft={draft}
          groups={groups}
          features={features}
          saving={saving}
          onEditingChange={onEditingChange}
          onSaveEdit={onSaveEdit}
          onCancelEdit={onCancelEdit}
        />
      )}
    </div>
  );
}

export function UserDirectory(props: UserDirectoryProps) {
  const { lang, users, editingId, editing } = props;

  return (
    <div className="space-y-3">
      {users.length === 0 && (
        <EmptyState
          icon={<UsersIcon className="h-6 w-6" />}
          title={lang === "ru" ? "Пользователей пока нет" : "No users yet"}
          description={lang === "ru" ? "Создайте первый аккаунт справа." : "Create the first account on the right."}
        />
      )}

      {users.map((user) => (
        <UserCard
          key={user.id}
          {...props}
          user={user}
          isEditing={editingId === user.id}
          draft={editing}
        />
      ))}
    </div>
  );
}
