import { ACCESS_UI_TEXT, getAccessSourceLabel } from "@/lib/accessUiText";
import type { AccessFeatureOption, AccessGroupOption, PermissionMode } from "./settingsUsersTypes";

export const SELECT_CLASS =
  "h-10 w-full rounded-lg border border-border bg-secondary/30 px-3 text-sm text-foreground outline-none ring-0 transition-all focus:border-primary/40 focus:ring-1 focus:ring-primary/30";

export function FieldLabel({ htmlFor, children }: { htmlFor?: string; children: string }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
      {children}
    </label>
  );
}

export function UserAvatar({ name, active }: { name: string; active: boolean }) {
  const initials = name.slice(0, 2).toUpperCase();
  return (
    <div
      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-xs font-bold tracking-wide transition-colors ${
        active
          ? "bg-primary/15 text-primary ring-1 ring-primary/20"
          : "bg-muted/40 text-muted-foreground ring-1 ring-border/40"
      }`}
    >
      {initials}
    </div>
  );
}

export function PermissionSummary({
  lang,
  entries,
  features,
  title,
}: {
  lang: "en" | "ru";
  entries: Array<[string, boolean]>;
  features: AccessFeatureOption[];
  title: string;
}) {
  const allowedCount = entries.filter(([, allowed]) => allowed).length;
  const deniedCount = entries.length - allowedCount;
  const previewEntries = entries.slice(0, 6);
  const renderChip = ([feat, allowed]: [string, boolean]) => (
    <span
      key={feat}
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium ${
        allowed
          ? "bg-emerald-500/10 text-emerald-400"
          : "bg-red-500/8 text-red-400/80"
      }`}
    >
      {features.find((feature) => feature.value === feat)?.label || feat}
    </span>
  );

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground/70">
        <span className="font-semibold uppercase tracking-wider">{title}</span>
        <span>
          {allowedCount} {lang === "ru" ? "разрешено" : "allowed"}
        </span>
        <span>
          {deniedCount} {lang === "ru" ? "запрещено" : "denied"}
        </span>
      </div>
      <div className="flex flex-wrap gap-1.5 sm:hidden">
        {previewEntries.map(renderChip)}
        {entries.length > previewEntries.length && (
          <span className="inline-flex items-center rounded-md bg-secondary/35 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
            +{entries.length - previewEntries.length}
          </span>
        )}
      </div>
      <div className="hidden flex-wrap gap-1.5 sm:flex">
        {entries.map(renderChip)}
      </div>
    </div>
  );
}

export function PermissionModeField({
  lang,
  label,
  mode,
  source,
  effective,
  onChange,
}: {
  lang: "en" | "ru";
  label: string;
  mode: PermissionMode;
  source?: string;
  effective?: boolean;
  onChange: (value: PermissionMode) => void;
}) {
  const t = ACCESS_UI_TEXT[lang].common;
  return (
    <div className="group/perm flex flex-col items-stretch gap-2 rounded-lg border border-border/40 bg-secondary/10 px-3 py-2.5 transition-colors hover:bg-secondary/20 2xl:flex-row 2xl:items-center 2xl:justify-between">
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium text-foreground/90">{label}</div>
        <div className="mt-0.5 text-[11px] text-muted-foreground/60">
          {t.effective}: {effective ? t.allowed : t.denied}
          {source ? ` · ${getAccessSourceLabel(lang, source)}` : ""}
        </div>
      </div>
      <select
        value={mode}
        onChange={(event) => onChange(event.target.value as PermissionMode)}
        className="h-8 w-full shrink-0 rounded-md border border-border bg-secondary/30 px-2 text-xs text-foreground outline-none focus:ring-1 focus:ring-primary/30 2xl:w-36"
        aria-label={`${label} mode`}
      >
        <option value="inherit">{t.inherit}</option>
        <option value="allow">{t.allow}</option>
        <option value="deny">{t.deny}</option>
      </select>
    </div>
  );
}

export function GroupPicker({
  groups,
  selectedGroupIds,
  onToggle,
}: {
  groups: AccessGroupOption[];
  selectedGroupIds: number[];
  onToggle: (groupId: number) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {groups.map((group) => {
        const active = selectedGroupIds.includes(group.id);
        return (
          <button
            key={group.id}
            type="button"
            onClick={() => onToggle(group.id)}
            className={`min-h-8 rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
              active
                ? "bg-primary/15 text-primary ring-1 ring-primary/25"
                : "bg-secondary/20 text-muted-foreground ring-1 ring-border/40 hover:bg-secondary/40 hover:text-foreground"
            }`}
          >
            {group.name}
          </button>
        );
      })}
      {groups.length === 0 && <span className="text-xs text-muted-foreground/50 italic">Нет групп</span>}
    </div>
  );
}
