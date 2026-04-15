import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Shield, ArrowLeftRight, Trash2, ShieldCheck, ShieldX } from "lucide-react";

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
import { EmptyState } from "@/components/ui/page-shell";
import { useI18n } from "@/lib/i18n";
import {
  ACCESS_UI_TEXT,
  getAccessFeatureLabel,
  localizeAccessFeatures,
} from "@/lib/accessUiText";

const SELECT_CLASS =
  "h-9 w-full rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 text-sm text-foreground outline-none ring-0 transition-all focus:border-primary/40 focus:ring-1 focus:ring-primary/30";

const FALLBACK_FEATURES = ACCESS_FEATURE_OPTIONS;

function FieldLabel({ htmlFor, children }: { htmlFor?: string; children: string }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
      {children}
    </label>
  );
}

/* ── Reusable rule row ── */
function RuleRow({
  name,
  feature,
  allowed,
  onToggle,
  onDelete,
  allowedLabel,
  deniedLabel,
  toggleTitle,
  deleteTitle,
}: {
  name: string;
  feature: string;
  allowed: boolean;
  onToggle: () => void;
  onDelete: () => void;
  allowedLabel: string;
  deniedLabel: string;
  toggleTitle: string;
  deleteTitle: string;
}) {
  return (
    <div className="group/rule flex items-center gap-3 rounded-lg border border-white/[0.04] bg-white/[0.015] px-4 py-3 transition-all hover:bg-white/[0.03] hover:border-white/[0.08]">
      <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${allowed ? "bg-emerald-500/10" : "bg-red-500/10"}`}>
        {allowed
          ? <ShieldCheck className="h-4 w-4 text-emerald-400" />
          : <ShieldX className="h-4 w-4 text-red-400/80" />
        }
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-foreground">{name}</span>
          <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
            allowed ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400/80"
          }`}>
            {allowed ? allowedLabel : deniedLabel}
          </span>
        </div>
        <div className="mt-0.5 text-xs text-muted-foreground/60">{feature}</div>
      </div>
      <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover/rule:opacity-100">
        <button
          onClick={onToggle}
          className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground/50 transition-colors hover:bg-white/[0.06] hover:text-foreground"
          title={toggleTitle}
        >
          <ArrowLeftRight className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={onDelete}
          className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground/50 transition-colors hover:bg-red-500/10 hover:text-red-400"
          title={deleteTitle}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
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
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }
  if (error) {
    return <div className="p-6 text-sm text-destructive">{copy.error}</div>;
  }

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
          <Shield className="h-4 w-4 text-muted-foreground/50" />
          <span className="text-sm font-medium text-foreground">{permissions.length}</span>
          <span className="text-xs text-muted-foreground/60">{lang === "ru" ? "пользовательских" : "user rules"}</span>
        </div>
        <div className="h-4 w-px bg-white/[0.06]" />
        <div className="flex items-center gap-1.5">
          <div className="h-2 w-2 rounded-full bg-amber-400/80" />
          <span className="text-sm font-medium text-foreground">{groupPermissions.length}</span>
          <span className="text-xs text-muted-foreground/60">{lang === "ru" ? "групповых" : "group rules"}</span>
        </div>
      </div>

      {/* ── Creation forms — side by side ── */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* User override creator */}
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.015]">
          <div className="flex items-center gap-3 border-b border-white/[0.06] px-5 py-3.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/12 text-blue-400">
              <Shield className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-foreground">{copy.userOverrideTitle}</h2>
              <p className="text-[11px] text-muted-foreground/60">{lang === "ru" ? "Точечное правило для пользователя" : "Override rule for a user"}</p>
            </div>
          </div>
          <div className="grid gap-3 px-5 py-4 sm:grid-cols-[1fr_1fr_1fr_auto]">
            <div>
              <FieldLabel htmlFor="permission-user-select">{lang === "ru" ? "Пользователь" : "User"}</FieldLabel>
              <select id="permission-user-select" value={userForm.userId} onChange={(e) => setUserForm((c) => ({ ...c, userId: Number(e.target.value) }))} className={SELECT_CLASS}>
                {users.map((u) => (<option key={u.id} value={u.id}>{u.username}</option>))}
              </select>
            </div>
            <div>
              <FieldLabel htmlFor="permission-feature-select">{lang === "ru" ? "Фича" : "Feature"}</FieldLabel>
              <select id="permission-feature-select" value={userForm.feature} onChange={(e) => setUserForm((c) => ({ ...c, feature: e.target.value }))} className={SELECT_CLASS}>
                {features.map((f) => (<option key={f.value} value={f.value}>{f.label}</option>))}
              </select>
            </div>
            <div>
              <FieldLabel htmlFor="permission-rule-select">{lang === "ru" ? "Правило" : "Rule"}</FieldLabel>
              <select id="permission-rule-select" value={userForm.allowed ? "1" : "0"} onChange={(e) => setUserForm((c) => ({ ...c, allowed: e.target.value === "1" }))} className={SELECT_CLASS}>
                <option value="1">{common.allow}</option>
                <option value="0">{common.deny}</option>
              </select>
            </div>
            <div className="flex items-end">
              <Button size="sm" onClick={() => void createUserPermission()} disabled={!users.length || !features.length}>
                {common.save}
              </Button>
            </div>
          </div>
        </div>

        {/* Group policy creator */}
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.015]">
          <div className="flex items-center gap-3 border-b border-white/[0.06] px-5 py-3.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/12 text-amber-400">
              <Shield className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-foreground">{copy.groupPolicyTitle}</h2>
              <p className="text-[11px] text-muted-foreground/60">{lang === "ru" ? "Политика для всей группы" : "Policy for entire group"}</p>
            </div>
          </div>
          <div className="grid gap-3 px-5 py-4 sm:grid-cols-[1fr_1fr_1fr_auto]">
            <div>
              <FieldLabel htmlFor="group-permission-group-select">{lang === "ru" ? "Группа" : "Group"}</FieldLabel>
              <select id="group-permission-group-select" value={groupForm.groupId} onChange={(e) => setGroupForm((c) => ({ ...c, groupId: Number(e.target.value) }))} className={SELECT_CLASS}>
                {groups.map((g) => (<option key={g.id} value={g.id}>{g.name}</option>))}
              </select>
            </div>
            <div>
              <FieldLabel htmlFor="group-permission-feature-select">{lang === "ru" ? "Фича" : "Feature"}</FieldLabel>
              <select id="group-permission-feature-select" value={groupForm.feature} onChange={(e) => setGroupForm((c) => ({ ...c, feature: e.target.value }))} className={SELECT_CLASS}>
                {features.map((f) => (<option key={f.value} value={f.value}>{f.label}</option>))}
              </select>
            </div>
            <div>
              <FieldLabel htmlFor="group-permission-rule-select">{lang === "ru" ? "Правило" : "Rule"}</FieldLabel>
              <select id="group-permission-rule-select" value={groupForm.allowed ? "1" : "0"} onChange={(e) => setGroupForm((c) => ({ ...c, allowed: e.target.value === "1" }))} className={SELECT_CLASS}>
                <option value="1">{common.allow}</option>
                <option value="0">{common.deny}</option>
              </select>
            </div>
            <div className="flex items-end">
              <Button size="sm" onClick={() => void createGroupPermission()} disabled={!groups.length || !features.length}>
                {common.save}
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Rule lists — side by side ── */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* User rules */}
        <div>
          <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">{copy.userListTitle}</h3>
          <div className="space-y-2">
            {permissions.length ? (
              permissions.map((p) => (
                <RuleRow
                  key={p.id}
                  name={p.username}
                  feature={getAccessFeatureLabel(lang, p.feature, p.feature_display)}
                  allowed={p.allowed}
                  onToggle={() => void toggleUserPermission(p.id, p.allowed)}
                  onDelete={() => void removeUserPermission(p.id)}
                  allowedLabel={common.allowed}
                  deniedLabel={common.denied}
                  toggleTitle={common.toggle}
                  deleteTitle={common.delete}
                />
              ))
            ) : (
              <EmptyState
                icon={<Shield className="h-5 w-5" />}
                title={copy.noUserOverrides}
                description={lang === "ru" ? "Создайте правило выше." : "Create a rule above."}
              />
            )}
          </div>
        </div>

        {/* Group rules */}
        <div>
          <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">{copy.groupListTitle}</h3>
          <div className="space-y-2">
            {groupPermissions.length ? (
              groupPermissions.map((p) => (
                <RuleRow
                  key={p.id}
                  name={p.group_name}
                  feature={getAccessFeatureLabel(lang, p.feature, p.feature_display)}
                  allowed={p.allowed}
                  onToggle={() => void toggleGroupPermission(p.id, p.allowed)}
                  onDelete={() => void removeGroupPermission(p.id)}
                  allowedLabel={common.allowed}
                  deniedLabel={common.denied}
                  toggleTitle={common.toggle}
                  deleteTitle={common.delete}
                />
              ))
            ) : (
              <EmptyState
                icon={<Shield className="h-5 w-5" />}
                title={copy.noGroupPolicies}
                description={lang === "ru" ? "Задайте политику для группы выше." : "Set a group policy above."}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
