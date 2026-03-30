import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

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
import { EmptyState, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { SettingsWorkspace } from "@/components/settings/SettingsWorkspace";
import { useI18n } from "@/lib/i18n";
import {
  ACCESS_UI_TEXT,
  formatAccessText,
  getAccessFeatureLabel,
  localizeAccessFeatures,
} from "@/lib/accessUiText";

type PermissionMode = "inherit" | "allow" | "deny";
const SELECT_CLASS = "h-10 rounded-xl border border-border bg-background/80 px-3 text-sm text-foreground";

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
    <label htmlFor={htmlFor} className="mb-1.5 block text-[11px] font-medium text-muted-foreground">
      {children}
    </label>
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
    <div className="flex flex-wrap gap-2">
      {users.map((user) => {
        const active = selectedIds.includes(user.id);
        return (
          <button
            key={user.id}
            type="button"
            onClick={() => onToggle(user.id)}
            className={`rounded-xl border px-3 py-1.5 text-sm transition-colors ${
              active
                ? "border-primary bg-primary/10 text-primary"
                : "border-border bg-background/60 text-muted-foreground hover:text-foreground"
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
    <div className="rounded-2xl border border-border/70 bg-background/50 p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-medium text-foreground">{label}</div>
        <select
          value={mode}
          onChange={(e) => onChange(e.target.value as PermissionMode)}
          className={SELECT_CLASS}
          aria-label={`${label} mode`}
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
  const directoryTitle = lang === "ru" ? "Каталог групп" : "Group directory";
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

  const membersCount = groups.reduce((sum, group) => sum + group.member_count, 0);

  return (
    <SettingsWorkspace
      title={copy.title}
      description={copy.subtitle}
      asideHint="Группа удобна как базовый контейнер доступа: сначала состав, затем общая политика. Индивидуальные исключения лучше не смешивать с групповой моделью."
      actions={
        <>
          <StatusBadge label={`Groups: ${groups.length}`} dot={false} />
          <StatusBadge label={`${common.members}: ${membersCount}`} tone="info" dot={false} />
          <StatusBadge label={`Policies: ${features.length}`} dot={false} />
        </>
      }
    >
      <div className="workspace-subtle rounded-xl px-4 py-3 text-sm leading-6 text-muted-foreground">
        Держи группу как понятную роль команды: название, участники, потом набор общих правил. Чем меньше точечных исключений, тем проще поддержка.
      </div>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <SectionCard title={directoryTitle} description="Группы, участники и явные политики доступа.">
          <div className="space-y-4">
            {groups.length === 0 ? (
              <EmptyState
                title="Групп пока нет"
                description="Создайте первую группу справа и сразу назначьте ей участников и доступ."
              />
            ) : null}

            {groups.map((group) => {
          const isEditing = editingId === group.id;
          const draft = editing as {
            name?: string;
            members?: number[];
            permission_modes?: Record<string, PermissionMode>;
          };

          return (
            <div key={group.id} className="rounded-2xl border border-border/80 bg-background/50 p-4">
              {!isEditing ? (
                <div className="space-y-3">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="text-base font-semibold text-foreground">{group.name}</div>
                        <StatusBadge label={`${group.member_count} ${common.members.toLowerCase()}`} tone="info" />
                      </div>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        <div className="workspace-subtle rounded-xl px-3 py-3">
                          <div className="text-[11px] font-medium text-muted-foreground">{common.members}</div>
                          <div className="mt-1 text-sm text-foreground">
                            {group.members?.length ? group.members.map((member) => member.username).join(", ") : common.none}
                          </div>
                        </div>
                        <div className="workspace-subtle rounded-xl px-3 py-3">
                          <div className="text-[11px] font-medium text-muted-foreground">{copy.explicitPolicy}</div>
                          <div className="mt-1 text-sm text-foreground">
                            {Object.entries(group.explicit_permissions || {})
                              .map(([feature, allowed]) => `${getAccessFeatureLabel(lang, feature)}: ${allowed ? common.allowed.toLowerCase() : common.denied.toLowerCase()}`)
                              .join(", ") || common.none}
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" onClick={() => startEdit(group)}>
                        {copy.editAction}
                      </Button>
                      <Button size="sm" variant="destructive" onClick={() => void removeGroup(group)}>
                        {common.delete}
                      </Button>
                    </div>
                    </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <FieldLabel htmlFor={`group-name-${group.id}`}>{copy.namePlaceholder}</FieldLabel>
                    <Input
                      id={`group-name-${group.id}`}
                      name="group-name"
                      value={draft.name || ""}
                      onChange={(e) => setEditing((state) => ({ ...state, name: e.target.value }))}
                    />
                  </div>

                  <div className="space-y-2">
                    <div className="text-[11px] font-medium text-muted-foreground">{common.members}</div>
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
                    <div className="text-sm font-medium text-foreground">{copy.policyTitle}</div>
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
          </div>
        </SectionCard>

        {editingId === null ? (
          <SectionCard
            title={copy.createTitle}
            description="Создайте группу и задайте её состав и правила доступа."
            className="xl:sticky xl:top-4"
            bodyClassName="space-y-4"
          >
            <div>
              <FieldLabel htmlFor="create-group-name">{copy.namePlaceholder}</FieldLabel>
              <Input
                id="create-group-name"
                name="group-name"
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder={copy.namePlaceholder}
              />
            </div>

            <div>
              <div className="mb-1.5 text-[11px] font-medium text-muted-foreground">{common.members}</div>
              <MemberPicker
                users={users.map((user) => ({ id: user.id, username: user.username }))}
                selectedIds={createMembers}
                onToggle={(id) => setCreateMembers((prev) => toggleId(prev, id))}
              />
            </div>

            <div className="space-y-3">
              <div className="text-sm font-medium text-foreground">{copy.policyTitle}</div>
              <div className="grid gap-3">
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
          </SectionCard>
        ) : (
          <SectionCard
            title={lang === "ru" ? "Создание временно скрыто" : "Creation temporarily hidden"}
            description={
              lang === "ru"
                ? "Заверши редактирование текущей группы, чтобы не смешивать правку и создание в одном экране."
                : "Finish editing the current group before creating a new one."
            }
            className="xl:sticky xl:top-4"
          >
            <div className="text-sm leading-6 text-muted-foreground">
              {lang === "ru"
                ? "Это уменьшает случайные ошибки, когда в форме одновременно открыт draft новой группы и режим редактирования существующей."
                : "This keeps the page focused and avoids mixing a create draft with an active edit state."}
            </div>
          </SectionCard>
        )}
      </div>
    </SettingsWorkspace>
  );
}
