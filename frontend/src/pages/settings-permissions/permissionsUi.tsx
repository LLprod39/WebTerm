import { ArrowLeftRight, Search, Shield, ShieldCheck, ShieldX, Trash2, Users } from "lucide-react";

import { ACCESS_FEATURE_OPTIONS, type AccessGroup, type AccessGroupPermission, type AccessPermission, type AccessUser } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, StatusBadge } from "@/components/ui/page-shell";
import { ACCESS_UI_TEXT, getAccessFeatureLabel } from "@/lib/accessUiText";
import { cn } from "@/lib/utils";


export type SubjectKind = "user" | "group";
export type SubjectFilter = "all" | SubjectKind;
export type ExceptionDraft = {
  kind: SubjectKind;
  subjectId: number;
  feature: string;
  allowed: boolean;
};

export type DeleteTarget = {
  kind: SubjectKind;
  id: number;
  title: string;
  description: string;
};

export type MatrixCell = {
  feature: string;
  allowed: boolean | null;
  explicit: boolean;
  source: string;
};

export type MatrixRow = {
  key: string;
  kind: SubjectKind;
  id: number;
  name: string;
  detail: string;
  cells: MatrixCell[];
};

export const FALLBACK_FEATURES = ACCESS_FEATURE_OPTIONS;

export function keyedPermissionMap<T extends { feature: string }>(items: T[], idSelector: (item: T) => number) {
  return new Map(items.map((item) => [`${idSelector(item)}:${item.feature}`, item] as const));
}

export function PermissionPill({
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

export function FilterButton({
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

export function ExceptionSheet({
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

export function ExplicitRuleRows({
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

