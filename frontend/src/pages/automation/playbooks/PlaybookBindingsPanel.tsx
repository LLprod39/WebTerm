import { useMemo, useState } from "react";
import { KeyRound, Link2, Loader2, Plus, Search, Settings2, Trash2, X } from "lucide-react";

import type { PlaybookBindingProfile, PlaybookInventoryBindings } from "@/api/playbooks";
import { ConfirmDialog } from "@/components/system/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { FrontendGroup, FrontendServer } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { PlaybookWorkspaceVersioningController } from "./usePlaybookWorkspaceVersioning";

interface PlaybookBindingsPanelProps {
  lang: string;
  workspace: PlaybookWorkspaceVersioningController;
  servers: FrontendServer[];
  groups: Array<FrontendGroup & { id: number }>;
  hostSelectors: string[];
}

interface ValueRow { key: string; value: string }

export function PlaybookBindingsPanel({ lang, workspace, servers, groups, hostSelectors }: PlaybookBindingsPanelProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState<PlaybookBindingProfile | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PlaybookBindingProfile | null>(null);
  const [name, setName] = useState("");
  const [selectorMappings, setSelectorMappings] = useState<PlaybookInventoryBindings>({});
  const [variableRows, setVariableRows] = useState<ValueRow[]>([]);
  const [secretRows, setSecretRows] = useState<ValueRow[]>([]);
  const [removedSecrets, setRemovedSecrets] = useState<Set<string>>(new Set());
  const [targetSearch, setTargetSearch] = useState("");
  const [concurrency, setConcurrency] = useState(4);
  const [become, setBecome] = useState(true);
  const [dryRun, setDryRun] = useState(true);
  const [tags, setTags] = useState("");
  const [skipTags, setSkipTags] = useState("");
  const [limit, setLimit] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [formError, setFormError] = useState("");

  const filteredServers = useMemo(() => {
    const query = targetSearch.trim().toLocaleLowerCase();
    return query ? servers.filter((server) => `${server.name} ${server.host}`.toLocaleLowerCase().includes(query)) : servers;
  }, [servers, targetSearch]);
  const filteredGroups = useMemo(() => {
    const query = targetSearch.trim().toLocaleLowerCase();
    return query ? groups.filter((group) => group.name.toLocaleLowerCase().includes(query)) : groups;
  }, [groups, targetSearch]);

  if (!workspace.bindingsAccessible) return null;

  const edit = (profile?: PlaybookBindingProfile) => {
    const selectorNames = Array.from(new Set([
      ...(hostSelectors.length ? hostSelectors : ["all"]),
      ...Object.keys(profile?.selector_mappings || {}),
    ]));
    setCurrent(profile || null);
    setName(profile?.name || "");
    setSelectorMappings(Object.fromEntries(selectorNames.map((selector) => [selector, profile?.selector_mappings[selector] || { server_ids: [], group_ids: [] }])));
    setVariableRows(Object.entries(profile?.variable_values || {}).map(([key, value]) => ({ key, value: String(value ?? "") })));
    setSecretRows([]);
    setRemovedSecrets(new Set());
    setTargetSearch("");
    setConcurrency(profile?.options.concurrency || 4);
    setBecome(profile?.options.become ?? true);
    setDryRun(profile?.options.dry_run ?? true);
    setTags(profile?.options.tags || "");
    setSkipTags(profile?.options.skip_tags || "");
    setLimit(profile?.options.limit || "");
    setIsDefault(profile?.is_default || false);
    setFormError("");
    setOpen(true);
  };

  const close = () => {
    setSecretRows([]);
    setRemovedSecrets(new Set());
    setOpen(false);
  };

  const toggleTarget = (selector: string, type: "server" | "group", id: number) => {
    setSelectorMappings((currentMappings) => {
      const mapping = currentMappings[selector] || { server_ids: [], group_ids: [] };
      const key = type === "server" ? "server_ids" : "group_ids";
      const values = mapping[key];
      return { ...currentMappings, [selector]: { ...mapping, [key]: values.includes(id) ? values.filter((value) => value !== id) : [...values, id] } };
    });
  };

  const updateSecretRows = (rows: ValueRow[]) => {
    setSecretRows(rows);
    const replacementNames = new Set(rows.map((row) => row.key.trim()).filter(Boolean));
    if (!replacementNames.size) return;
    setRemovedSecrets((previous) => {
      const next = new Set(Array.from(previous).filter((secret) => !replacementNames.has(secret)));
      return next.size === previous.size ? previous : next;
    });
  };

  const save = async () => {
    setFormError("");
    const emptySelector = Object.entries(selectorMappings).find(([, mapping]) => !mapping.server_ids.length && !mapping.group_ids.length)?.[0];
    if (emptySelector) {
      setFormError(tr(`Выберите цели для hosts: ${emptySelector}.`, `Choose targets for hosts: ${emptySelector}.`));
      return;
    }
    const variableValues = Object.fromEntries(variableRows.filter((row) => row.key.trim()).map((row) => [row.key.trim(), row.value]));
    const secretValues = Object.fromEntries(secretRows.filter((row) => row.key.trim() && row.value).map((row) => [row.key.trim(), row.value]));
    const effectiveRemovedSecrets = Array.from(removedSecrets).filter((secret) => !(secret in secretValues));
    const saved = await workspace.saveBinding({
      name: name.trim(),
      selector_mappings: selectorMappings,
      variable_values: variableValues,
      ...(Object.keys(secretValues).length ? { secret_values: secretValues } : {}),
      ...(effectiveRemovedSecrets.length ? { remove_secret_names: effectiveRemovedSecrets } : {}),
      options: { concurrency, become, dry_run: dryRun, tags: tags.trim(), skip_tags: skipTags.trim(), limit: limit.trim() },
      is_default: isDefault,
    }, current);
    if (saved) close();
  };

  return (
    <section className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1" aria-labelledby="bindings-panel-title">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <div className="flex items-center gap-2"><Link2 className="h-4 w-4 text-primary" /><h3 id="bindings-panel-title" className="text-sm font-semibold text-foreground">{tr("Мои профили запуска", "My run profiles")}</h3></div>
          <p className="mt-1 text-xs text-muted-foreground">{tr("Профили принадлежат только вам; секретные значения никогда не возвращаются в браузер.", "Profiles belong only to you; secret values are never returned to the browser.")}</p>
        </div>
        <Button size="sm" variant="outline" className="gap-1.5" onClick={() => edit()}><Plus className="h-3.5 w-3.5" />{tr("Новый профиль", "New profile")}</Button>
      </div>

      <div className="divide-y divide-border">
        {workspace.bindings.length ? workspace.bindings.map((profile) => (
          <div key={profile.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
            <button type="button" className="min-w-0 flex-1 text-left" onClick={() => edit(profile)}>
              <div className="flex items-center gap-2"><span className="text-sm font-medium text-foreground">{profile.name}</span>{profile.is_default ? <span className="rounded-sm bg-primary/10 px-1.5 py-0.5 text-2xs text-primary">{tr("По умолчанию", "Default")}</span> : null}</div>
              <p className="mt-1 text-xs text-muted-foreground">{Object.keys(profile.selector_mappings).length} {tr("селекторов", "selectors")} · v{profile.version}{profile.secret_variables.length ? ` · ${profile.secret_variables.length} ${tr("секретов", "secrets")}` : ""}</p>
              {profile.secret_variables.length ? <div className="mt-1 flex flex-wrap gap-1">{profile.secret_variables.map((secret) => <span key={secret} className="inline-flex items-center gap-1 text-2xs text-muted-foreground"><KeyRound className="h-3 w-3" />{secret}</span>)}</div> : null}
            </button>
            <Button size="sm" variant="ghost" className="h-8 gap-1" onClick={() => edit(profile)}><Settings2 className="h-3.5 w-3.5" />{tr("Изменить", "Edit")}</Button>
            <Button size="sm" variant="ghost" className="h-8 text-destructive hover:text-destructive" aria-label={tr(`Удалить профиль ${profile.name}`, `Delete profile ${profile.name}`)} onClick={() => setDeleteTarget(profile)}><Trash2 className="h-3.5 w-3.5" /></Button>
          </div>
        )) : <div className="px-4 py-6 text-center text-sm text-muted-foreground">{tr("Сохранённых профилей пока нет", "No saved profiles yet")}</div>}
      </div>

      <Dialog open={open} onOpenChange={(next) => (next ? setOpen(true) : close())}>
        <DialogContent className="max-w-3xl" closeLabel={tr("Закрыть", "Close")}>
          <DialogHeader><DialogTitle>{current ? tr("Изменить профиль", "Edit profile") : tr("Новый профиль запуска", "New run profile")}</DialogTitle><DialogDescription>{tr("Выберите доступные серверы и группы; числовые ID вводить не нужно.", "Choose available servers and groups; no numeric IDs are required.")}</DialogDescription></DialogHeader>
          <DialogBody className="max-h-[72vh] space-y-4 overflow-auto">
            <div className="space-y-1.5"><Label htmlFor="binding-name">{tr("Название", "Name")}</Label><Input id="binding-name" value={name} onChange={(event) => setName(event.target.value)} /></div>

            <section className="space-y-3 rounded-sm border border-border bg-surface-0/35 p-3">
              <div className="relative"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><Input value={targetSearch} onChange={(event) => setTargetSearch(event.target.value)} className="pl-9" placeholder={tr("Найти сервер или группу", "Find server or group")} aria-label={tr("Поиск целей", "Search targets")} /></div>
              {Object.entries(selectorMappings).map(([selector, mapping]) => (
                <div key={selector} className="rounded-sm border border-border bg-card p-3">
                  <div className="flex items-center justify-between gap-2"><Label className="font-mono text-xs">hosts: {selector}</Label><span className="text-2xs text-muted-foreground">{mapping.server_ids.length} S · {mapping.group_ids.length} G</span></div>
                  <div className="mt-2 flex max-h-40 flex-wrap gap-1.5 overflow-auto">
                    {filteredGroups.map((group) => <TargetButton key={`g-${group.id}`} active={mapping.group_ids.includes(group.id)} label={`${tr("Группа", "Group")}: ${group.name}`} onClick={() => toggleTarget(selector, "group", group.id)} />)}
                    {filteredServers.map((server) => <TargetButton key={`s-${server.id}`} active={mapping.server_ids.includes(server.id)} label={`${tr("Сервер", "Server")}: ${server.name}`} detail={server.host} onClick={() => toggleTarget(selector, "server", server.id)} />)}
                    {!filteredGroups.length && !filteredServers.length ? <span className="text-xs text-muted-foreground">{tr("Ничего не найдено", "No targets found")}</span> : null}
                  </div>
                </div>
              ))}
            </section>

            <RowsEditor title={tr("Переменные", "Variables")} rows={variableRows} onChange={setVariableRows} secret={false} tr={tr} />

            <section className="space-y-3 rounded-sm border border-border bg-surface-0/35 p-3">
              <div><h4 className="flex items-center gap-2 text-sm font-medium text-foreground"><KeyRound className="h-4 w-4 text-primary" />{tr("Управляемые секреты", "Managed secrets")}</h4><p className="mt-1 text-xs text-muted-foreground">{tr("Введите только новые значения. Существующие значения скрыты и удаляются явно.", "Enter new values only. Existing values stay hidden and are removed explicitly.")}</p></div>
              {current?.secret_variables.length ? <div className="flex flex-wrap gap-1.5">{current.secret_variables.map((secret) => {
                const removed = removedSecrets.has(secret);
                return <button key={secret} type="button" aria-pressed={removed} onClick={() => setRemovedSecrets((previous) => { const next = new Set(previous); if (next.has(secret)) next.delete(secret); else next.add(secret); return next; })} className={cn("inline-flex items-center gap-1 rounded-sm border px-2 py-1 text-xs", removed ? "border-destructive/30 bg-destructive/5 text-destructive line-through" : "border-success/25 bg-success/5 text-success")}><KeyRound className="h-3 w-3" />{secret}{removed ? ` · ${tr("удалить", "remove")}` : ` · ${tr("настроен", "configured")}`}</button>;
              })}</div> : null}
              <RowsEditor title={tr("Новые или заменяемые секреты", "New or replaced secrets")} rows={secretRows} onChange={updateSecretRows} secret tr={tr} />
            </section>

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex items-center gap-2 rounded-sm border border-primary/25 bg-primary/5 p-3 text-sm text-foreground"><Checkbox checked={dryRun} onCheckedChange={(checked) => setDryRun(checked === true)} />{tr("Проверочный прогон по умолчанию", "Dry run by default")}</label>
              <label className="flex items-center gap-2 rounded-sm border border-border p-3 text-sm text-muted-foreground"><Checkbox checked={isDefault} onCheckedChange={(checked) => setIsDefault(checked === true)} />{tr("Использовать профиль по умолчанию", "Use as default profile")}</label>
            </div>

            <details className="rounded-sm border border-border bg-card">
              <summary className="flex cursor-pointer items-center gap-2 px-3 py-2.5 text-sm font-medium text-foreground"><Settings2 className="h-4 w-4 text-primary" />{tr("Дополнительные настройки", "Advanced settings")}</summary>
              <div className="grid gap-3 border-t border-border p-3 sm:grid-cols-2">
                <div className="space-y-1.5"><Label htmlFor="binding-concurrency">{tr("Параллельность", "Concurrency")}</Label><Input id="binding-concurrency" type="number" min={1} max={12} value={concurrency} onChange={(event) => setConcurrency(Math.max(1, Math.min(12, Number(event.target.value) || 1)))} /></div>
                <label className="flex items-center gap-2 self-end pb-2 text-sm text-muted-foreground"><Checkbox checked={become} onCheckedChange={(checked) => setBecome(checked === true)} />{tr("Повышенные права (become)", "Elevated access (become)")}</label>
                <div className="space-y-1.5"><Label htmlFor="binding-tags">{tr("Теги", "Tags")}</Label><Input id="binding-tags" value={tags} onChange={(event) => setTags(event.target.value)} placeholder="deploy,config" /></div>
                <div className="space-y-1.5"><Label htmlFor="binding-skip-tags">{tr("Пропустить теги", "Skip tags")}</Label><Input id="binding-skip-tags" value={skipTags} onChange={(event) => setSkipTags(event.target.value)} placeholder="dangerous" /></div>
                <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="binding-limit">Limit</Label><Input id="binding-limit" value={limit} onChange={(event) => setLimit(event.target.value)} placeholder="web:&online" /></div>
              </div>
            </details>
            {formError ? <p role="alert" className="text-xs text-destructive">{formError}</p> : null}
          </DialogBody>
          <DialogFooter><Button variant="outline" onClick={close}>{tr("Отмена", "Cancel")}</Button><Button disabled={workspace.bindingBusy || !name.trim()} onClick={() => void save()}>{workspace.bindingBusy ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : null}{tr("Сохранить профиль", "Save profile")}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog open={Boolean(deleteTarget)} onOpenChange={(next) => !next && setDeleteTarget(null)} title={tr("Удалить профиль?", "Delete profile?")} description={deleteTarget ? tr(`Профиль «${deleteTarget.name}» будет удалён.`, `Profile “${deleteTarget.name}” will be deleted.`) : ""} confirmLabel={tr("Удалить", "Delete")} cancelLabel={tr("Отмена", "Cancel")} tone="destructive" onConfirm={async () => { if (deleteTarget) await workspace.removeBinding(deleteTarget.id); setDeleteTarget(null); }} />
    </section>
  );
}

function TargetButton({ active, label, detail, onClick }: { active: boolean; label: string; detail?: string; onClick: () => void }) {
  return <button type="button" aria-pressed={active} onClick={onClick} className={cn("rounded-sm border px-2 py-1.5 text-left text-xs", active ? "border-primary bg-primary/10 text-foreground" : "border-border bg-surface-0 text-muted-foreground hover:text-foreground")}><span>{label}</span>{detail ? <span className="ml-1 font-mono text-2xs opacity-60">{detail}</span> : null}</button>;
}

function RowsEditor({ title, rows, onChange, secret, tr }: { title: string; rows: ValueRow[]; onChange: (rows: ValueRow[]) => void; secret: boolean; tr: (ru: string, en: string) => string }) {
  const update = (index: number, patch: Partial<ValueRow>) => onChange(rows.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row));
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between gap-2"><Label>{title}</Label><Button type="button" size="xs" variant="outline" className="h-7 gap-1" onClick={() => onChange([...rows, { key: "", value: "" }])}><Plus className="h-3 w-3" />{tr("Добавить", "Add")}</Button></div>
      {rows.length ? <div className="space-y-2">{rows.map((row, index) => <div key={index} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_2rem] gap-2"><Input value={row.key} onChange={(event) => update(index, { key: event.target.value })} placeholder={tr("Имя", "Name")} aria-label={`${title}: ${tr("имя", "name")}`} /><Input type={secret ? "password" : "text"} autoComplete="off" value={row.value} onChange={(event) => update(index, { value: event.target.value })} placeholder={tr("Значение", "Value")} aria-label={`${title}: ${tr("значение", "value")}`} /><Button type="button" size="icon" variant="ghost" className="h-9 w-8" aria-label={tr("Удалить строку", "Remove row")} onClick={() => onChange(rows.filter((_, rowIndex) => rowIndex !== index))}><X className="h-3.5 w-3.5" /></Button></div>)}</div> : <p className="text-xs text-muted-foreground">{tr("Не настроено", "Not configured")}</p>}
    </section>
  );
}
