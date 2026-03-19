import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
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
import { useI18n } from "@/lib/i18n";
import {
  ACCESS_UI_TEXT,
  getAccessFeatureLabel,
  localizeAccessFeatures,
} from "@/lib/accessUiText";

const FALLBACK_FEATURES = [
  { value: "servers", label: "Servers" },
  { value: "dashboard", label: "Dashboard" },
  { value: "agents", label: "Agents" },
  { value: "studio", label: "Studio" },
  { value: "settings", label: "Settings" },
  { value: "orchestrator", label: "Orchestrator" },
  { value: "knowledge_base", label: "Knowledge Base" },
];

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
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">{copy.title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{copy.subtitle}</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-3 rounded-lg border border-border bg-card p-4">
          <h2 className="text-sm font-medium text-foreground">{copy.userOverrideTitle}</h2>
          <div className="grid gap-3 md:grid-cols-4">
            <select
              value={userForm.userId}
              onChange={(e) =>
                setUserForm((current) => ({ ...current, userId: Number(e.target.value) }))
              }
              className="rounded-md border border-border bg-secondary px-3 py-2 text-sm"
            >
              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.username}
                </option>
              ))}
            </select>
            <select
              value={userForm.feature}
              onChange={(e) =>
                setUserForm((current) => ({ ...current, feature: e.target.value }))
              }
              className="rounded-md border border-border bg-secondary px-3 py-2 text-sm"
            >
              {features.map((feature) => (
                <option key={feature.value} value={feature.value}>
                  {feature.label}
                </option>
              ))}
            </select>
            <select
              value={userForm.allowed ? "1" : "0"}
              onChange={(e) =>
                setUserForm((current) => ({ ...current, allowed: e.target.value === "1" }))
              }
              className="rounded-md border border-border bg-secondary px-3 py-2 text-sm"
            >
              <option value="1">{common.allow}</option>
              <option value="0">{common.deny}</option>
            </select>
            <Button onClick={() => void createUserPermission()} disabled={!users.length || !features.length}>
              {common.save}
            </Button>
          </div>
        </section>

        <section className="space-y-3 rounded-lg border border-border bg-card p-4">
          <h2 className="text-sm font-medium text-foreground">{copy.groupPolicyTitle}</h2>
          <div className="grid gap-3 md:grid-cols-4">
            <select
              value={groupForm.groupId}
              onChange={(e) =>
                setGroupForm((current) => ({ ...current, groupId: Number(e.target.value) }))
              }
              className="rounded-md border border-border bg-secondary px-3 py-2 text-sm"
            >
              {groups.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.name}
                </option>
              ))}
            </select>
            <select
              value={groupForm.feature}
              onChange={(e) =>
                setGroupForm((current) => ({ ...current, feature: e.target.value }))
              }
              className="rounded-md border border-border bg-secondary px-3 py-2 text-sm"
            >
              {features.map((feature) => (
                <option key={feature.value} value={feature.value}>
                  {feature.label}
                </option>
              ))}
            </select>
            <select
              value={groupForm.allowed ? "1" : "0"}
              onChange={(e) =>
                setGroupForm((current) => ({ ...current, allowed: e.target.value === "1" }))
              }
              className="rounded-md border border-border bg-secondary px-3 py-2 text-sm"
            >
              <option value="1">{common.allow}</option>
              <option value="0">{common.deny}</option>
            </select>
            <Button onClick={() => void createGroupPermission()} disabled={!groups.length || !features.length}>
              {common.save}
            </Button>
          </div>
        </section>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-lg border border-border bg-card">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-sm font-medium text-foreground">{copy.userListTitle}</h2>
          </div>
          <div className="divide-y divide-border">
            {permissions.length ? (
              permissions.map((permission) => (
                <div key={permission.id} className="flex items-center gap-3 px-4 py-3">
                  <div>
                    <div className="font-medium text-foreground">{permission.username}</div>
                    <div className="text-xs text-muted-foreground">
                      {getAccessFeatureLabel(lang, permission.feature, permission.feature_display)} • {permission.allowed ? common.allowed : common.denied}
                    </div>
                  </div>
                  <div className="ml-auto flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void toggleUserPermission(permission.id, permission.allowed)}
                    >
                      {common.toggle}
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => void removeUserPermission(permission.id)}
                    >
                      {common.delete}
                    </Button>
                  </div>
                </div>
              ))
            ) : (
              <div className="px-4 py-5 text-sm text-muted-foreground">{copy.noUserOverrides}</div>
            )}
          </div>
        </section>

        <section className="rounded-lg border border-border bg-card">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-sm font-medium text-foreground">{copy.groupListTitle}</h2>
          </div>
          <div className="divide-y divide-border">
            {groupPermissions.length ? (
              groupPermissions.map((permission) => (
                <div key={permission.id} className="flex items-center gap-3 px-4 py-3">
                  <div>
                    <div className="font-medium text-foreground">{permission.group_name}</div>
                    <div className="text-xs text-muted-foreground">
                      {getAccessFeatureLabel(lang, permission.feature, permission.feature_display)} • {permission.allowed ? common.allowed : common.denied}
                    </div>
                  </div>
                  <div className="ml-auto flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void toggleGroupPermission(permission.id, permission.allowed)}
                    >
                      {common.toggle}
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => void removeGroupPermission(permission.id)}
                    >
                      {common.delete}
                    </Button>
                  </div>
                </div>
              ))
            ) : (
              <div className="px-4 py-5 text-sm text-muted-foreground">{copy.noGroupPolicies}</div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
