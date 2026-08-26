import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderOpen, FolderPlus, Pencil, Search, Trash2, Users } from "lucide-react";

import { createAccessGroup, deleteAccessGroup, fetchAccessGroups, fetchAccessUsers, updateAccessGroup, type AccessGroup } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, StatusBadge, QueryStateBlock } from "@/components/ui/page-shell";
import { SkeletonTable } from "@/components/ui/list-state";
import { DeleteDialog } from "@/components/system/ConfirmDialog";
import { useI18n } from "@/lib/i18n";
import { notify } from "@/lib/notify";
import { ACCESS_UI_TEXT, formatAccessText, getAccessFeatureLabel, localizeAccessFeatures } from "@/lib/accessUiText";
import { cn } from "@/lib/utils";
import {
  FALLBACK_FEATURES,
  GroupSheet,
  buildExplicitPayload,
  createPermissionModesFromExplicit,
  emptyDraft,
  type GroupDraft,
} from "./settings-groups/groupsUi";


export default function SettingsGroupsPage() {
  const { lang } = useI18n();
  const copy = ACCESS_UI_TEXT[lang].groupsPage;
  const common = ACCESS_UI_TEXT[lang].common;
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");
  const [sheetMode, setSheetMode] = useState<"create" | "edit" | null>(null);
  const [draft, setDraft] = useState<GroupDraft>(() => emptyDraft());
  const [memberSearch, setMemberSearch] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<AccessGroup | null>(null);

  const { data: groupsData, isLoading, error, refetch } = useQuery({
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

  const filteredGroups = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return groups;
    return groups.filter((group) =>
      [group.name, ...(group.members || []).map((member) => member.username)]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
  }, [groups, search]);

  const totalMembers = groups.reduce((sum, group) => sum + group.member_count, 0);
  const groupsWithPolicy = groups.filter((group) => Object.keys(group.explicit_permissions || {}).length > 0).length;
  const emptyGroups = groups.filter((group) => group.member_count === 0).length;

  const refreshAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["access", "groups"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "users"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "permissions"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "group-permissions"] }),
    ]);
  };

  const closeSheet = () => {
    setSheetMode(null);
    setDraft(emptyDraft());
    setMemberSearch("");
  };

  const openCreate = () => {
    setDraft(emptyDraft());
    setMemberSearch("");
    setSheetMode("create");
  };

  const openEdit = (group: AccessGroup) => {
    setDraft({
      id: group.id,
      name: group.name,
      members: (group.members || []).map((member) => member.id),
      permission_modes: createPermissionModesFromExplicit(features, group.explicit_permissions),
    });
    setMemberSearch("");
    setSheetMode("edit");
  };

  const saveDraft = async () => {
    if (!draft.name.trim()) return;
    setSaving(true);
    try {
      if (sheetMode === "edit" && draft.id) {
        await updateAccessGroup(draft.id, {
          name: draft.name.trim(),
          members: draft.members,
          explicit_permissions: buildExplicitPayload(draft.permission_modes),
        });
        notify.success({ title: common.save, description: draft.name.trim() });
      } else {
        await createAccessGroup({
          name: draft.name.trim(),
          members: draft.members,
          explicit_permissions: buildExplicitPayload(draft.permission_modes),
        });
        notify.success({ title: copy.createAction, description: draft.name.trim() });
      }
      closeSheet();
      await refreshAll();
    } catch (err) {
      notify.error({ title: copy.error, description: err instanceof Error ? err.message : String(err) });
    } finally {
      setSaving(false);
    }
  };

  const confirmRemoveGroup = async () => {
    if (!deleteTarget) return;
    setSaving(true);
    try {
      await deleteAccessGroup(deleteTarget.id);
      notify.success({ title: common.delete, description: deleteTarget.name });
      setDeleteTarget(null);
      await refreshAll();
    } catch (err) {
      notify.error({ title: copy.error, description: err instanceof Error ? err.message : String(err) });
    } finally {
      setSaving(false);
    }
  };

  if (isLoading) {
    return <div className="p-6"><SkeletonTable rows={6} cols={4} /></div>;
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
              <FolderOpen className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-foreground">{copy.title}</h1>
              <p className="mt-1 text-sm leading-5 text-muted-foreground">{copy.subtitle}</p>
            </div>
          </div>
          <Button className="h-10 gap-2" onClick={openCreate}>
            <FolderPlus className="h-4 w-4" />
            {copy.createAction}
          </Button>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-lg border border-border/70 bg-secondary/10 px-4 py-3">
            <div className="text-2xl font-semibold leading-8 text-foreground">{groups.length}</div>
            <div className="mt-1 text-sm leading-5 text-muted-foreground">{lang === "ru" ? "групп" : "groups"}</div>
          </div>
          <div className="rounded-lg border border-border/70 bg-secondary/10 px-4 py-3">
            <div className="text-2xl font-semibold leading-8 text-foreground">{totalMembers}</div>
            <div className="mt-1 text-sm leading-5 text-muted-foreground">{common.members.toLowerCase()}</div>
          </div>
          <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-4 py-3">
            <div className="text-2xl font-semibold leading-8 text-foreground">{groupsWithPolicy}</div>
            <div className="mt-1 text-sm leading-5 text-amber-300">{copy.explicitPolicy}</div>
          </div>
          <div className="rounded-lg border border-border/70 bg-secondary/10 px-4 py-3">
            <div className="text-2xl font-semibold leading-8 text-foreground">{emptyGroups}</div>
            <div className="mt-1 text-sm leading-5 text-muted-foreground">{lang === "ru" ? "без участников" : "empty groups"}</div>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/70 bg-card px-4 py-3">
          <div className="relative min-w-64 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={lang === "ru" ? "Поиск группы или участника" : "Search group or member"}
              className="h-10 pl-9"
            />
          </div>
          <div className="text-sm text-muted-foreground">
            {lang === "ru" ? `${filteredGroups.length} из ${groups.length}` : `${filteredGroups.length} of ${groups.length}`}
          </div>
        </div>

        {filteredGroups.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{lang === "ru" ? "Группа" : "Group"}</TableHead>
                <TableHead>{common.members}</TableHead>
                <TableHead>{copy.explicitPolicy}</TableHead>
                <TableHead className="w-28 text-right">{lang === "ru" ? "Действия" : "Actions"}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredGroups.map((group) => {
                const policyEntries = Object.entries(group.explicit_permissions || {});
                return (
                  <TableRow key={group.id}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-sm font-semibold text-primary">
                          {group.name.slice(0, 2).toUpperCase()}
                        </div>
                        <div className="min-w-0">
                          <div className="truncate font-semibold text-foreground">{group.name}</div>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Users className="h-4 w-4 text-muted-foreground" />
                        <span className="font-medium text-foreground">{group.member_count}</span>
                      </div>
                      <div className="mt-1 max-w-md truncate text-sm text-muted-foreground">
                        {group.members?.length
                          ? group.members.map((member) => member.username).join(", ")
                          : lang === "ru" ? "Нет участников" : "No members"}
                      </div>
                    </TableCell>
                    <TableCell>
                      {policyEntries.length ? (
                        <div className="flex flex-wrap gap-1.5">
                          {policyEntries.slice(0, 3).map(([feature, allowed]) => (
                            <span
                              key={feature}
                              className={cn(
                                "inline-flex items-center rounded-md border px-2 py-1 text-xs font-medium",
                                allowed
                                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                                  : "border-red-500/30 bg-red-500/10 text-red-300",
                              )}
                            >
                              {getAccessFeatureLabel(lang, feature)}
                            </span>
                          ))}
                          {policyEntries.length > 3 ? (
                            <StatusBadge label={`+${policyEntries.length - 3}`} tone="neutral" dot={false} />
                          ) : null}
                        </div>
                      ) : (
                        <span className="text-sm text-muted-foreground">{common.inherit}</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => openEdit(group)}
                          className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                          aria-label={copy.editAction}
                          title={copy.editAction}
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => setDeleteTarget(group)}
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
        ) : (
          <EmptyState
            icon={<Users className="h-6 w-6" />}
            title={groups.length ? (lang === "ru" ? "Группы не найдены" : "No groups found") : lang === "ru" ? "Групп пока нет" : "No groups yet"}
            description={groups.length ? (lang === "ru" ? "Измените поиск." : "Adjust the search.") : lang === "ru" ? "Создайте первую группу." : "Create the first group."}
          />
        )}
      </div>

      <GroupSheet
        lang={lang}
        open={sheetMode !== null}
        mode={sheetMode}
        draft={draft}
        users={users}
        features={features}
        saving={saving}
        memberSearch={memberSearch}
        onMemberSearchChange={setMemberSearch}
        onOpenChange={(open) => {
          if (!open && !saving) closeSheet();
        }}
        onDraftChange={setDraft}
        onSave={saveDraft}
      />

      <DeleteDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open && !saving) setDeleteTarget(null);
        }}
        title={formatAccessText(copy.deleteConfirm, { name: deleteTarget?.name || "" })}
        description={
          lang === "ru"
            ? `Группа "${deleteTarget?.name || ""}" будет удалена. Участники потеряют наследуемые групповые правила.`
            : `Group "${deleteTarget?.name || ""}" will be removed. Members will lose inherited group policies.`
        }
        confirmLabel={common.delete}
        cancelLabel={common.cancel}
        onConfirm={confirmRemoveGroup}
      />
    </>
  );
}
