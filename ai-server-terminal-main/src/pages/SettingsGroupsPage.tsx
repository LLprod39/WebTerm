import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createAccessGroup,
  deleteAccessGroup,
  fetchAccessGroups,
  fetchAccessUsers,
  updateAccessGroup,
  type AccessGroup,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/lib/i18n";
import {
  ACCESS_UI_TEXT,
  formatAccessText,
  getAccessFeatureLabel,
  localizeAccessFeatures,
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

function toggleId(source: number[], id: number) {
  return source.includes(id) ? source.filter((value) => value !== id) : [...source, id];
}

function MemberPicker({
  users,
  selectedIds,
  onToggle,
}: {
  users: Array<{ id: number; username: string }>;
  selectedIds: number[];
  onToggle: (id: number) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {users.map((user) => {
        const active = selectedIds.includes(user.id);
        return (
          <button
            key={user.id}
            type="button"
            onClick={() => onToggle(user.id)}
            className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
              active
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            {user.username}
          </button>
        );
      })}
    </div>
  );
}

function PermissionModeField({
  lang,
  label,
  mode,
  onChange,
}: {
  lang: "en" | "ru";
  label: string;
  mode: PermissionMode;
  onChange: (value: PermissionMode) => void;
}) {
  return (
    <div className="rounded-lg border border-border bg-background/40 p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-medium text-foreground">{label}</div>
        <select
          value={mode}
          onChange={(e) => onChange(e.target.value as PermissionMode)}
          className="rounded-md border border-border bg-secondary px-2 py-1 text-xs"
        >
          <option value="inherit">{ACCESS_UI_TEXT[lang].common.unset}</option>
          <option value="allow">{ACCESS_UI_TEXT[lang].common.allow}</option>
          <option value="deny">{ACCESS_UI_TEXT[lang].common.deny}</option>
        </select>
      </div>
    </div>
  );
}

export default function SettingsGroupsPage() {
  const { lang } = useI18n();
  const copy = ACCESS_UI_TEXT[lang].groupsPage;
  const common = ACCESS_UI_TEXT[lang].common;
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editing, setEditing] = useState<Record<string, unknown>>({});
  const [createName, setCreateName] = useState("");
  const [createMembers, setCreateMembers] = useState<number[]>([]);
  const [createPermissionModes, setCreatePermissionModes] = useState<Record<string, PermissionMode>>({});

  const { data: groupsData, isLoading, error } = useQuery({
    queryKey: ["access", "groups"],
    queryFn: fetchAccessGroups,
  });
  const { data: usersData } = useQuery({
    queryKey: ["access", "users"],
    queryFn: fetchAccessUsers,
  });

  const groups = useMemo(() => groupsData?.groups ?? [], [groupsData?.groups]);
  const users = useMemo(() => usersData?.users ?? [], [usersData?.users]);
  const features = useMemo(
    () => localizeAccessFeatures(lang, groupsData?.features ?? usersData?.features ?? FALLBACK_FEATURES),
    [groupsData?.features, lang, usersData?.features],
  );

  const refreshAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["access", "groups"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "users"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "permissions"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "group-permissions"] }),
    ]);
  };

  const startEdit = (group: AccessGroup) => {
    setEditingId(group.id);
    setEditing({
      name: group.name,
      members: (group.members || []).map((member) => member.id),
      permission_modes: createPermissionModes(features, group.explicit_permissions),
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditing({});
  };

  const createGroup = async () => {
    if (!createName.trim()) return;
    setSaving(true);
    try {
      await createAccessGroup({
        name: createName.trim(),
        members: createMembers,
        explicit_permissions: buildExplicitPayload(createPermissionModes),
      });
      setCreateName("");
      setCreateMembers([]);
      setCreatePermissionModes({});
      await refreshAll();
    } finally {
      setSaving(false);
    }
  };

  const saveEdit = async () => {
    if (!editingId) return;
    setSaving(true);
    try {
      await updateAccessGroup(editingId, {
        name: editing.name,
        members: editing.members,
        explicit_permissions: buildExplicitPayload(
          (editing.permission_modes as Record<string, PermissionMode> | undefined) || {},
        ),
      });
      cancelEdit();
      await refreshAll();
    } finally {
      setSaving(false);
    }
  };

  const removeGroup = async (group: AccessGroup) => {
    if (!confirm(formatAccessText(copy.deleteConfirm, { name: group.name }))) return;
    await deleteAccessGroup(group.id);
    await refreshAll();
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
        <h2 className="text-sm font-medium text-foreground">{copy.createTitle}</h2>
        <Input value={createName} onChange={(e) => setCreateName(e.target.value)} placeholder={copy.namePlaceholder} />

        <div className="space-y-2">
          <div className="text-xs text-muted-foreground">{common.members}</div>
          <MemberPicker users={users.map((user) => ({ id: user.id, username: user.username }))} selectedIds={createMembers} onToggle={(id) => setCreateMembers((prev) => toggleId(prev, id))} />
        </div>

        <div className="space-y-3">
          <div className="text-xs text-muted-foreground">{copy.policyTitle}</div>
          <div className="grid gap-3 md:grid-cols-2">
            {features.map((feature) => (
              <PermissionModeField
                key={feature.value}
                lang={lang}
                label={feature.label}
                mode={createPermissionModes[feature.value] || "inherit"}
                onChange={(value) =>
                  setCreatePermissionModes((state) => ({
                    ...state,
                    [feature.value]: value,
                  }))
                }
              />
            ))}
          </div>
        </div>

        <Button onClick={() => void createGroup()} disabled={saving || !createName.trim()}>
          {saving ? copy.creatingAction : copy.createAction}
        </Button>
      </section>

      <section className="space-y-4">
        {groups.map((group) => {
          const isEditing = editingId === group.id;
          const draft = editing as {
            name?: string;
            members?: number[];
            permission_modes?: Record<string, PermissionMode>;
          };

          return (
            <div key={group.id} className="rounded-lg border border-border bg-card p-4">
              {!isEditing ? (
                <div className="space-y-3">
                  <div className="flex items-start gap-3">
                    <div>
                      <div className="text-base font-medium text-foreground">{group.name}</div>
                      <div className="text-sm text-muted-foreground">
                        {common.members}: {group.member_count}
                        {group.members?.length ? ` • ${group.members.map((member) => member.username).join(", ")}` : ""}
                      </div>
                    </div>
                    <div className="ml-auto flex gap-2">
                      <Button size="sm" variant="outline" onClick={() => startEdit(group)}>
                        {copy.editAction}
                      </Button>
                      <Button size="sm" variant="destructive" onClick={() => void removeGroup(group)}>
                        {common.delete}
                      </Button>
                    </div>
                  </div>

                  <div className="text-xs text-muted-foreground">
                    {copy.explicitPolicy}:{" "}
                    {Object.entries(group.explicit_permissions || {})
                      .map(([feature, allowed]) => `${getAccessFeatureLabel(lang, feature)}:${allowed ? common.allowed.toLowerCase() : common.denied.toLowerCase()}`)
                      .join(", ") || common.none}
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <Input
                    value={draft.name || ""}
                    onChange={(e) => setEditing((state) => ({ ...state, name: e.target.value }))}
                  />

                  <div className="space-y-2">
                    <div className="text-xs text-muted-foreground">{common.members}</div>
                    <MemberPicker
                      users={users.map((user) => ({ id: user.id, username: user.username }))}
                      selectedIds={(draft.members as number[]) || []}
                      onToggle={(id) =>
                        setEditing((state) => ({
                          ...state,
                          members: toggleId(((state.members as number[]) || []), id),
                        }))
                      }
                    />
                  </div>

                  <div className="space-y-3">
                    <div className="text-xs text-muted-foreground">{copy.policyTitle}</div>
                    <div className="grid gap-3 md:grid-cols-2">
                      {features.map((feature) => (
                        <PermissionModeField
                          key={feature.value}
                          lang={lang}
                          label={feature.label}
                          mode={draft.permission_modes?.[feature.value] || "inherit"}
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
