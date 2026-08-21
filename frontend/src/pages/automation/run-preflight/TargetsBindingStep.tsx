import { KeyRound, Layers, Server, UserRound } from "lucide-react";

import type {
  PlaybookBindingProfile,
  PlaybookInventoryBindings,
} from "@/api/playbooks";
import { StatusIndicator } from "@/components/StatusIndicator";
import { ServerOsBadge } from "@/components/servers/ServerOsBadge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { FrontendGroup, FrontendServer } from "@/lib/api";
import { resolveServerOs } from "@/lib/server-os";
import { cn } from "@/lib/utils";

interface TargetsBindingStepProps {
  lang: string;
  servers: FrontendServer[];
  groups: FrontendGroup[];
  bindingProfiles: PlaybookBindingProfile[];
  selectedBindingProfileId: number | null;
  selectedServerIds: Set<number>;
  selectedGroupIds: Set<number>;
  hostSelectors: string[];
  inventoryBindings: PlaybookInventoryBindings;
  bindingChoices: Record<string, string>;
  onBindingProfileChange: (profileId: number | null) => void;
  onToggleServer: (serverId: number) => void;
  onToggleGroup: (groupId: number) => void;
  onSelectOnline: () => void;
  onClearTargets: () => void;
  onBindingChoiceChange: (selector: string, choice: string) => void;
  showSourceSelector?: boolean;
}

export function TargetsBindingStep({
  lang,
  servers,
  groups,
  bindingProfiles,
  selectedBindingProfileId,
  selectedServerIds,
  selectedGroupIds,
  hostSelectors,
  inventoryBindings,
  bindingChoices,
  onBindingProfileChange,
  onToggleServer,
  onToggleGroup,
  onSelectOnline,
  onClearTargets,
  onBindingChoiceChange,
  showSourceSelector = true,
}: TargetsBindingStepProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const selectedProfile = bindingProfiles.find((profile) => profile.id === selectedBindingProfileId) || null;
  const profileVariableNames = selectedProfile
    ? Array.from(
        new Set([
          ...Object.keys(selectedProfile.variable_values || {}),
          ...(selectedProfile.secret_variables || []),
        ]),
      )
    : [];

  return (
    <div className="space-y-4">
      {showSourceSelector ? <section className="rounded-sm border border-border bg-card p-4 shadow-elev-1">
        <div className="grid gap-3 sm:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] sm:items-end">
          <div className="space-y-1.5">
            <Label htmlFor="run-target-source">{tr("Источник целей", "Target source")}</Label>
            <Select
              value={selectedBindingProfileId ? `profile:${selectedBindingProfileId}` : "adhoc"}
              onValueChange={(value) => onBindingProfileChange(value === "adhoc" ? null : Number(value.slice(8)))}
            >
              <SelectTrigger id="run-target-source" aria-label={tr("Источник целей", "Target source")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="adhoc">{tr("Разовый выбор", "Ad-hoc targets")}</SelectItem>
                {bindingProfiles.map((profile) => (
                  <SelectItem key={profile.id} value={`profile:${profile.id}`}>
                    {profile.name}{profile.is_default ? ` · ${tr("по умолчанию", "default")}` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <p className="text-xs text-muted-foreground">
            {selectedProfile
              ? tr(
                  "Используется ваш личный versioned binding profile.",
                  "Your personal versioned binding profile will be used.",
                )
              : tr(
                  "Выберите серверы/группы и явно свяжите hosts-селекторы.",
                  "Select servers/groups and map every hosts selector explicitly.",
                )}
          </p>
        </div>
      </section> : null}

      {selectedProfile ? (
        <section className="rounded-sm border border-primary/30 bg-primary/5 p-4 shadow-elev-1">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <UserRound className="h-4 w-4 text-primary" />
                <h3 className="text-sm font-semibold text-foreground">{selectedProfile.name}</h3>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                v{selectedProfile.version} · {Object.keys(selectedProfile.selector_mappings || {}).length} {tr("привязок", "bindings")}
              </p>
            </div>
            {selectedProfile.is_default ? (
              <span className="rounded-sm border border-primary/30 bg-primary/10 px-2 py-1 text-2xs text-primary">
                {tr("По умолчанию", "Default")}
              </span>
            ) : null}
          </div>

          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            <div className="rounded-sm border border-border bg-card p-3">
              <p className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">
                {tr("Selector mappings", "Selector mappings")}
              </p>
              <div className="mt-2 space-y-1.5">
                {Object.entries(selectedProfile.selector_mappings || {}).map(([selector, binding]) => (
                  <div key={selector} className="flex justify-between gap-3 text-xs">
                    <span className="truncate font-mono text-foreground">{selector}</span>
                    <span className="shrink-0 text-muted-foreground">
                      {binding.server_ids.length} S · {binding.group_ids.length} G
                    </span>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-sm border border-border bg-card p-3">
              <div className="flex items-center gap-1.5">
                <KeyRound className="h-3.5 w-3.5 text-muted-foreground" />
                <p className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">
                  {tr("Переменные — только имена", "Variables — names only")}
                </p>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {profileVariableNames.length ? profileVariableNames.map((name) => (
                  <span key={name} className="rounded-sm border border-border bg-surface-0 px-2 py-1 font-mono text-2xs text-foreground">
                    {name}{selectedProfile.secret_variables.includes(name) ? " · secret" : ""}
                  </span>
                )) : <span className="text-xs text-muted-foreground">{tr("Нет переменных", "No variables")}</span>}
              </div>
              {selectedProfile.secret_variables.length ? (
                <p className="mt-2 text-xs text-muted-foreground">
                  {tr(
                    "Секретные значения хранятся отдельно и никогда не загружаются в браузер.",
                    "Secret values are stored separately and are never loaded into the browser.",
                  )}
                </p>
              ) : null}
            </div>
          </div>
        </section>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <section className="space-y-3 rounded-sm border border-border bg-card p-4 shadow-elev-1">
              <div className="flex items-center justify-between gap-2">
                <h3 className="flex items-center gap-2 text-sm font-medium text-foreground">
                  <Server className="h-4 w-4 text-primary" />
                  {tr("Серверы", "Servers")} ({selectedServerIds.size})
                </h3>
                <div className="flex gap-1">
                  <Button size="xs" variant="outline" className="h-7" onClick={onSelectOnline}>
                    {tr("Онлайн", "Online")}
                  </Button>
                  <Button size="xs" variant="outline" className="h-7" onClick={onClearTargets}>
                    {tr("Сброс", "Clear")}
                  </Button>
                </div>
              </div>
              <div className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
                {servers.map((server) => (
                  <button
                    key={server.id}
                    type="button"
                    aria-pressed={selectedServerIds.has(server.id)}
                    onClick={() => onToggleServer(server.id)}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded-sm border px-3 py-2.5 text-left text-xs transition-colors",
                      selectedServerIds.has(server.id)
                        ? "border-primary bg-primary/10 text-foreground"
                        : "border-border bg-surface-0/50 text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <ServerOsBadge kind={resolveServerOs(server)} size="sm" />
                    <StatusIndicator status={server.status} showLabel={false} />
                    <span className="min-w-0 flex-1 truncate font-medium">{server.name}</span>
                    <span className="font-mono opacity-60">{server.host}</span>
                  </button>
                ))}
              </div>
            </section>

            <section className="space-y-3 rounded-sm border border-border bg-card p-4 shadow-elev-1">
              <h3 className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Layers className="h-4 w-4 text-primary" />
                {tr("Группы", "Groups")} ({selectedGroupIds.size})
              </h3>
              <div className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
                {groups.map((group) => (
                  <button
                    key={group.id}
                    type="button"
                    aria-pressed={group.id != null && selectedGroupIds.has(group.id)}
                    disabled={group.id == null}
                    onClick={() => { if (group.id != null) onToggleGroup(group.id); }}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded-sm border px-3 py-2.5 text-left text-xs transition-colors",
                      group.id != null && selectedGroupIds.has(group.id)
                        ? "border-primary bg-primary/10 text-foreground"
                        : "border-border bg-surface-0/50 text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: group.color || "hsl(var(--primary))" }} />
                    <span className="min-w-0 flex-1 truncate font-medium">{group.name}</span>
                    <span className="font-mono opacity-60">{group.server_count ?? "—"}</span>
                  </button>
                ))}
              </div>
            </section>
          </div>

          {hostSelectors.length ? (
            <section className="space-y-3 rounded-sm border border-primary/25 bg-primary/5 p-4 shadow-elev-1">
              <div>
                <h3 className="text-sm font-medium text-foreground">{tr("Привязка hosts", "Host bindings")}</h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  {tr("Исходный YAML не меняется.", "The source YAML remains unchanged.")}
                </p>
              </div>
              <div className="grid gap-2 md:grid-cols-2">
                {hostSelectors.map((selector) => (
                  <div key={selector} className="space-y-1.5 rounded-sm border border-border bg-card p-3">
                    <Label className="font-mono text-xs">hosts: {selector}</Label>
                    <Select
                      value={bindingChoices[selector] || (hostSelectors.length === 1 ? "selected" : "")}
                      onValueChange={(choice) => onBindingChoiceChange(selector, choice)}
                    >
                      <SelectTrigger aria-label={`hosts: ${selector}`}>
                        <SelectValue placeholder={tr("Выберите цель", "Choose target")} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="selected">{tr("Все выбранные выше", "All selected above")}</SelectItem>
                        {groups.filter((group) => group.id != null && selectedGroupIds.has(group.id)).map((group) => (
                          <SelectItem key={`group-${group.id}`} value={`group:${group.id}`}>
                            {tr("Группа", "Group")}: {group.name}
                          </SelectItem>
                        ))}
                        {servers.filter((server) => selectedServerIds.has(server.id)).map((server) => (
                          <SelectItem key={`server-${server.id}`} value={`server:${server.id}`}>
                            {tr("Сервер", "Server")}: {server.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {!inventoryBindings[selector] ? (
                      <p className="text-xs text-amber-400">{tr("Требуется привязка", "Binding required")}</p>
                    ) : null}
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}
