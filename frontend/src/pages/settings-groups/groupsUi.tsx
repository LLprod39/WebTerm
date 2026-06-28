import { Search, Shield } from "lucide-react";

import { ACCESS_FEATURE_OPTIONS, type AccessUser } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ACCESS_UI_TEXT } from "@/lib/accessUiText";
import { cn } from "@/lib/utils";


export type PermissionMode = "inherit" | "allow" | "deny";
export type GroupDraft = {
  id?: number;
  name: string;
  members: number[];
  permission_modes: Record<string, PermissionMode>;
};

export const FALLBACK_FEATURES = ACCESS_FEATURE_OPTIONS;

export function createPermissionModesFromExplicit(
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

export function buildExplicitPayload(modes: Record<string, PermissionMode>) {
  return Object.fromEntries(
    Object.entries(modes).map(([feature, mode]) => [feature, mode === "inherit" ? null : mode === "allow"]),
  );
}

function toggleId(source: number[], id: number) {
  return source.includes(id) ? source.filter((value) => value !== id) : [...source, id];
}

export function emptyDraft(): GroupDraft {
  return { name: "", members: [], permission_modes: {} };
}

function FieldLabel({ htmlFor, children }: { htmlFor?: string; children: string }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-sm font-medium text-foreground">
      {children}
    </label>
  );
}

function PolicyModeControl({
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
  const common = ACCESS_UI_TEXT[lang].common;
  const options: Array<{ value: PermissionMode; label: string; className: string }> = [
    { value: "inherit", label: common.inherit, className: "data-[active=true]:border-border data-[active=true]:bg-secondary" },
    { value: "allow", label: common.allow, className: "data-[active=true]:border-emerald-500/40 data-[active=true]:bg-emerald-500/10 data-[active=true]:text-emerald-300" },
    { value: "deny", label: common.deny, className: "data-[active=true]:border-red-500/40 data-[active=true]:bg-red-500/10 data-[active=true]:text-red-300" },
  ];
  return (
    <div className="rounded-lg border border-border/60 bg-secondary/10 px-3 py-3">
      <div className="text-sm font-medium text-foreground">{label}</div>
      <div className="mt-2 grid grid-cols-3 gap-1.5">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            data-active={mode === option.value}
            onClick={() => onChange(option.value)}
            className={cn(
              "min-h-9 rounded-md border border-border/50 px-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground",
              option.className,
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function GroupSheet({
  lang,
  open,
  mode,
  draft,
  users,
  features,
  saving,
  memberSearch,
  onMemberSearchChange,
  onOpenChange,
  onDraftChange,
  onSave,
}: {
  lang: "en" | "ru";
  open: boolean;
  mode: "create" | "edit" | null;
  draft: GroupDraft;
  users: AccessUser[];
  features: Array<{ value: string; label: string }>;
  saving: boolean;
  memberSearch: string;
  onMemberSearchChange: (value: string) => void;
  onOpenChange: (open: boolean) => void;
  onDraftChange: (draft: GroupDraft) => void;
  onSave: () => void | Promise<void>;
}) {
  const copy = ACCESS_UI_TEXT[lang].groupsPage;
  const common = ACCESS_UI_TEXT[lang].common;
  const filteredUsers = users.filter((user) =>
    [user.username, user.email, ...(user.groups || []).map((group) => group.name)]
      .join(" ")
      .toLowerCase()
      .includes(memberSearch.trim().toLowerCase()),
  );

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-[calc(100vw-1rem)] max-w-[680px] flex-col p-0 sm:w-[680px] sm:max-w-[680px]">
        <SheetHeader className="border-b border-border/70 px-5 py-4 pr-12 text-left">
          <SheetTitle className="text-lg">
            {mode === "edit" ? copy.editAction : copy.createTitle}
          </SheetTitle>
          <SheetDescription>
            {lang === "ru"
              ? "Задайте участников и групповые правила. Не задано означает наследование от профиля или системных defaults."
              : "Set members and group rules. Unset means access falls back to profile or system defaults."}
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 space-y-6 overflow-auto px-5 py-5">
          <div>
            <FieldLabel htmlFor="group-name">{copy.namePlaceholder}</FieldLabel>
            <Input
              id="group-name"
              value={draft.name}
              onChange={(event) => onDraftChange({ ...draft, name: event.target.value })}
              placeholder={copy.namePlaceholder}
              className="h-10"
            />
          </div>

          <section>
            <div className="mb-2 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-base font-semibold text-foreground">{common.members}</h3>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  {lang === "ru" ? "Фильтруйте пользователей и добавляйте их в группу." : "Filter users and add them to the group."}
                </p>
              </div>
              <StatusBadge label={String(draft.members.length)} tone="info" dot={false} />
            </div>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={memberSearch}
                onChange={(event) => onMemberSearchChange(event.target.value)}
                placeholder={lang === "ru" ? "Поиск по логину, email или группе" : "Search by username, email, or group"}
                className="h-10 pl-9"
              />
            </div>
            <div className="mt-3 max-h-56 overflow-auto rounded-lg border border-border/70">
              {filteredUsers.length ? (
                filteredUsers.map((user) => {
                  const active = draft.members.includes(user.id);
                  return (
                    <button
                      key={user.id}
                      type="button"
                      onClick={() => onDraftChange({ ...draft, members: toggleId(draft.members, user.id) })}
                      className={cn(
                        "flex min-h-12 w-full items-center justify-between gap-3 border-b border-border/50 px-3 py-2 text-left last:border-b-0 hover:bg-secondary/30",
                        active && "bg-primary/10",
                      )}
                    >
                      <span className="min-w-0">
                        <span className="block text-sm font-medium text-foreground">{user.username}</span>
                        <span className="block truncate text-sm text-muted-foreground">{user.email || common.noEmail}</span>
                      </span>
                      <span className={cn("rounded-md border px-2 py-1 text-xs", active ? "border-primary/40 text-primary" : "border-border/60 text-muted-foreground")}>
                        {active ? common.allowed : common.none}
                      </span>
                    </button>
                  );
                })
              ) : (
                <div className="px-3 py-8 text-center text-sm text-muted-foreground">
                  {lang === "ru" ? "Пользователи не найдены." : "No users found."}
                </div>
              )}
            </div>
          </section>

          <section>
            <div className="mb-3">
              <h3 className="text-base font-semibold text-foreground">{copy.policyTitle}</h3>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {lang === "ru"
                  ? "Показывайте только явные групповые исключения. Остальное оставляйте наследоваться."
                  : "Only set explicit group exceptions. Leave everything else inherited."}
              </p>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {features.map((feature) => (
                <PolicyModeControl
                  key={feature.value}
                  lang={lang}
                  label={feature.label}
                  mode={draft.permission_modes[feature.value] || "inherit"}
                  onChange={(value) =>
                    onDraftChange({
                      ...draft,
                      permission_modes: { ...draft.permission_modes, [feature.value]: value },
                    })
                  }
                />
              ))}
            </div>
          </section>
        </div>

        <SheetFooter className="border-t border-border/70 px-5 py-4">
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}>
            {common.cancel}
          </Button>
          <Button onClick={() => void onSave()} disabled={saving || !draft.name.trim()}>
            {saving ? common.saving : mode === "edit" ? common.save : copy.createAction}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

