import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
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

const FALLBACK_FEATURES = [
  { value: "servers", label: "Servers" },
  { value: "dashboard", label: "Dashboard" },
  { value: "agents", label: "Agents" },
  { value: "studio", label: "Studio" },
  { value: "settings", label: "Settings" },
  { value: "orchestrator", label: "Orchestrator" },
  { value: "knowledge_base", label: "Knowledge Base" },
];

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
  return (
    <div className="rounded-lg border border-border bg-background/40 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-foreground">{label}</div>
          <div className="mt-1 text-[11px] text-muted-foreground">
            {ACCESS_UI_TEXT[lang].common.effective}:{" "}
            {effective ? ACCESS_UI_TEXT[lang].common.allowed : ACCESS_UI_TEXT[lang].common.denied}
            {source ? ` • ${ACCESS_UI_TEXT[lang].common.source.toLowerCase()}: ${getAccessSourceLabel(lang, source)}` : ""}
          </div>
        </div>
        <select
          value={mode}
          onChange={(e) => onChange(e.target.value as PermissionMode)}
          className="rounded-md border border-border bg-secondary px-2 py-1 text-xs"
        >
          <option value="inherit">{ACCESS_UI_TEXT[lang].common.inherit}</option>
          <option value="allow">{ACCESS_UI_TEXT[lang].common.allow}</option>
          <option value="deny">{ACCESS_UI_TEXT[lang].common.deny}</option>
        </select>
      </div>
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
    <div className="flex flex-wrap gap-2">
      {groups.map((group) => {
        const active = selectedGroupIds.includes(group.id);
        return (
          <button
            key={group.id}
            type="button"
            onClick={() => onToggle(group.id)}
            className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
              active
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            {group.name}
          </button>
        );
      })}
    </div>
  );
}

function toggleId(source: number[], id: number) {
  return source.includes(id) ? source.filter((value) => value !== id) : [...source, id];
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
    return <div className="p-6 text-sm text-muted-foreground">{copy.loading}</div>;
  }
  if (error) {
    return <div className="p-6 text-sm text-destructive">{copy.error}</div>;
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">{copy.title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{copy.subtitle}</p>
      </div>

      <section className="space-y-4 rounded-lg border border-border bg-card p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-medium text-foreground">{copy.createTitle}</h2>
            <p className="text-xs text-muted-foreground">{copy.createHint}</p>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <Input
            placeholder={copy.username}
            value={createForm.username}
            onChange={(e) => setCreateForm((state) => ({ ...state, username: e.target.value }))}
          />
          <Input
            placeholder={copy.email}
            value={createForm.email}
            onChange={(e) => setCreateForm((state) => ({ ...state, email: e.target.value }))}
          />
          <Input
            type="password"
            placeholder={copy.passwordPlaceholder}
            value={createForm.password}
            onChange={(e) => setCreateForm((state) => ({ ...state, password: e.target.value }))}
          />
        </div>

        <div className="grid gap-3 md:grid-cols-[1.3fr_1fr]">
          <select
            value={createForm.access_profile}
            onChange={(e) => setCreateForm((state) => ({ ...state, access_profile: e.target.value }))}
            className="rounded-md border border-border bg-secondary px-3 py-2 text-sm"
          >
            <option value="server_only">{getAccessProfileLabel(lang, "server_only")}</option>
            <option value="admin_full">{getAccessProfileLabel(lang, "admin_full")}</option>
            <option value="custom">{getAccessProfileLabel(lang, "custom")}</option>
            <option value="reset_defaults">{getAccessProfileLabel(lang, "reset_defaults")}</option>
          </select>
          <div className="flex items-center gap-5">
            <label className="flex items-center gap-2 text-sm">
              {common.staff}
              <Switch
                checked={createForm.is_staff}
                onCheckedChange={(value) => setCreateForm((state) => ({ ...state, is_staff: value }))}
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              {common.active}
              <Switch
                checked={createForm.is_active}
                onCheckedChange={(value) => setCreateForm((state) => ({ ...state, is_active: value }))}
              />
            </label>
          </div>
        </div>

        <div className="space-y-2">
          <div className="text-xs text-muted-foreground">{common.groups}</div>
          <GroupPicker
            groups={groups}
            selectedGroupIds={createForm.groups}
            onToggle={(groupId) =>
              setCreateForm((state) => ({ ...state, groups: toggleId(state.groups, groupId) }))
            }
          />
        </div>

        <div>
          <Button
            onClick={() => void createUser()}
            disabled={saving || !createForm.username.trim() || !createForm.password.trim()}
          >
            {saving ? copy.creatingAction : copy.createAction}
          </Button>
        </div>
      </section>

      <section className="space-y-4">
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
            <div key={user.id} className="rounded-lg border border-border bg-card p-4">
              {!isEditing ? (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-start gap-3">
                    <div>
                      <div className="text-base font-medium text-foreground">{user.username}</div>
                      <div className="text-sm text-muted-foreground">{user.email || common.noEmail}</div>
                    </div>
                    <div className="ml-auto flex flex-wrap gap-2 text-xs">
                      <span className="rounded-full border border-border px-2 py-1 text-muted-foreground">
                        {common.profile.toLowerCase()}: {getAccessProfileLabel(lang, user.access_profile || "custom")}
                      </span>
                      <span className="rounded-full border border-border px-2 py-1 text-muted-foreground">
                        {user.is_staff ? common.staff : common.nonStaff}
                      </span>
                      <span className="rounded-full border border-border px-2 py-1 text-muted-foreground">
                        {user.is_active ? common.active : common.inactive}
                      </span>
                    </div>
                  </div>

                  <div className="space-y-2 text-sm">
                    <div>
                      <span className="text-muted-foreground">{common.groups}:</span>{" "}
                      {(user.groups || []).length
                        ? user.groups?.map((group) => group.name).join(", ")
                        : common.none}
                    </div>
                    <div>
                      <span className="text-muted-foreground">{copy.effectiveAccess}:</span>{" "}
                      {summarizeAllowedFeatures(lang, user.effective_permissions) || common.none}
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" onClick={() => startEdit(user)}>
                      {copy.editAction}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => void resetPassword(user)}>
                      {common.password}
                    </Button>
                    <Button size="sm" variant="destructive" onClick={() => void removeUser(user)}>
                      {common.delete}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="grid gap-3 md:grid-cols-3">
                    <Input
                      value={draft.username || ""}
                      onChange={(e) => setEditing((state) => ({ ...state, username: e.target.value }))}
                    />
                    <Input
                      value={draft.email || ""}
                      onChange={(e) => setEditing((state) => ({ ...state, email: e.target.value }))}
                    />
                    <select
                      value={draft.access_profile || "custom"}
                      onChange={(e) => setEditing((state) => ({ ...state, access_profile: e.target.value }))}
                      className="rounded-md border border-border bg-secondary px-3 py-2 text-sm"
                    >
                      <option value="server_only">{getAccessProfileLabel(lang, "server_only")}</option>
                      <option value="admin_full">{getAccessProfileLabel(lang, "admin_full")}</option>
                      <option value="custom">{getAccessProfileLabel(lang, "custom")}</option>
                      <option value="reset_defaults">{getAccessProfileLabel(lang, "reset_defaults")}</option>
                    </select>
                  </div>

                  <div className="flex items-center gap-5">
                    <label className="flex items-center gap-2 text-sm">
                      {common.staff}
                      <Switch
                        checked={!!draft.is_staff}
                        onCheckedChange={(value) => setEditing((state) => ({ ...state, is_staff: value }))}
                      />
                    </label>
                    <label className="flex items-center gap-2 text-sm">
                      {common.active}
                      <Switch
                        checked={!!draft.is_active}
                        onCheckedChange={(value) => setEditing((state) => ({ ...state, is_active: value }))}
                      />
                    </label>
                  </div>

                  <div className="space-y-2">
                    <div className="text-xs text-muted-foreground">{common.groups}</div>
                    <GroupPicker
                      groups={groups}
                      selectedGroupIds={(draft.groups as number[]) || []}
                      onToggle={(groupId) =>
                        setEditing((state) => ({
                          ...state,
                          groups: toggleId(((state.groups as number[]) || []), groupId),
                        }))
                      }
                    />
                  </div>

                  <div className="space-y-3">
                    <div>
                      <div className="text-sm font-medium text-foreground">{copy.explicitOverrides}</div>
                      <div className="text-xs text-muted-foreground">{copy.explicitOverridesHint}</div>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      {features.map((feature) => (
                        <PermissionModeField
                          key={feature.value}
                          lang={lang}
                          label={feature.label}
                          mode={draft.permission_modes?.[feature.value] || "inherit"}
                          source={user.permission_sources?.[feature.value]}
                          effective={user.effective_permissions?.[feature.value]}
                          onChange={(value) =>
                            setEditing((state) => ({
                              ...state,
                              permission_modes: {
                                ...((state.permission_modes as Record<string, PermissionMode> | undefined) || {}),
                                [feature.value]: value,
                              },
                            }))
                          }
                        />
                      ))}
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => void saveEdit()} disabled={saving}>
                      {saving ? common.saving : common.save}
                    </Button>
                    <Button size="sm" variant="outline" onClick={cancelEdit} disabled={saving}>
                      {common.cancel}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </section>
    </div>
  );
}
