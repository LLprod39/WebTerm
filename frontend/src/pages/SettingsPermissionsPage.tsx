import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, Shield, Users } from "lucide-react";

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
  type AccessGroupPermission,
  type AccessPermission,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, QueryStateBlock } from "@/components/ui/page-shell";
import { SkeletonTable } from "@/components/ui/list-state";
import { DeleteDialog } from "@/components/system/ConfirmDialog";
import { useI18n } from "@/lib/i18n";
import { notify } from "@/lib/notify";
import { ACCESS_UI_TEXT, getAccessFeatureLabel, getAccessProfileLabel, localizeAccessFeatures } from "@/lib/accessUiText";
import {
  ExceptionSheet,
  ExplicitRuleRows,
  FALLBACK_FEATURES,
  FilterButton,
  PermissionPill,
  keyedPermissionMap,
  type DeleteTarget,
  type ExceptionDraft,
  type MatrixRow,
  type SubjectFilter,
  type SubjectKind,
} from "./settings-permissions/permissionsUi";


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

  const { data: permsData, isLoading, error, refetch } = useQuery({
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
    return <div className="p-6"><SkeletonTable rows={8} cols={5} /></div>;
  }
  if (error) {
    return (
      <div className="p-6">
        <QueryStateBlock error={error} errorText={copy.error} onRetry={() => void refetch()}>
          {null}
        </QueryStateBlock>
      </div>
    );
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
