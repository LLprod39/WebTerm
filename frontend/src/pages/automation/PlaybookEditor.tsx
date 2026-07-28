import { useState } from "react";
import { ArrowLeft, CheckCircle2, FileCode2, Play, Save, Settings2, ShieldCheck } from "lucide-react";

import type { PlaybookDetail } from "@/api/playbooks";
import type { CodeEditorDiagnostic } from "@/components/editor/CodeEditor";
import { InlineAlert } from "@/components/system/InlineAlert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { PlaybookCompatibilityPanel } from "./PlaybookCompatibilityPanel";
import { isSourceBackedPlaybook, type PlaybookEditorState } from "./playbookEditorState";
import { PlaybookEditorInspector } from "./playbooks/PlaybookEditorInspector";
import { PlaybookRunbookWorkspace } from "./playbooks/PlaybookRunbookWorkspace";
import { PlaybookYamlWorkspace } from "./playbooks/PlaybookYamlWorkspace";

export type { PlaybookEditorState } from "./playbookEditorState";

interface PlaybookEditorProps {
  lang: string;
  state: PlaybookEditorState;
  saving: boolean;
  dirty: boolean;
  saveError?: string | null;
  readOnly?: boolean;
  metadataReadOnly?: boolean;
  canRun?: boolean;
  canValidate?: boolean;
  canAdapt?: boolean;
  publishedRevisionNumber?: number | null;
  hasUnpublishedRevision?: boolean;
  onChange: (patch: Partial<PlaybookEditorState>) => void;
  onSave: () => void;
  onBack: () => void;
  onRun: () => void;
  title: string;
  playbookId: number | null;
  onCompatibilityApplied: (playbook: PlaybookDetail) => void;
}

export function PlaybookEditor({
  lang,
  state,
  saving,
  dirty,
  saveError,
  readOnly = false,
  metadataReadOnly = readOnly,
  canRun = true,
  canValidate = true,
  canAdapt = true,
  publishedRevisionNumber,
  hasUnpublishedRevision = false,
  onChange,
  onSave,
  onBack,
  onRun,
  playbookId,
  onCompatibilityApplied,
}: PlaybookEditorProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const yamlMode = isSourceBackedPlaybook(state);
  const [yamlTab, setYamlTab] = useState<"working" | "original">("working");
  const [yamlDiagnostics, setYamlDiagnostics] = useState<CodeEditorDiagnostic[]>([]);
  const hasContent = yamlMode
    ? Boolean(state.sourceYaml.trim())
    : state.tasks.some((task) => Boolean(String(task?.command ?? "").trim()));
  const hasSyntaxErrors = yamlMode && yamlDiagnostics.some((diagnostic) => diagnostic.severity === "error");
  const canSave = Boolean(String(state.name ?? "").trim()) && hasContent && !hasSyntaxErrors;
  const save = () => {
    if (canSave && dirty && !saving && !readOnly) onSave();
  };
  const saveLabel = readOnly
    ? tr("Только чтение", "Read only")
    : saving
      ? tr("Сохраняем…", "Saving…")
      : dirty
        ? tr("Не сохранено", "Not saved")
        : tr("Сохранено", "Saved");

  return (
    <section className="space-y-3">
      <header className="flex flex-col gap-3 rounded-sm border border-border bg-card px-4 py-3 shadow-elev-1 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <Button size="icon" variant="ghost" className="h-9 w-9 shrink-0" onClick={onBack} aria-label={tr("Назад к Ansible", "Back to Ansible")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="min-w-0">
            <h1 className="truncate font-display text-xl font-semibold text-foreground">{state.name || tr("Новый playbook", "New playbook")}</h1>
            <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground" role="status" aria-live="polite">
              <span className={dirty || saveError ? "text-warning" : "text-success"}>{saveError ? tr("Ошибка сохранения", "Save failed") : saveLabel}</span>
              {publishedRevisionNumber ? <span>· {tr("Запуск использует версию", "Runs use version")} #{publishedRevisionNumber}</span> : null}
              {hasUnpublishedRevision ? <span>· {tr("есть новая версия", "new version available")}</span> : null}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label={tr("Действия playbook", "Playbook actions")}>
          <Button size="sm" variant="outline" className="h-9 gap-1.5" disabled={readOnly || !canSave || !dirty || saving} onClick={save}>
            {dirty ? <Save className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
            {readOnly ? tr("Только чтение", "Read only") : saving ? tr("Сохраняем…", "Saving…") : dirty ? tr("Сохранить", "Save") : tr("Сохранено", "Saved")}
          </Button>
          <Button size="sm" className="h-9 gap-1.5 px-4" disabled={!canRun || !canSave || saving} onClick={onRun}>
            <Play className="h-3.5 w-3.5" />
            {publishedRevisionNumber ? tr("Запустить", "Run") : tr("Подготовить запуск…", "Prepare run…")}
          </Button>
        </div>
      </header>

      {saveError ? <InlineAlert tone="danger" title={tr("Не удалось сохранить", "Could not save")} description={saveError} /> : null}

      <Tabs defaultValue="playbook" className="space-y-3">
        <TabsList aria-label={tr("Разделы playbook", "Playbook sections")} className="h-auto w-full justify-start overflow-x-auto rounded-sm border border-border bg-card p-1 sm:w-auto">
          <TabsTrigger value="playbook" className="min-h-9 gap-1.5"><FileCode2 className="h-3.5 w-3.5" />Playbook</TabsTrigger>
          {yamlMode ? <TabsTrigger value="check" className="min-h-9 gap-1.5"><ShieldCheck className="h-3.5 w-3.5" />{tr("Проверка", "Check")}</TabsTrigger> : null}
          <TabsTrigger value="settings" className="min-h-9 gap-1.5"><Settings2 className="h-3.5 w-3.5" />{tr("Настройки", "Settings")}</TabsTrigger>
        </TabsList>

        <TabsContent value="playbook" className="m-0">
          {yamlMode ? (
            <PlaybookYamlWorkspace
              tr={tr}
              state={state}
              readOnly={readOnly}
              yamlTab={yamlTab}
              diagnostics={yamlDiagnostics}
              onYamlTabChange={setYamlTab}
              onSourceChange={(sourceYaml) => onChange({ sourceYaml })}
              onSave={save}
              onDiagnosticsChange={setYamlDiagnostics}
            />
          ) : (
            <PlaybookRunbookWorkspace tr={tr} state={state} readOnly={readOnly} onChange={onChange} />
          )}
        </TabsContent>

        {yamlMode ? (
          <TabsContent value="check" className="m-0">
            {dirty ? (
              <InlineAlert
                tone="warning"
                title={tr("Сначала сохраните изменения", "Save changes first")}
                description={tr("Проверка должна использовать сохранённый YAML.", "The check must use saved YAML.")}
              />
            ) : canValidate ? (
              <PlaybookCompatibilityPanel
                lang={lang}
                playbookId={playbookId}
                sourceYaml={state.sourceYaml}
                report={state.activeCompatibilityRevision?.report || state.compatibility}
                activeRevision={state.activeCompatibilityRevision}
                canAdapt={canAdapt}
                onApplied={onCompatibilityApplied}
              />
            ) : (
              <InlineAlert tone="info" title={tr("Проверка недоступна", "Check unavailable")} description={tr("У вас нет права на проверку этого playbook.", "You do not have permission to validate this playbook.")} />
            )}
          </TabsContent>
        ) : null}

        <TabsContent value="settings" className="m-0">
          <section className="space-y-4 rounded-sm border border-border bg-card p-4 shadow-elev-1">
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="playbook-name">{tr("Название", "Name")} *</Label>
                <Input id="playbook-name" disabled={metadataReadOnly} value={state.name} onChange={(event) => onChange({ name: event.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="playbook-description">{tr("Краткое описание", "Short description")}</Label>
                <Textarea id="playbook-description" disabled={metadataReadOnly} rows={2} value={state.description} onChange={(event) => onChange({ description: event.target.value })} />
              </div>
            </div>
            <PlaybookEditorInspector lang={lang} state={state} yamlMode={yamlMode} metadataReadOnly={metadataReadOnly} onChange={onChange} />
          </section>
        </TabsContent>
      </Tabs>
    </section>
  );
}
