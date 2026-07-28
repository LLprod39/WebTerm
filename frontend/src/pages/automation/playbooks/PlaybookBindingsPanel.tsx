import { useState } from "react";
import { KeyRound, Link2, Loader2, Plus, Settings2, Trash2 } from "lucide-react";

import type { PlaybookBindingProfile, PlaybookInventoryBindings } from "@/api/playbooks";
import { ConfirmDialog } from "@/components/system/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { PlaybookWorkspaceVersioningController } from "./usePlaybookWorkspaceVersioning";

interface PlaybookBindingsPanelProps {
  lang: string;
  workspace: PlaybookWorkspaceVersioningController;
}

function objectFromJson(value: string, label: string): Record<string, unknown> {
  const parsed = JSON.parse(value || "{}");
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error(`${label} must be a JSON object`);
  return parsed as Record<string, unknown>;
}

export function PlaybookBindingsPanel({ lang, workspace }: PlaybookBindingsPanelProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState<PlaybookBindingProfile | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PlaybookBindingProfile | null>(null);
  const [name, setName] = useState("");
  const [selectorText, setSelectorText] = useState("{}");
  const [variablesText, setVariablesText] = useState("{}");
  const [secretName, setSecretName] = useState("");
  const [secretValue, setSecretValue] = useState("");
  const [concurrency, setConcurrency] = useState(4);
  const [become, setBecome] = useState(true);
  const [dryRun, setDryRun] = useState(false);
  const [isDefault, setIsDefault] = useState(false);
  const [formError, setFormError] = useState("");

  if (!workspace.bindingsAccessible) return null;

  const edit = (profile?: PlaybookBindingProfile) => {
    setCurrent(profile || null);
    setName(profile?.name || "");
    setSelectorText(JSON.stringify(profile?.selector_mappings || {}, null, 2));
    setVariablesText(JSON.stringify(profile?.variable_values || {}, null, 2));
    setSecretName("");
    setSecretValue("");
    setConcurrency(profile?.options.concurrency || 4);
    setBecome(profile?.options.become ?? true);
    setDryRun(profile?.options.dry_run ?? false);
    setIsDefault(profile?.is_default || false);
    setFormError("");
    setOpen(true);
  };

  const close = () => {
    setSecretName("");
    setSecretValue("");
    setOpen(false);
  };

  const save = async () => {
    setFormError("");
    try {
      const selectorMappings = objectFromJson(selectorText, "selector_mappings") as PlaybookInventoryBindings;
      const variableValues = objectFromJson(variablesText, "variable_values");
      const saved = await workspace.saveBinding(
        {
          name: name.trim(),
          selector_mappings: selectorMappings,
          variable_values: variableValues,
          ...(secretName.trim() && secretValue
            ? { secret_values: { [secretName.trim()]: secretValue } }
            : {}),
          options: { concurrency, become, dry_run: dryRun },
          is_default: isDefault,
        },
        current,
      );
      if (saved) {
        close();
      }
    } catch (error) {
      setFormError(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <section className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1" aria-labelledby="bindings-panel-title">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <div className="flex items-center gap-2">
            <Link2 className="h-4 w-4 text-primary" />
            <h3 id="bindings-panel-title" className="text-sm font-semibold text-foreground">
              {tr("Мои профили запуска", "My run profiles")}
            </h3>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {tr(
              "Привязки принадлежат только вам. Секретные значения сохраняются отдельно и никогда не показываются снова.",
              "Bindings belong only to you. Secret values are stored separately and are never displayed again.",
            )}
          </p>
        </div>
        <Button size="sm" variant="outline" className="gap-1.5" onClick={() => edit()}>
          <Plus className="h-3.5 w-3.5" />
          {tr("Новый профиль", "New profile")}
        </Button>
      </div>

      <div className="divide-y divide-border">
        {workspace.bindings.length ? (
          workspace.bindings.map((profile) => (
            <div key={profile.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <button type="button" className="min-w-0 flex-1 text-left" onClick={() => edit(profile)}>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-foreground">{profile.name}</span>
                  {profile.is_default ? (
                    <span className="rounded-sm bg-primary/10 px-1.5 py-0.5 text-2xs text-primary">{tr("По умолчанию", "Default")}</span>
                  ) : null}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {Object.keys(profile.selector_mappings).length} {tr("селекторов", "selectors")} · v{profile.version}
                  {profile.secret_variables.length ? ` · ${profile.secret_variables.length} ${tr("секретов", "secrets")}` : ""}
                </p>
                {profile.secret_variables.length ? (
                  <div className="mt-1 flex flex-wrap gap-1" aria-label={tr("Настроенные секреты", "Configured secrets")}>
                    {profile.secret_variables.map((secret) => (
                      <span key={secret} className="inline-flex items-center gap-1 text-2xs text-muted-foreground">
                        <KeyRound className="h-3 w-3" /> {secret}: {tr("настроен", "configured")}
                      </span>
                    ))}
                  </div>
                ) : null}
              </button>
              <Button size="sm" variant="ghost" className="h-8 gap-1" onClick={() => edit(profile)}>
                <Settings2 className="h-3.5 w-3.5" />
                {tr("Изменить", "Edit")}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-8 text-destructive hover:text-destructive"
                aria-label={tr(`Удалить профиль ${profile.name}`, `Delete profile ${profile.name}`)}
                onClick={() => setDeleteTarget(profile)}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))
        ) : (
          <div className="px-4 py-6 text-center text-sm text-muted-foreground">
            {tr("Сохранённых профилей пока нет", "No saved profiles yet")}
          </div>
        )}
      </div>

      <Dialog open={open} onOpenChange={(next) => (next ? setOpen(true) : close())}>
        <DialogContent className="max-w-2xl" closeLabel={tr("Закрыть", "Close")}>
          <DialogHeader>
            <DialogTitle>{current ? tr("Изменить профиль", "Edit profile") : tr("Новый профиль запуска", "New run profile")}</DialogTitle>
            <DialogDescription>
              {tr("Используйте IDs доступных серверов и групп из inventory.", "Use IDs of servers and groups available in your inventory.")}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="max-h-[70vh] space-y-4 overflow-auto">
            <div className="space-y-1.5">
              <Label htmlFor="binding-name">{tr("Название", "Name")}</Label>
              <Input id="binding-name" value={name} onChange={(event) => setName(event.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="binding-selectors">selector_mappings JSON</Label>
              <Textarea id="binding-selectors" value={selectorText} onChange={(event) => setSelectorText(event.target.value)} className="min-h-32 font-mono text-xs" />
              <p className="text-2xs text-muted-foreground">{`{"web":{"server_ids":[1],"group_ids":[]}}`}</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="binding-variables">variable_values JSON</Label>
              <Textarea id="binding-variables" value={variablesText} onChange={(event) => setVariablesText(event.target.value)} className="min-h-24 font-mono text-xs" />
            </div>
            <div className="rounded-sm border border-border bg-surface-0 p-3">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <KeyRound className="h-4 w-4 text-primary" />
                {tr("Добавить или заменить один секрет", "Add or replace one secret")}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {tr("Существующие значения не загружаются в браузер.", "Existing values are never loaded into the browser.")}
              </p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <Input value={secretName} onChange={(event) => setSecretName(event.target.value)} placeholder={tr("Имя переменной", "Variable name")} aria-label={tr("Имя секретной переменной", "Secret variable name")} />
                <Input type="password" value={secretValue} onChange={(event) => setSecretValue(event.target.value)} placeholder={tr("Новое значение", "New value")} aria-label={tr("Новое секретное значение", "New secret value")} autoComplete="new-password" />
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="binding-concurrency">{tr("Параллельность", "Concurrency")}</Label>
                <Input id="binding-concurrency" type="number" min={1} max={12} value={concurrency} onChange={(event) => setConcurrency(Number(event.target.value) || 1)} />
              </div>
              <label className="flex items-center gap-2 self-end pb-2 text-sm text-muted-foreground">
                <Checkbox checked={become} onCheckedChange={(checked) => setBecome(checked === true)} /> become
              </label>
              <label className="flex items-center gap-2 self-end pb-2 text-sm text-muted-foreground">
                <Checkbox checked={dryRun} onCheckedChange={(checked) => setDryRun(checked === true)} /> dry-run
              </label>
            </div>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <Checkbox checked={isDefault} onCheckedChange={(checked) => setIsDefault(checked === true)} />
              {tr("Использовать по умолчанию", "Use by default")}
            </label>
            {current?.secret_variables.length ? (
              <p className="text-xs text-muted-foreground">
                {tr("Уже настроены", "Already configured")}: {current.secret_variables.join(", ")}. {tr("Значения скрыты.", "Values are hidden.")}
              </p>
            ) : null}
            {formError ? <p role="alert" className="text-xs text-destructive">{formError}</p> : null}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={close}>{tr("Отмена", "Cancel")}</Button>
            <Button disabled={workspace.bindingBusy || !name.trim()} onClick={() => void save()}>
              {workspace.bindingBusy ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : null}
              {tr("Сохранить профиль", "Save profile")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(next) => !next && setDeleteTarget(null)}
        title={tr("Удалить профиль?", "Delete profile?")}
        description={deleteTarget ? tr(`Профиль «${deleteTarget.name}» будет удалён.`, `Profile “${deleteTarget.name}” will be deleted.`) : ""}
        confirmLabel={tr("Удалить", "Delete")}
        cancelLabel={tr("Отмена", "Cancel")}
        tone="destructive"
        onConfirm={async () => {
          if (deleteTarget) await workspace.removeBinding(deleteTarget.id);
          setDeleteTarget(null);
        }}
      />
    </section>
  );
}
