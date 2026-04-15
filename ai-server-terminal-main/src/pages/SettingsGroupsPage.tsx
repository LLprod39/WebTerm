import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2, FolderPlus, Users, ChevronUp } from "lucide-react";

import {
  ACCESS_FEATURE_OPTIONS,
  createAccessGroup,
  deleteAccessGroup,
  fetchAccessGroups,
  fetchAccessUsers,
  updateAccessGroup,
  type AccessGroup,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, StatusBadge } from "@/components/ui/page-shell";
import { useI18n } from "@/lib/i18n";
import {
  ACCESS_UI_TEXT,
  formatAccessText,
  getAccessFeatureLabel,
  localizeAccessFeatures,
} from "@/lib/accessUiText";

type PermissionMode = "inherit" | "allow" | "deny";

const SELECT_CLASS =
  "h-9 w-full rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 text-sm text-foreground outline-none ring-0 transition-all focus:border-primary/40 focus:ring-1 focus:ring-primary/30";

const FALLBACK_FEATURES = ACCESS_FEATURE_OPTIONS;

/* ── helpers ── */
function createPermissionModesFromExplicit(
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

/* ── micro-components ── */
function FieldLabel({ htmlFor, children }: { htmlFor?: string; children: string }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
      {children}
    </label>
  );
}

function GroupAvatar({ name, count }: { name: string; count: number }) {
  const initials = name.slice(0, 2).toUpperCase();
  return (
    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-violet-500/15 text-xs font-bold tracking-wide text-violet-400 ring-1 ring-violet-500/20">
      {initials}
    </div>
  );
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
    <div className="flex flex-wrap gap-1.5">
      {users.map((user) => {
        const active = selectedIds.includes(user.id);
        return (
          <button
            key={user.id}
            type="button"
            onClick={() => onToggle(user.id)}
            className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
              active
                ? "bg-primary/15 text-primary ring-1 ring-primary/25"
                : "bg-white/[0.03] text-muted-foreground ring-1 ring-white/[0.06] hover:bg-white/[0.06] hover:text-foreground"
            }`}
          >
            {user.username}
          </button>
        );
      })}
      {users.length === 0 && <span className="text-xs text-muted-foreground/50 italic">Нет пользователей</span>}
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
  const t = ACCESS_UI_TEXT[lang].common;
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-white/[0.04] bg-white/[0.02] px-3 py-2.5 transition-colors hover:bg-white/[0.04]">
      <div className="text-[13px] font-medium text-foreground/90">{label}</div>
      <select
        value={mode}
        onChange={(e) => onChange(e.target.value as PermissionMode)}
        className="h-7 rounded-md border border-white/[0.06] bg-white/[0.03] px-2 text-xs text-foreground outline-none focus:ring-1 focus:ring-primary/30"
        aria-label={`${label} mode`}
      >
        <option value="inherit">{t.unset || t.inherit}</option>
        <option value="allow">{t.allow}</option>
        <option value="deny">{t.deny}</option>
      </select>
    </div>
  );
}

/* ── page ── */
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
  const [createPModes, setCreatePModes] = useState<Record<string, PermissionMode>>({});

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
      permission_modes: createPermissionModesFromExplicit(features, group.explicit_permissions),
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
        explicit_permissions: buildExplicitPayload(createPModes),
      });
      setCreateName("");
      setCreateMembers([]);
      setCreatePModes({});
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
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }
  if (error) {
    return <div className="p-6 text-sm text-destructive">{copy.error}</div>;
  }

  const totalMembers = groups.reduce((sum, g) => sum + g.member_count, 0);

  return (
    <div className="space-y-6 pb-10">
      {/* ── Header ── */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">{copy.title}</h1>
        <p className="mt-1 text-sm text-muted-foreground/70">{copy.subtitle}</p>
      </div>

      {/* ── Stats row ── */}
      <div className="flex flex-wrap items-center gap-5 rounded-xl border border-white/[0.06] bg-white/[0.02] px-5 py-3">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-muted-foreground/50" />
          <span className="text-sm font-medium text-foreground">{groups.length}</span>
          <span className="text-xs text-muted-foreground/60">{lang === "ru" ? "групп" : "groups"}</span>
        </div>
        <div className="h-4 w-px bg-white/[0.06]" />
        <div className="flex items-center gap-1.5">
          <div className="h-2 w-2 rounded-full bg-violet-400/80" />
          <span className="text-sm font-medium text-foreground">{totalMembers}</span>
          <span className="text-xs text-muted-foreground/60">{common.members.toLowerCase()}</span>
        </div>
        <div className="h-4 w-px bg-white/[0.06]" />
        <div className="flex items-center gap-1.5">
          <div className="h-2 w-2 rounded-full bg-amber-400/80" />
          <span className="text-sm font-medium text-foreground">{features.length}</span>
          <span className="text-xs text-muted-foreground/60">{lang === "ru" ? "фич" : "features"}</span>
        </div>
      </div>

      {/* ── Main 2-col layout ── */}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">

        {/* ── Group directory ── */}
        <div className="space-y-3">
          {groups.length === 0 && (
            <EmptyState
              icon={<Users className="h-6 w-6" />}
              title={lang === "ru" ? "Групп пока нет" : "No groups yet"}
              description={lang === "ru" ? "Создайте первую группу справа." : "Create the first group on the right."}
            />
          )}

          {groups.map((group) => {
            const isEditing = editingId === group.id;
            const draft = editing as {
              name?: string;
              members?: number[];
              permission_modes?: Record<string, PermissionMode>;
            };

            return (
              <div
                key={group.id}
                className={`rounded-xl border transition-all duration-200 ${
                  isEditing
                    ? "border-primary/30 bg-white/[0.03] shadow-[0_0_0_1px_rgba(var(--primary-rgb),0.1)]"
                    : "border-white/[0.06] bg-white/[0.015] hover:bg-white/[0.03] hover:border-white/[0.1]"
                }`}
              >
                {/* Card head */}
                <div className="flex items-center gap-3 px-4 py-3.5">
                  <GroupAvatar name={group.name} count={group.member_count} />

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[15px] font-semibold text-foreground">{group.name}</span>
                      <StatusBadge label={`${group.member_count} ${common.members.toLowerCase()}`} tone="info" dot={false} />
                    </div>
                    <div className="mt-0.5 text-xs text-muted-foreground/60">
                      {group.members?.length
                        ? group.members.map((m) => m.username).join(", ")
                        : lang === "ru" ? "Нет участников" : "No members"}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      onClick={() => (isEditing ? cancelEdit() : startEdit(group))}
                      className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground/50 transition-colors hover:bg-white/[0.06] hover:text-foreground"
                      title={isEditing ? common.cancel : copy.editAction}
                    >
                      {isEditing ? <ChevronUp className="h-4 w-4" /> : <Pencil className="h-3.5 w-3.5" />}
                    </button>
                    <button
                      onClick={() => void removeGroup(group)}
                      className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground/50 transition-colors hover:bg-red-500/10 hover:text-red-400"
                      title={common.delete}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                {/* Policy summary — shown when not editing */}
                {!isEditing && group.explicit_permissions && Object.keys(group.explicit_permissions).length > 0 && (
                  <div className="border-t border-white/[0.04] px-4 py-2.5">
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(group.explicit_permissions).map(([feat, allowed]) => (
                        <span
                          key={feat}
                          className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium ${
                            allowed
                              ? "bg-emerald-500/10 text-emerald-400"
                              : "bg-red-500/8 text-red-400/80"
                          }`}
                        >
                          {getAccessFeatureLabel(lang, feat)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* ── Edit panel ── */}
                {isEditing && (
                  <div className="border-t border-primary/15 px-4 pb-5 pt-4 space-y-5">
                    <div>
                      <FieldLabel htmlFor={`group-name-${group.id}`}>{copy.namePlaceholder}</FieldLabel>
                      <Input
                        id={`group-name-${group.id}`}
                        name="group-name"
                        value={draft.name || ""}
                        onChange={(e) => setEditing((s) => ({ ...s, name: e.target.value }))}
                        className="h-9 bg-white/[0.03] border-white/[0.06]"
                      />
                    </div>

                    <div>
                      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">{common.members}</div>
                      <MemberPicker
                        users={users.map((u) => ({ id: u.id, username: u.username }))}
                        selectedIds={(draft.members as number[]) || []}
                        onToggle={(id) =>
                          setEditing((s) => ({
                            ...s,
                            members: toggleId(((s.members as number[]) || []), id),
                          }))
                        }
                      />
                    </div>

                    <div>
                      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">{copy.policyTitle}</div>
                      <div className="grid gap-2 sm:grid-cols-2">
                        {features.map((feature) => (
                          <PermissionModeField
                            key={feature.value}
                            lang={lang}
                            label={feature.label}
                            mode={draft.permission_modes?.[feature.value] || "inherit"}
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

                    <div className="flex gap-2 pt-2">
                      <Button size="sm" onClick={() => void saveEdit()} disabled={saving}>
                        {saving ? common.saving : common.save}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={cancelEdit} disabled={saving}>
                        {common.cancel}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* ── Create group sidebar ── */}
        {editingId === null ? (
          <div className="xl:sticky xl:top-4 h-fit rounded-xl border border-white/[0.06] bg-white/[0.015]">
            <div className="flex items-center gap-3 border-b border-white/[0.06] px-5 py-4">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-violet-500/15 text-violet-400">
                <FolderPlus className="h-4 w-4" />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-foreground">{copy.createTitle}</h2>
                <p className="text-[11px] text-muted-foreground/60">{lang === "ru" ? "Задайте название, участников и политику" : "Set name, members and policy"}</p>
              </div>
            </div>
            <div className="space-y-4 px-5 py-5">
              <div>
                <FieldLabel htmlFor="create-group-name">{copy.namePlaceholder}</FieldLabel>
                <Input
                  id="create-group-name"
                  name="group-name"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  placeholder={copy.namePlaceholder}
                  className="h-9 bg-white/[0.03] border-white/[0.06]"
                />
              </div>

              <div>
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">{common.members}</div>
                <MemberPicker
                  users={users.map((u) => ({ id: u.id, username: u.username }))}
                  selectedIds={createMembers}
                  onToggle={(id) => setCreateMembers((prev) => toggleId(prev, id))}
                />
              </div>

              <div>
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">{copy.policyTitle}</div>
                <div className="grid gap-2">
                  {features.map((feature) => (
                    <PermissionModeField
                      key={feature.value}
                      lang={lang}
                      label={feature.label}
                      mode={createPModes[feature.value] || "inherit"}
                      onChange={(value) =>
                        setCreatePModes((s) => ({ ...s, [feature.value]: value }))
                      }
                    />
                  ))}
                </div>
              </div>

              <Button className="w-full" onClick={() => void createGroup()} disabled={saving || !createName.trim()}>
                {saving ? copy.creatingAction : copy.createAction}
              </Button>
            </div>
          </div>
        ) : (
          <div className="xl:sticky xl:top-4 h-fit rounded-xl border border-dashed border-white/[0.08] bg-white/[0.01] px-5 py-8 text-center">
            <p className="text-xs text-muted-foreground/50">
              {lang === "ru"
                ? "Заверши редактирование группы, чтобы создать новую."
                : "Finish editing the current group to create a new one."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
