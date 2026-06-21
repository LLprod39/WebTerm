import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftRight, Plus, Search, Shield, ShieldCheck, ShieldX, Trash2, Users } from "lucide-react";

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
  type AccessGroup,
  type AccessGroupPermission,
  type AccessPermission,
  type AccessUser,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, StatusBadge } from "@/components/ui/page-shell";
import { DeleteDialog } from "@/components/system/ConfirmDialog";
import { useI18n } from "@/lib/i18n";
import { notify } from "@/lib/notify";
import {
  ACCESS_UI_TEXT,
  getAccessFeatureLabel,
  getAccessProfileLabel,
  localizeAccessFeatures,
} from "@/lib/accessUiText";
import { cn } from "@/lib/utils";

type SubjectKind = "user" | "group";
type SubjectFilter = "all" | SubjectKind;
type ExceptionDraft = {
  kind: SubjectKind;
  subjectId: number;
  feature: string;
  allowed: boolean;
};

type DeleteTarget = {
  kind: SubjectKind;
  id: number;
  title: string;
  description: string;
};

type MatrixCell = {
  feature: string;
  allowed: boolean | null;
  explicit: boolean;
  source: string;
};

type MatrixRow = {
  key: string;
  kind: SubjectKind;
  id: number;
  name: string;
  detail: string;
  cells: MatrixCell[];
};

const FALLBACK_FEATURES = ACCESS_FEATURE_OPTIONS;

function keyedPermissionMap<T extends { feature: string }>(items: T[], idSelector: (item: T) => number) {
  return new Map(items.map((item) => [`${idSelector(item)}:${item.feature}`, item] as const));
}

function PermissionPill({
  allowed,
  explicit,
  source,
}: {
  allowed: boolean | null;
  explicit: boolean;
  source: string;
}) {
  const tone =
    allowed === true
      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
      : allowed === false
        ? "border-red-500/30 bg-red-500/10 text-red-300"
        : "border-border/60 bg-secondary/20 text-muted-foreground";
  return (
    <span className={cn("inline-flex min-w-24 flex-col rounded-md border px-2 py-1 text-left text-xs leading-4", tone)}>
      <span className="font-semibold">
        {allowed === true ? "Allow" : allowed === false ? "Deny" : "Inherit"}
      </span>
      <span className="truncate opacity-80">{explicit ? "explicit" : source}</span>
    </span>
  );
}

function FilterButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-active={active}
      className="min-h-10 rounded-lg border border-border/70 px-3 text-sm text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground data-[active=true]:border-primary/40 data-[active=true]:bg-primary/10 data-[active=true]:text-primary"
    >
      {children}
    </button>
  );
}

function SubjectPicker({
  lang,
  kind,
  users,
  groups,
  value,
  search,
  onSearchChange,
  onChange,
}: {
  lang: "en" | "ru";
  kind: SubjectKind;
  users: AccessUser[];
  groups: AccessGroup[];
  value: number;
  search: string;
  onSearchChange: (value: string) => void;
  onChange: (id: number) => void;
}) {
  const subjects =
    kind === "user"
      ? users.map((user) => ({ id: user.id, name: user.username, detail: user.email || ACCESS_UI_TEXT[lang].common.noEmail }))
      : groups.map((group) => ({ id: group.id, name: group.name, detail: `${group.member_count} ${ACCESS_UI_TEXT[lang].common.members.toLowerCase()}` }));
  const filtered = subjects.filter((subject) =>
    [subject.name, subject.detail].join(" ").toLowerCase().includes(search.trim().toLowerCase()),
  );
  return (
    <div>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder={lang === "ru" ? "Поиск субъекта" : "Search subject"}
          className="h-10 pl-9"
        />
      </div>
      <div className="mt-3 max-h-56 overflow-auto rounded-lg border border-border/70">
        {filtered.length ? (
          filtered.map((subject) => {
            const active = value === subject.id;
            return (
              <button
                key={subject.id}
                type="button"
                onClick={() => onChange(subject.id)}
                className={cn(
                  "flex min-h-12 w-full items-center justify-between gap-3 border-b border-border/50 px-3 py-2 text-left last:border-b-0 hover:bg-secondary/30",
                  active && "bg-primary/10",
                )}
              >
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-foreground">{subject.name}</span>
                  <span className="block truncate text-sm text-muted-foreground">{subject.detail}</span>
                </span>
                {active ? <StatusBadge label={ACCESS_UI_TEXT[lang].common.allowed} tone="info" dot={false} /> : null}
              </button>
            );
          })
        ) : (
          <div className="px-3 py-8 text-center text-sm text-muted-foreground">
            {lang === "ru" ? "Субъекты не найдены." : "No subjects found."}
          </div>
        )}
      </div>
    </div>
  );
}

function ExceptionSheet({
  lang,
  open,
  draft,
  users,
  groups,
  features,
  saving,
  subjectSearch,
  onSubjectSearchChange,
  onDraftChange,
  onOpenChange,
  onSave,
}: {
  lang: "en" | "ru";
  open: boolean;
  draft: ExceptionDraft;
  users: AccessUser[];
  groups: AccessGroup[];
  features: Array<{ value: string; label: string }>;
  saving: boolean;
  subjectSearch: string;
  onSubjectSearchChange: (value: string) => void;
  onDraftChange: (draft: ExceptionDraft) => void;
  onOpenChange: (open: boolean) => void;
  onSave: () => void | Promise<void>;
}) {
  const copy = ACCESS_UI_TEXT[lang].permissions;
  const common = ACCESS_UI_TEXT[lang].common;
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-[calc(100vw-1rem)] max-w-[680px] flex-col p-0 sm:w-[680px] sm:max-w-[680px]">
        <SheetHeader className="border-b border-border/70 px-5 py-4 pr-12 text-left">
          <SheetTitle className="text-lg">
            {draft.kind === "user" ? copy.userOverrideTitle : copy.groupPolicyTitle}
          </SheetTitle>
          <SheetDescription>
            {lang === "ru"
              ? "Создайте или обновите точечное исключение. Матрица сразу показывает, что оно перекрывает."
              : "Create or update an explicit exception. The matrix shows what it overrides."}
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 space-y-6 overflow-auto px-5 py-5">
          <section>
            <div className="mb-2 text-sm font-medium text-foreground">{lang === "ru" ? "Субъект" : "Subject"}</div>
            <div className="grid grid-cols-2 gap-2">
              <FilterButton
                active={draft.kind === "user"}
                onClick={() =>
                  onDraftChange({
                    ...draft,
                    kind: "user",
                    subjectId: users[0]?.id || 0,
                  })
                }
              >
                {lang === "ru" ? "Пользователь" : "User"}
              </FilterButton>
              <FilterButton
                active={draft.kind === "group"}
                onClick={() =>
                  onDraftChange({
                    ...draft,
                    kind: "group",
                    subjectId: groups[0]?.id || 0,
                  })
                }
              >
                {lang === "ru" ? "Группа" : "Group"}
              </FilterButton>
            </div>
            <div className="mt-3">
              <SubjectPicker
                lang={lang}
                kind={draft.kind}
                users={users}
                groups={groups}
                value={draft.subjectId}
                search={subjectSearch}
                onSearchChange={onSubjectSearchChange}
                onChange={(subjectId) => onDraftChange({ ...draft, subjectId })}
              />
            </div>
          </section>

          <section>
            <div className="mb-2 text-sm font-medium text-foreground">{lang === "ru" ? "Модуль" : "Feature"}</div>
            <div className="grid gap-2 sm:grid-cols-2">
              {features.map((feature) => (
                <button
                  key={feature.value}
                  type="button"
                  onClick={() => onDraftChange({ ...draft, feature: feature.value })}
                  data-active={draft.feature === feature.value}
                  className="min-h-11 rounded-lg border border-border/70 px-3 text-left text-sm text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground data-[active=true]:border-primary/40 data-[active=true]:bg-primary/10 data-[active=true]:text-primary"
                >
                  {feature.label}
                </button>
              ))}
            </div>
          </section>

          <section>
            <div className="mb-2 text-sm font-medium text-foreground">{lang === "ru" ? "Правило" : "Rule"}</div>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => onDraftChange({ ...draft, allowed: true })}
                data-active={draft.allowed}
                className="min-h-11 rounded-lg border border-border/70 px-3 text-sm text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground data-[active=true]:border-emerald-500/40 data-[active=true]:bg-emerald-500/10 data-[active=true]:text-emerald-300"
              >
                {common.allow}
              </button>
              <button
                type="button"
                onClick={() => onDraftChange({ ...draft, allowed: false })}
                data-active={!draft.allowed}
                className="min-h-11 rounded-lg border border-border/70 px-3 text-sm text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground data-[active=true]:border-red-500/40 data-[active=true]:bg-red-500/10 data-[active=true]:text-red-300"
              >
                {common.deny}
              </button>
            </div>
          </section>
        </div>

        <SheetFooter className="border-t border-border/70 px-5 py-4">
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}>
            {common.cancel}
          </Button>
          <Button onClick={() => void onSave()} disabled={saving || !draft.subjectId || !draft.feature}>
            {saving ? common.saving : common.save}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function ExplicitRuleRows({
  lang,
  userPermissions,
  groupPermissions,
  onToggleUser,
  onToggleGroup,
  onDelete,
}: {
  lang: "en" | "ru";
  userPermissions: AccessPermission[];
  groupPermissions: AccessGroupPermission[];
  onToggleUser: (permission: AccessPermission) => void;
  onToggleGroup: (permission: AccessGroupPermission) => void;
  onDelete: (target: DeleteTarget) => void;
}) {
  const copy = ACCESS_UI_TEXT[lang].permissions;
  const common = ACCESS_UI_TEXT[lang].common;
  const rows = [
    ...userPermissions.map((permission) => ({ kind: "user" as const, permission })),
    ...groupPermissions.map((permission) => ({ kind: "group" as const, permission })),
  ];

  if (!rows.length) {
    return (
      <EmptyState
        icon={<Shield className="h-5 w-5" />}
        title={lang === "ru" ? "Исключений нет" : "No explicit exceptions"}
        description={lang === "ru" ? "Добавьте исключение через кнопку сверху." : "Add an exception from the action above."}
      />
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{lang === "ru" ? "Субъект" : "Subject"}</TableHead>
          <TableHead>{lang === "ru" ? "Модуль" : "Feature"}</TableHead>
          <TableHead>{lang === "ru" ? "Правило" : "Rule"}</TableHead>
          <TableHead className="w-28 text-right">{lang === "ru" ? "Действия" : "Actions"}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => {
          const permission = row.permission;
          const isUser = row.kind === "user";
          const subjectName = isUser ? (permission as AccessPermission).username : (permission as AccessGroupPermission).group_name;
          const featureLabel = getAccessFeatureLabel(lang, permission.feature, permission.feature_display);
          return (
            <TableRow key={`${row.kind}-${permission.id}`}>
              <TableCell>
                <div className="flex items-center gap-2">
                  {isUser ? <Users className="h-4 w-4 text-muted-foreground" /> : <Shield className="h-4 w-4 text-muted-foreground" />}
                  <div>
                    <div className="font-medium text-foreground">{subjectName}</div>
                    <div className="text-sm text-muted-foreground">{isUser ? copy.userOverrideTitle : copy.groupPolicyTitle}</div>
                  </div>
                </div>
              </TableCell>
              <TableCell className="font-medium text-foreground">{featureLabel}</TableCell>
              <TableCell>
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium",
                    permission.allowed
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                      : "border-red-500/30 bg-red-500/10 text-red-300",
                  )}
                >
                  {permission.allowed ? <ShieldCheck className="h-3.5 w-3.5" /> : <ShieldX className="h-3.5 w-3.5" />}
                  {permission.allowed ? common.allowed : common.denied}
                </span>
              </TableCell>
              <TableCell>
                <div className="flex justify-end gap-1">
                  <button
                    type="button"
                    onClick={() => (isUser ? onToggleUser(permission as AccessPermission) : onToggleGroup(permission as AccessGroupPermission))}
                    className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                    aria-label={common.toggle}
                    title={common.toggle}
                  >
                    <ArrowLeftRight className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      onDelete({
                        kind: row.kind,
                        id: permission.id,
                        title: isUser ? copy.deleteUserPermission : copy.deleteGroupPermission,
                        description: isUser
                          ? lang === "ru"
                            ? `Личное правило ${subjectName}: ${featureLabel} будет удалено. Итоговый доступ вернётся к профилю и группам.`
                            : `The direct rule for ${subjectName}: ${featureLabel} will be removed. Effective access will fall back to profile and groups.`
                          : lang === "ru"
                            ? `Групповая политика ${subjectName}: ${featureLabel} будет удалена. Участники начнут наследовать другие правила.`
                            : `The group policy for ${subjectName}: ${featureLabel} will be removed. Members will inherit other rules.`,
                      })
                    }
                    className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-red-500/10 hover:text-red-300"
                    aria-label={common.delete}
                    title={common.delete}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

export default function SettingsPermissionsPage() {
  const { lang } = useI18n();
  const copy = ACCESS_UI_TEXT[lang].permissions;
  const common = ACCESS_UI_TEXT[lang].common;
  const queryClient = useQueryClient();
  const [matrixSearch, setMatrixSearch] = useState("");
  const [kindFilter, setKindFilter] = useState<SubjectFilter>("all");
  const [exceptionOpen, setExceptionOpen] = useState(false);
  const [subjectSearch, setSubjectSearch] = useState("");
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState<ExceptionDraft>({ kind: "user", subjectId: 0, feature: "", allowed: true });
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);

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

  const userPermissions = useMemo(() => permsData?.permissions ?? [], [permsData?.permissions]);
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
  const userPermissionMap = useMemo(() => keyedPermissionMap(userPermissions, (permission) => permission.user_id), [userPermissions]);
  const groupPermissionMap = useMemo(() => keyedPermissionMap(groupPermissions, (permission) => permission.group_id), [groupPermissions]);

  const matrixRows = useMemo<MatrixRow[]>(() => {
    const userRows = users.map((user) => ({
      key: `user-${user.id}`,
      kind: "user" as const,
      id: user.id,
      name: user.username,
      detail: `${user.email || common.noEmail} · ${getAccessProfileLabel(lang, user.access_profile || "custom")}`,
      cells: features.map((feature) => {
        const direct = userPermissionMap.get(`${user.id}:${feature.value}`);
        const groupSources = user.group_permission_sources?.[feature.value] || [];
        const effective = user.effective_permissions?.[feature.value];
        const source = direct
          ? "direct"
          : groupSources.length
            ? groupSources.map((sourceItem) => sourceItem.group_name).join(", ")
            : user.permission_sources?.[feature.value] || user.access_profile || "profile";
        return {
          feature: feature.value,
          allowed: typeof effective === "boolean" ? effective : null,
          explicit: Boolean(direct),
          source,
        };
      }),
    }));

    const groupRows = groups.map((group) => ({
      key: `group-${group.id}`,
      kind: "group" as const,
      id: group.id,
      name: group.name,
      detail: `${group.member_count} ${common.members.toLowerCase()}`,
      cells: features.map((feature) => {
        const explicit = groupPermissionMap.get(`${group.id}:${feature.value}`);
        return {
          feature: feature.value,
          allowed: explicit ? explicit.allowed : null,
          explicit: Boolean(explicit),
          source: "group",
        };
      }),
    }));

    return [...userRows, ...groupRows];
  }, [common.members, common.noEmail, features, groupPermissionMap, groups, lang, userPermissionMap, users]);

  const filteredRows = useMemo(() => {
    const needle = matrixSearch.trim().toLowerCase();
    return matrixRows.filter((row) => {
      const kindMatches = kindFilter === "all" || row.kind === kindFilter;
      const searchMatches = !needle || [row.name, row.detail, row.kind].join(" ").toLowerCase().includes(needle);
      return kindMatches && searchMatches;
    });
  }, [kindFilter, matrixRows, matrixSearch]);

  const reload = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["access", "permissions"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "group-permissions"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "users"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "groups"] }),
    ]);
  };

  const openException = (kind: SubjectKind, subjectId?: number, feature?: string, allowed = true) => {
    const defaultSubjectId = kind === "user" ? users[0]?.id : groups[0]?.id;
    setDraft({
      kind,
      subjectId: subjectId || defaultSubjectId || 0,
      feature: feature || features[0]?.value || "",
      allowed,
    });
    setSubjectSearch("");
    setExceptionOpen(true);
  };

  const saveException = async () => {
    if (!draft.subjectId || !draft.feature) return;
    setSaving(true);
    try {
      if (draft.kind === "user") {
        await upsertAccessPermission({
          user_id: draft.subjectId,
          feature: draft.feature,
          allowed: draft.allowed,
        });
      } else {
        await upsertAccessGroupPermission({
          group_id: draft.subjectId,
          feature: draft.feature,
          allowed: draft.allowed,
        });
      }
      notify.success({ title: common.save, description: getAccessFeatureLabel(lang, draft.feature) });
      setExceptionOpen(false);
      await reload();
    } catch (err) {
      notify.error({ title: copy.error, description: err instanceof Error ? err.message : String(err) });
    } finally {
      setSaving(false);
    }
  };

  const toggleUserPermission = async (permission: AccessPermission) => {
    await updateAccessPermission(permission.id, !permission.allowed);
    await reload();
  };

  const toggleGroupPermission = async (permission: AccessGroupPermission) => {
    await updateAccessGroupPermission(permission.id, !permission.allowed);
    await reload();
  };

  const confirmDeletePermission = async () => {
    if (!deleteTarget) return;
    setSaving(true);
    try {
      if (deleteTarget.kind === "user") {
        await deleteAccessPermission(deleteTarget.id);
      } else {
        await deleteAccessGroupPermission(deleteTarget.id);
      }
      setDeleteTarget(null);
      await reload();
    } catch (err) {
      notify.error({ title: copy.error, description: err instanceof Error ? err.message : String(err) });
    } finally {
      setSaving(false);
    }
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
    <>
      <div className="space-y-6 pb-10">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
              <Shield className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-foreground">{copy.title}</h1>
              <p className="mt-1 text-sm leading-5 text-muted-foreground">{copy.subtitle}</p>
            </div>
          </div>
          <Button className="h-10 gap-2" onClick={() => openException("user")}>
            <Plus className="h-4 w-4" />
            {lang === "ru" ? "Добавить исключение" : "Add exception"}
          </Button>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-lg border border-border/70 bg-secondary/10 px-4 py-3">
            <div className="text-2xl font-semibold leading-8 text-foreground">{users.length}</div>
            <div className="mt-1 text-sm leading-5 text-muted-foreground">{lang === "ru" ? "пользователей" : "users"}</div>
          </div>
          <div className="rounded-lg border border-border/70 bg-secondary/10 px-4 py-3">
            <div className="text-2xl font-semibold leading-8 text-foreground">{groups.length}</div>
            <div className="mt-1 text-sm leading-5 text-muted-foreground">{lang === "ru" ? "групп" : "groups"}</div>
          </div>
          <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-4 py-3">
            <div className="text-2xl font-semibold leading-8 text-foreground">{userPermissions.length}</div>
            <div className="mt-1 text-sm leading-5 text-amber-300">{copy.userListTitle}</div>
          </div>
          <div className="rounded-lg border border-blue-500/25 bg-blue-500/10 px-4 py-3">
            <div className="text-2xl font-semibold leading-8 text-foreground">{groupPermissions.length}</div>
            <div className="mt-1 text-sm leading-5 text-blue-300">{copy.groupListTitle}</div>
          </div>
        </div>

        <section className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/70 bg-card px-4 py-3">
            <div>
              <h2 className="text-base font-semibold text-foreground">{lang === "ru" ? "Матрица итогового доступа" : "Effective Access Matrix"}</h2>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {lang === "ru" ? "Клик по ячейке создаёт или обновляет explicit rule." : "Click a cell to create or update an explicit rule."}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative min-w-64">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={matrixSearch}
                  onChange={(event) => setMatrixSearch(event.target.value)}
                  placeholder={lang === "ru" ? "Поиск субъекта" : "Search subject"}
                  className="h-10 pl-9"
                />
              </div>
              <div className="flex gap-1">
                <FilterButton active={kindFilter === "all"} onClick={() => setKindFilter("all")}>
                  {lang === "ru" ? "Все" : "All"}
                </FilterButton>
                <FilterButton active={kindFilter === "user"} onClick={() => setKindFilter("user")}>
                  {lang === "ru" ? "Пользователи" : "Users"}
                </FilterButton>
                <FilterButton active={kindFilter === "group"} onClick={() => setKindFilter("group")}>
                  {lang === "ru" ? "Группы" : "Groups"}
                </FilterButton>
              </div>
            </div>
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="sticky left-0 z-10 min-w-64 bg-secondary/40">{lang === "ru" ? "Субъект" : "Subject"}</TableHead>
                {features.map((feature) => (
                  <TableHead key={feature.value} className="min-w-36">{feature.label}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredRows.length ? (
                filteredRows.map((row) => (
                  <TableRow key={row.key}>
                    <TableCell className="sticky left-0 z-10 min-w-64 bg-card">
                      <div className="flex items-center gap-2">
                        {row.kind === "user" ? <Users className="h-4 w-4 text-muted-foreground" /> : <Shield className="h-4 w-4 text-muted-foreground" />}
                        <div className="min-w-0">
                          <div className="truncate font-semibold text-foreground">{row.name}</div>
                          <div className="truncate text-sm text-muted-foreground">{row.detail}</div>
                        </div>
                      </div>
                    </TableCell>
                    {row.cells.map((cell) => (
                      <TableCell key={`${row.key}-${cell.feature}`} className="min-w-36">
                        <button
                          type="button"
                          onClick={() => openException(row.kind, row.id, cell.feature, cell.allowed !== false)}
                          className="text-left"
                          aria-label={`${row.name} ${getAccessFeatureLabel(lang, cell.feature)}`}
                        >
                          <PermissionPill allowed={cell.allowed} explicit={cell.explicit} source={cell.source} />
                        </button>
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={features.length + 1}>
                    <EmptyState
                      icon={<Shield className="h-5 w-5" />}
                      title={lang === "ru" ? "Субъекты не найдены" : "No subjects found"}
                      description={lang === "ru" ? "Измените фильтры матрицы." : "Adjust the matrix filters."}
                    />
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </section>

        <section className="space-y-3">
          <div>
            <h2 className="text-base font-semibold text-foreground">{lang === "ru" ? "Явные исключения" : "Explicit Exceptions"}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {lang === "ru" ? "Один список для пользовательских и групповых правил." : "One list for user and group rules."}
            </p>
          </div>
          <ExplicitRuleRows
            lang={lang}
            userPermissions={userPermissions}
            groupPermissions={groupPermissions}
            onToggleUser={(permission) => void toggleUserPermission(permission)}
            onToggleGroup={(permission) => void toggleGroupPermission(permission)}
            onDelete={setDeleteTarget}
          />
        </section>
      </div>

      <ExceptionSheet
        lang={lang}
        open={exceptionOpen}
        draft={draft}
        users={users}
        groups={groups}
        features={features}
        saving={saving}
        subjectSearch={subjectSearch}
        onSubjectSearchChange={setSubjectSearch}
        onDraftChange={setDraft}
        onOpenChange={(open) => {
          if (!open && !saving) setExceptionOpen(false);
        }}
        onSave={saveException}
      />

      <DeleteDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open && !saving) setDeleteTarget(null);
        }}
        title={deleteTarget?.title || ""}
        description={deleteTarget?.description || ""}
        confirmLabel={common.delete}
        cancelLabel={common.cancel}
        onConfirm={confirmDeletePermission}
      />
    </>
  );
}
