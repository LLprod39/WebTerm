import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, KeyRound, Trash2, UserPlus, ShieldCheck, Users as UsersIcon, ChevronDown, ChevronUp } from "lucide-react";

import {
  ACCESS_FEATURE_OPTIONS,
  createAccessUser,
  deleteAccessUser,
  fetchAccessGroups,
  fetchAccessUsers,
  setAccessUserPassword,
  updateAccessUser,
  type AccessUser,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { EmptyState, StatusBadge } from "@/components/ui/page-shell";
import { useI18n } from "@/lib/i18n";
import {
  ACCESS_UI_TEXT,
  formatAccessText,
  getAccessProfileLabel,
  getAccessSourceLabel,
  localizeAccessFeatures,
  summarizeAllowedFeatures,
} from "@/lib/accessUiText";

type PermissionMode = "inherit" | "allow" | "deny";

const SELECT_CLASS =
  "h-10 w-full rounded-lg border border-border bg-secondary/30 px-3 text-sm text-foreground outline-none ring-0 transition-all focus:border-primary/40 focus:ring-1 focus:ring-primary/30";

const FALLBACK_FEATURES = ACCESS_FEATURE_OPTIONS;

function createPermissionModes(
  features: Array<{ value: string; label: string }>,
  explicit?: Record<string, boolean>,
): Record<string, PermissionMode> {
  return Object.fromEntries(
    features.map((feature) => {
      const value = explicit?.[feature.value];
      return [feature.value, value === true ? "allow" : value === false ? "deny" : "inherit"];
    }),
  );
}

function buildExplicitPayload(modes: Record<string, PermissionMode>) {
  return Object.fromEntries(
    Object.entries(modes).map(([feature, mode]) => [feature, mode === "inherit" ? null : mode === "allow"]),
  );
}

function toggleId(source: number[], id: number) {
  return source.includes(id) ? source.filter((value) => value !== id) : [...source, id];
}

function FieldLabel({ htmlFor, children }: { htmlFor?: string; children: string }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
      {children}
    </label>
  );
}

function UserAvatar({ name, active }: { name: string; active: boolean }) {
  const initials = name.slice(0, 2).toUpperCase();
  return (
    <div
      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-xs font-bold tracking-wide transition-colors ${
        active
          ? "bg-primary/15 text-primary ring-1 ring-primary/20"
          : "bg-muted/40 text-muted-foreground ring-1 ring-border/40"
      }`}
    >
      {initials}
    </div>
  );
}

function PermissionSummary({
  lang,
  entries,
  features,
  title,
}: {
  lang: "en" | "ru";
  entries: Array<[string, boolean]>;
  features: Array<{ value: string; label: string }>;
  title: string;
}) {
  const allowedCount = entries.filter(([, allowed]) => allowed).length;
  const deniedCount = entries.length - allowedCount;
  const previewEntries = entries.slice(0, 6);
  const renderChip = ([feat, allowed]: [string, boolean]) => (
    <span
      key={feat}
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium ${
        allowed
          ? "bg-emerald-500/10 text-emerald-400"
          : "bg-red-500/8 text-red-400/80"
      }`}
    >
      {features.find((feature) => feature.value === feat)?.label || feat}
    </span>
  );

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground/70">
        <span className="font-semibold uppercase tracking-wider">{title}</span>
        <span>
          {allowedCount} {lang === "ru" ? "разрешено" : "allowed"}
        </span>
        <span>
          {deniedCount} {lang === "ru" ? "запрещено" : "denied"}
        </span>
      </div>
      <div className="flex flex-wrap gap-1.5 sm:hidden">
        {previewEntries.map(renderChip)}
        {entries.length > previewEntries.length && (
          <span className="inline-flex items-center rounded-md bg-secondary/35 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
            +{entries.length - previewEntries.length}
          </span>
        )}
      </div>
      <div className="hidden flex-wrap gap-1.5 sm:flex">
        {entries.map(renderChip)}
      </div>
    </div>
  );
}

function PermissionModeField({
  lang,
  label,
  mode,
  source,
  effective,
  onChange,
}: {
  lang: "en" | "ru";
  label: string;
  mode: PermissionMode;
  source?: string;
  effective?: boolean;
  onChange: (value: PermissionMode) => void;
}) {
  const t = ACCESS_UI_TEXT[lang].common;
  return (
    <div className="group/perm flex flex-col items-stretch gap-2 rounded-lg border border-border/40 bg-secondary/10 px-3 py-2.5 transition-colors hover:bg-secondary/20 2xl:flex-row 2xl:items-center 2xl:justify-between">
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium text-foreground/90">{label}</div>
        <div className="mt-0.5 text-[11px] text-muted-foreground/60">
          {t.effective}: {effective ? t.allowed : t.denied}
          {source ? ` · ${getAccessSourceLabel(lang, source)}` : ""}
        </div>
      </div>
      <select
        value={mode}
        onChange={(e) => onChange(e.target.value as PermissionMode)}
        className="h-8 w-full shrink-0 rounded-md border border-border bg-secondary/30 px-2 text-xs text-foreground outline-none focus:ring-1 focus:ring-primary/30 2xl:w-36"
        aria-label={`${label} mode`}
      >
        <option value="inherit">{t.inherit}</option>
        <option value="allow">{t.allow}</option>
        <option value="deny">{t.deny}</option>
      </select>
    </div>
  );
}

function GroupPicker({
  groups,
  selectedGroupIds,
  onToggle,
}: {
  groups: Array<{ id: number; name: string }>;
  selectedGroupIds: number[];
  onToggle: (groupId: number) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {groups.map((group) => {
        const active = selectedGroupIds.includes(group.id);
        return (
          <button
            key={group.id}
            type="button"
            onClick={() => onToggle(group.id)}
            className={`min-h-8 rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
              active
                ? "bg-primary/15 text-primary ring-1 ring-primary/25"
                : "bg-secondary/20 text-muted-foreground ring-1 ring-border/40 hover:bg-secondary/40 hover:text-foreground"
            }`}
          >
            {group.name}
          </button>
        );
      })}
      {groups.length === 0 && <span className="text-xs text-muted-foreground/50 italic">Нет групп</span>}
    </div>
  );
}

export default function SettingsUsersPage() {
  const { lang } = useI18n();
  const copy = ACCESS_UI_TEXT[lang].users;
  const common = ACCESS_UI_TEXT[lang].common;
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editing, setEditing] = useState<Record<string, unknown>>({});
  const [createForm, setCreateForm] = useState({
    username: "",
    email: "",
    password: "",
    is_staff: false,
    is_active: true,
    access_profile: "server_only",
    groups: [] as number[],
  });

  const { data: usersData, isLoading, error } = useQuery({
    queryKey: ["access", "users"],
    queryFn: fetchAccessUsers,
  });
  const { data: groupsData } = useQuery({
    queryKey: ["access", "groups"],
    queryFn: fetchAccessGroups,
  });

  const users = useMemo(() => usersData?.users ?? [], [usersData?.users]);
  const groups = useMemo(() => groupsData?.groups ?? [], [groupsData?.groups]);
  const features = useMemo(
    () => localizeAccessFeatures(lang, usersData?.features ?? groupsData?.features ?? FALLBACK_FEATURES),
    [groupsData?.features, lang, usersData?.features],
  );

  const refreshAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["access", "users"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "groups"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "permissions"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "group-permissions"] }),
    ]);
  };

  const startEdit = (user: AccessUser) => {
    setEditingId(user.id);
    setEditing({
      username: user.username,
      email: user.email,
      is_staff: user.is_staff,
      is_active: user.is_active,
      access_profile: user.access_profile || "custom",
      groups: (user.groups || []).map((group) => group.id),
      permission_modes: createPermissionModes(features, user.explicit_permissions),
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditing({});
  };

  const createUser = async () => {
    setSaving(true);
    try {
      await createAccessUser(createForm);
      setCreateForm({
        username: "",
        email: "",
        password: "",
        is_staff: false,
        is_active: true,
        access_profile: "server_only",
        groups: [],
      });
      await refreshAll();
    } finally {
      setSaving(false);
    }
  };

  const saveEdit = async () => {
    if (!editingId) return;
    const permissionModes = (editing.permission_modes as Record<string, PermissionMode> | undefined) || {};
    setSaving(true);
    try {
      await updateAccessUser(editingId, {
        username: editing.username,
        email: editing.email,
        is_staff: editing.is_staff,
        is_active: editing.is_active,
        access_profile: editing.access_profile,
        groups: editing.groups,
        explicit_permissions: buildExplicitPayload(permissionModes),
      });
      cancelEdit();
      await refreshAll();
    } finally {
      setSaving(false);
    }
  };

  const removeUser = async (user: AccessUser) => {
    if (!confirm(formatAccessText(copy.deleteConfirm, { name: user.username }))) return;
    await deleteAccessUser(user.id);
    await refreshAll();
  };

  const resetPassword = async (user: AccessUser) => {
    const password = prompt(formatAccessText(copy.passwordPrompt, { name: user.username }));
    if (!password) return;
    await setAccessUserPassword(user.id, password);
    alert(copy.passwordUpdated);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }
  if (error) {
    return <div className="p-6 text-sm text-destructive">{copy.error}</div>;
  }

  const activeUsers = users.filter((user) => user.is_active).length;
  const staffUsers = users.filter((user) => user.is_staff).length;

  return (
    <div className="space-y-6 pb-10">
      {/* ── Header ── */}
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
          <UsersIcon className="h-4 w-4 text-primary" />
        </div>
        <div>
          <h1 className="text-base font-semibold tracking-tight text-foreground">{copy.title}</h1>
          <p className="text-[11px] text-muted-foreground">{copy.subtitle}</p>
        </div>
      </div>

      {/* ── Stats row ── */}
      <div className="flex flex-wrap items-center gap-5 rounded-xl border border-border/60 bg-secondary/10 px-5 py-3 shadow-sm">
        <div className="flex items-center gap-2">
          <UsersIcon className="h-4 w-4 text-muted-foreground/50" />
          <span className="text-sm font-medium text-foreground">{users.length}</span>
          <span className="text-xs text-muted-foreground/60">{lang === "ru" ? "всего" : "total"}</span>
        </div>
        <div className="h-4 w-px bg-border/60" />
        <div className="flex items-center gap-1.5">
          <div className="h-2 w-2 rounded-full bg-emerald-400/80" />
          <span className="text-sm font-medium text-foreground">{activeUsers}</span>
          <span className="text-xs text-muted-foreground/60">{common.active.toLowerCase()}</span>
        </div>
        <div className="h-4 w-px bg-border/60" />
        <div className="flex items-center gap-1.5">
          <div className="h-2 w-2 rounded-full bg-blue-400/80" />
          <span className="text-sm font-medium text-foreground">{staffUsers}</span>
          <span className="text-xs text-muted-foreground/60">{common.staff}</span>
        </div>
        <div className="h-4 w-px bg-border/60" />
        <div className="flex items-center gap-1.5">
          <div className="h-2 w-2 rounded-full bg-violet-400/80" />
          <span className="text-sm font-medium text-foreground">{groups.length}</span>
          <span className="text-xs text-muted-foreground/60">{common.groups.toLowerCase()}</span>
        </div>
      </div>

      {/* ── Main 2-col layout ── */}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">

        {/* ── User directory ── */}
        <div className="space-y-3">
          {users.length === 0 && (
            <EmptyState
              icon={<UsersIcon className="h-6 w-6" />}
              title={lang === "ru" ? "Пользователей пока нет" : "No users yet"}
              description={lang === "ru" ? "Создайте первый аккаунт справа." : "Create the first account on the right."}
            />
          )}

          {users.map((user) => {
            const isEditing = editingId === user.id;
            const draft = editing as {
              username?: string;
              email?: string;
              is_staff?: boolean;
              is_active?: boolean;
              access_profile?: string;
              groups?: number[];
              permission_modes?: Record<string, PermissionMode>;
            };

            return (
              <div
                key={user.id}
                className={`rounded-xl border transition-all duration-200 ${
                  isEditing
                    ? "border-primary/30 bg-primary/[0.03] shadow-sm"
                    : "border-border/60 bg-card hover:bg-secondary/20 hover:border-border"
                }`}
              >
                {/* Card head — always visible */}
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
                          {common.groups}: {user.groups?.map((g) => g.name).join(", ")}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      onClick={() => (isEditing ? cancelEdit() : startEdit(user))}
                      className="flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground/60 transition-colors hover:bg-secondary/40 hover:text-foreground"
                      aria-label={isEditing ? common.cancel : copy.editAction}
                      title={isEditing ? common.cancel : copy.editAction}
                    >
                      {isEditing ? <ChevronUp className="h-4 w-4" /> : <Pencil className="h-3.5 w-3.5" />}
                    </button>
                    <button
                      onClick={() => void resetPassword(user)}
                      className="flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground/60 transition-colors hover:bg-secondary/40 hover:text-foreground"
                      aria-label={common.password}
                      title={common.password}
                    >
                      <KeyRound className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => void removeUser(user)}
                      className="flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground/60 transition-colors hover:bg-red-500/10 hover:text-red-400"
                      aria-label={common.delete}
                      title={common.delete}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                {/* Effective access summary — always visible */}
                {!isEditing && (user.effective_permissions && Object.keys(user.effective_permissions).length > 0) && (
                  <div className="border-t border-border/40 px-4 py-2.5">
                    <PermissionSummary
                      lang={lang}
                      entries={Object.entries(user.effective_permissions || {})}
                      features={features}
                      title={copy.effectiveAccess}
                    />
                  </div>
                )}

                {/* ── Edit panel (collapsible) ── */}
                {isEditing && (
                  <div className="border-t border-primary/15 px-4 pb-5 pt-4 space-y-5">
                    {/* Basic fields */}
                    <div className="grid gap-4 sm:grid-cols-3">
                      <div>
                        <FieldLabel htmlFor={`user-username-${user.id}`}>{copy.username}</FieldLabel>
                        <Input
                          id={`user-username-${user.id}`}
                          name="username"
                          autoComplete="username"
                          spellCheck={false}
                          value={draft.username || ""}
                          onChange={(e) => setEditing((s) => ({ ...s, username: e.target.value }))}
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
                          onChange={(e) => setEditing((s) => ({ ...s, email: e.target.value }))}
                          className="h-10 bg-secondary/20 border-border/60"
                        />
                      </div>
                      <div>
                        <FieldLabel htmlFor={`user-profile-${user.id}`}>{common.profile}</FieldLabel>
                        <select
                          id={`user-profile-${user.id}`}
                          value={draft.access_profile || "custom"}
                          onChange={(e) => setEditing((s) => ({ ...s, access_profile: e.target.value }))}
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

                    {/* Toggles */}
                    <div className="flex flex-wrap gap-6">
                      <label className="flex items-center gap-2.5 text-sm text-foreground/80 cursor-pointer select-none">
                        <Switch checked={!!draft.is_staff} onCheckedChange={(v) => setEditing((s) => ({ ...s, is_staff: v }))} />
                        {common.staff}
                      </label>
                      <label className="flex items-center gap-2.5 text-sm text-foreground/80 cursor-pointer select-none">
                        <Switch checked={!!draft.is_active} onCheckedChange={(v) => setEditing((s) => ({ ...s, is_active: v }))} />
                        {common.active}
                      </label>
                    </div>

                    {/* Groups */}
                    <div>
                      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">{common.groups}</div>
                      <GroupPicker
                        groups={groups}
                        selectedGroupIds={(draft.groups as number[]) || []}
                        onToggle={(groupId) =>
                          setEditing((s) => ({
                            ...s,
                            groups: toggleId(((s.groups as number[]) || []), groupId),
                          }))
                        }
                      />
                    </div>

                    {/* Permissions grid */}
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
                              setEditing((s) => ({
                                ...s,
                                permission_modes: {
                                  ...((s.permission_modes as Record<string, PermissionMode> | undefined) || {}),
                                  [feature.value]: value,
                                },
                              }))
                            }
                          />
                        ))}
                      </div>
                    </div>

                    {/* Save / Cancel */}
                    <div className="flex gap-2 pt-2">
                      <Button className="h-10" onClick={() => void saveEdit()} disabled={saving}>
                        {saving ? common.saving : common.save}
                      </Button>
                      <Button className="h-10" variant="ghost" onClick={cancelEdit} disabled={saving}>
                        {common.cancel}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* ── Create user sidebar ── */}
        <div className="order-first h-fit rounded-xl border border-border bg-card shadow-sm xl:order-none xl:sticky xl:top-4">
          <div className="flex items-center gap-3 border-b border-border/60 px-5 py-4">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
              <UserPlus className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-foreground">{copy.createTitle}</h2>
              <p className="text-[11px] text-muted-foreground/60">{copy.createHint}</p>
            </div>
          </div>
          <div className="space-y-4 px-5 py-5">
            <div>
              <FieldLabel htmlFor="create-user-username">{copy.username}</FieldLabel>
              <Input
                id="create-user-username"
                name="username"
                autoComplete="username"
                spellCheck={false}
                placeholder={copy.username}
                value={createForm.username}
                onChange={(e) => setCreateForm((s) => ({ ...s, username: e.target.value }))}
                className="h-10 bg-secondary/20 border-border/60"
              />
            </div>
            <div>
              <FieldLabel htmlFor="create-user-email">{copy.email}</FieldLabel>
              <Input
                id="create-user-email"
                name="email"
                type="email"
                autoComplete="email"
                spellCheck={false}
                placeholder={copy.email}
                value={createForm.email}
                onChange={(e) => setCreateForm((s) => ({ ...s, email: e.target.value }))}
                className="h-10 bg-secondary/20 border-border/60"
              />
            </div>
            <div>
              <FieldLabel htmlFor="create-user-password">{common.password}</FieldLabel>
              <Input
                id="create-user-password"
                name="new-password"
                type="password"
                autoComplete="new-password"
                placeholder={copy.passwordPlaceholder}
                value={createForm.password}
                onChange={(e) => setCreateForm((s) => ({ ...s, password: e.target.value }))}
                className="h-10 bg-secondary/20 border-border/60"
              />
            </div>
            <div>
              <FieldLabel htmlFor="create-user-profile">{common.profile}</FieldLabel>
              <select
                id="create-user-profile"
                value={createForm.access_profile}
                onChange={(e) => setCreateForm((s) => ({ ...s, access_profile: e.target.value }))}
                className={SELECT_CLASS}
                aria-label={common.profile}
              >
                <option value="server_only">{getAccessProfileLabel(lang, "server_only")}</option>
                <option value="admin_full">{getAccessProfileLabel(lang, "admin_full")}</option>
                <option value="custom">{getAccessProfileLabel(lang, "custom")}</option>
                <option value="reset_defaults">{getAccessProfileLabel(lang, "reset_defaults")}</option>
              </select>
            </div>

            <div className="flex flex-wrap gap-5 rounded-lg border border-border/40 bg-secondary/10 px-4 py-3">
              <label className="flex items-center gap-2.5 text-sm text-foreground/80 cursor-pointer select-none">
                <Switch
                  checked={createForm.is_staff}
                  onCheckedChange={(v) => setCreateForm((s) => ({ ...s, is_staff: v }))}
                />
                {common.staff}
              </label>
              <label className="flex items-center gap-2.5 text-sm text-foreground/80 cursor-pointer select-none">
                <Switch
                  checked={createForm.is_active}
                  onCheckedChange={(v) => setCreateForm((s) => ({ ...s, is_active: v }))}
                />
                {common.active}
              </label>
            </div>

            <div>
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">{common.groups}</div>
              <GroupPicker
                groups={groups}
                selectedGroupIds={createForm.groups}
                onToggle={(groupId) =>
                  setCreateForm((s) => ({ ...s, groups: toggleId(s.groups, groupId) }))
                }
              />
            </div>

            <Button
              className="h-10 w-full"
              onClick={() => void createUser()}
              disabled={saving || !createForm.username.trim() || !createForm.password.trim()}
            >
              {saving ? copy.creatingAction : copy.createAction}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
