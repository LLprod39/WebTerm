import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ACCESS_FEATURE_OPTIONS,
  deleteAccessGroupPermission,
  deleteAccessPermission,
  fetchAccessGroupPermissions,
  fetchAccessGroups,
  fetchAccessPermissions,
  fetchAccessUsers,
  updateAccessGroupPermission,
  updateAccessPermission,
  upsertAccessGroupPermission,
  upsertAccessPermission,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { EmptyState, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { SettingsWorkspace } from "@/components/settings/SettingsWorkspace";
import { useI18n } from "@/lib/i18n";
import {
  ACCESS_UI_TEXT,
  getAccessFeatureLabel,
  localizeAccessFeatures,
} from "@/lib/accessUiText";

const SELECT_CLASS = "h-10 rounded-xl border border-border bg-background/80 px-3 text-sm text-foreground";

const FALLBACK_FEATURES = ACCESS_FEATURE_OPTIONS;

function FieldLabel({ htmlFor, children }: { htmlFor?: string; children: string }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-[11px] font-medium text-muted-foreground">
      {children}
    </label>
  );
}

export default function SettingsPermissionsPage() {
  const { lang } = useI18n();
  const copy = ACCESS_UI_TEXT[lang].permissions;
  const common = ACCESS_UI_TEXT[lang].common;
  const queryClient = useQueryClient();
  const [userForm, setUserForm] = useState({
    userId: 0,
    feature: "",
    allowed: true,
  });
  const [groupForm, setGroupForm] = useState({
    groupId: 0,
    feature: "",
    allowed: true,
  });

  const { data: permsData, isLoading, error } = useQuery({
    queryKey: ["access", "permissions"],
    queryFn: fetchAccessPermissions,
  });
  const { data: groupPermsData } = useQuery({
    queryKey: ["access", "group-permissions"],
    queryFn: fetchAccessGroupPermissions,
  });
  const { data: usersData } = useQuery({
    queryKey: ["access", "users"],
    queryFn: fetchAccessUsers,
  });
  const { data: groupsData } = useQuery({
    queryKey: ["access", "groups"],
    queryFn: fetchAccessGroups,
  });

  const permissions = useMemo(() => permsData?.permissions ?? [], [permsData?.permissions]);
  const groupPermissions = useMemo(
    () => groupPermsData?.permissions ?? permsData?.group_permissions ?? [],
    [groupPermsData?.permissions, permsData?.group_permissions],
  );
  const features = useMemo(
    () => localizeAccessFeatures(lang, permsData?.features ?? groupPermsData?.features ?? FALLBACK_FEATURES),
    [groupPermsData?.features, lang, permsData?.features],
  );
  const users = useMemo(() => usersData?.users ?? [], [usersData?.users]);
  const groups = useMemo(() => groupsData?.groups ?? [], [groupsData?.groups]);

  useEffect(() => {
    if (!users.length || !features.length) return;
    setUserForm((current) => ({
      userId: current.userId || users[0].id,
      feature: current.feature || features[0].value,
      allowed: current.allowed,
    }));
  }, [features, users]);

  useEffect(() => {
    if (!groups.length || !features.length) return;
    setGroupForm((current) => ({
      groupId: current.groupId || groups[0].id,
      feature: current.feature || features[0].value,
      allowed: current.allowed,
    }));
  }, [features, groups]);

  const reload = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["access", "permissions"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "group-permissions"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "users"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "groups"] }),
    ]);
  };

  const createUserPermission = async () => {
    if (!userForm.userId || !userForm.feature) return;
    await upsertAccessPermission({
      user_id: userForm.userId,
      feature: userForm.feature,
      allowed: userForm.allowed,
    });
    await reload();
  };

  const createGroupPermission = async () => {
    if (!groupForm.groupId || !groupForm.feature) return;
    await upsertAccessGroupPermission({
      group_id: groupForm.groupId,
      feature: groupForm.feature,
      allowed: groupForm.allowed,
    });
    await reload();
  };

  const toggleUserPermission = async (permId: number, allowed: boolean) => {
    await updateAccessPermission(permId, !allowed);
    await reload();
  };

  const toggleGroupPermission = async (permId: number, allowed: boolean) => {
    await updateAccessGroupPermission(permId, !allowed);
    await reload();
  };

  const removeUserPermission = async (permId: number) => {
    if (!confirm(copy.deleteUserPermission)) return;
    await deleteAccessPermission(permId);
    await reload();
  };

  const removeGroupPermission = async (permId: number) => {
    if (!confirm(copy.deleteGroupPermission)) return;
    await deleteAccessGroupPermission(permId);
    await reload();
  };

  if (isLoading) {
    return <div className="p-6 text-sm text-muted-foreground">{copy.loading}</div>;
  }
  if (error) {
    return <div className="p-6 text-sm text-destructive">{copy.error}</div>;
  }

  return (
    <SettingsWorkspace
      title={copy.title}
      description={copy.subtitle}
      asideHint="Точечные правила лучше использовать как исключения. Базовый доступ держи в профилях и группах, чтобы схема прав оставалась читаемой."
      actions={
        <>
          <StatusBadge label={`User Rules: ${permissions.length}`} dot={false} />
          <StatusBadge label={`Group Rules: ${groupPermissions.length}`} tone="info" dot={false} />
          <StatusBadge label={`Features: ${features.length}`} dot={false} />
        </>
      }
    >
      <div className="workspace-subtle rounded-xl px-4 py-3 text-sm leading-6 text-muted-foreground">
        Здесь удобно хранить только исключения: разрешить или запретить конкретную фичу отдельно от основного профиля доступа.
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        <SectionCard title={copy.userOverrideTitle} description="Точечное правило перекрывает стандартный доступ пользователя.">
          <div className="grid gap-3 md:grid-cols-4">
            <div>
              <FieldLabel htmlFor="permission-user-select">{lang === "ru" ? "Пользователь" : "User"}</FieldLabel>
              <select
                id="permission-user-select"
                value={userForm.userId}
                onChange={(e) => setUserForm((current) => ({ ...current, userId: Number(e.target.value) }))}
                className={SELECT_CLASS}
              >
                {users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.username}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel htmlFor="permission-feature-select">{lang === "ru" ? "Фича" : "Feature"}</FieldLabel>
              <select
                id="permission-feature-select"
                value={userForm.feature}
                onChange={(e) => setUserForm((current) => ({ ...current, feature: e.target.value }))}
                className={SELECT_CLASS}
              >
                {features.map((feature) => (
                  <option key={feature.value} value={feature.value}>
                    {feature.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel htmlFor="permission-rule-select">{lang === "ru" ? "Правило" : "Rule"}</FieldLabel>
              <select
                id="permission-rule-select"
                value={userForm.allowed ? "1" : "0"}
                onChange={(e) => setUserForm((current) => ({ ...current, allowed: e.target.value === "1" }))}
                className={SELECT_CLASS}
              >
                <option value="1">{common.allow}</option>
                <option value="0">{common.deny}</option>
              </select>
            </div>
            <div className="flex items-end">
              <Button className="w-full" onClick={() => void createUserPermission()} disabled={!users.length || !features.length}>
                {common.save}
              </Button>
            </div>
          </div>
        </SectionCard>

        <SectionCard title={copy.groupPolicyTitle} description="Групповая политика применяется для всех участников группы.">
          <div className="grid gap-3 md:grid-cols-4">
            <div>
              <FieldLabel htmlFor="group-permission-group-select">{lang === "ru" ? "Группа" : "Group"}</FieldLabel>
              <select
                id="group-permission-group-select"
                value={groupForm.groupId}
                onChange={(e) => setGroupForm((current) => ({ ...current, groupId: Number(e.target.value) }))}
                className={SELECT_CLASS}
              >
                {groups.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel htmlFor="group-permission-feature-select">{lang === "ru" ? "Фича" : "Feature"}</FieldLabel>
              <select
                id="group-permission-feature-select"
                value={groupForm.feature}
                onChange={(e) => setGroupForm((current) => ({ ...current, feature: e.target.value }))}
                className={SELECT_CLASS}
              >
                {features.map((feature) => (
                  <option key={feature.value} value={feature.value}>
                    {feature.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel htmlFor="group-permission-rule-select">{lang === "ru" ? "Правило" : "Rule"}</FieldLabel>
              <select
                id="group-permission-rule-select"
                value={groupForm.allowed ? "1" : "0"}
                onChange={(e) => setGroupForm((current) => ({ ...current, allowed: e.target.value === "1" }))}
                className={SELECT_CLASS}
              >
                <option value="1">{common.allow}</option>
                <option value="0">{common.deny}</option>
              </select>
            </div>
            <div className="flex items-end">
              <Button className="w-full" onClick={() => void createGroupPermission()} disabled={!groups.length || !features.length}>
                {common.save}
              </Button>
            </div>
          </div>
        </SectionCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <SectionCard title={copy.userListTitle} description="Список точечных пользовательских правил.">
          <div className="space-y-3">
            {permissions.length ? (
              permissions.map((permission) => (
                <div key={permission.id} className="flex flex-col gap-3 rounded-2xl border border-border/70 bg-background/50 px-4 py-3 md:flex-row md:items-center">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="font-medium text-foreground">{permission.username}</div>
                      <StatusBadge
                        label={permission.allowed ? common.allowed : common.denied}
                        tone={permission.allowed ? "success" : "danger"}
                      />
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {getAccessFeatureLabel(lang, permission.feature, permission.feature_display)}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => void toggleUserPermission(permission.id, permission.allowed)}>
                      {common.toggle}
                    </Button>
                    <Button size="sm" variant="destructive" onClick={() => void removeUserPermission(permission.id)}>
                      {common.delete}
                    </Button>
                  </div>
                </div>
              ))
            ) : (
              <EmptyState title={copy.noUserOverrides} description="Когда создадите правило, оно появится здесь." />
            )}
          </div>
        </SectionCard>

        <SectionCard title={copy.groupListTitle} description="Список явных групповых политик.">
          <div className="space-y-3">
            {groupPermissions.length ? (
              groupPermissions.map((permission) => (
                <div key={permission.id} className="flex flex-col gap-3 rounded-2xl border border-border/70 bg-background/50 px-4 py-3 md:flex-row md:items-center">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="font-medium text-foreground">{permission.group_name}</div>
                      <StatusBadge
                        label={permission.allowed ? common.allowed : common.denied}
                        tone={permission.allowed ? "success" : "danger"}
                      />
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {getAccessFeatureLabel(lang, permission.feature, permission.feature_display)}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => void toggleGroupPermission(permission.id, permission.allowed)}>
                      {common.toggle}
                    </Button>
                    <Button size="sm" variant="destructive" onClick={() => void removeGroupPermission(permission.id)}>
                      {common.delete}
                    </Button>
                  </div>
                </div>
              ))
            ) : (
              <EmptyState title={copy.noGroupPolicies} description="Когда зададите политику для группы, она появится здесь." />
            )}
          </div>
        </SectionCard>
      </div>
    </SettingsWorkspace>
  );
}
