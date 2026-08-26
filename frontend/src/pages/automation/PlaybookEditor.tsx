import { useState } from "react";
import { ArrowLeft, CheckCircle2, GitBranch, Play, Save, Upload } from "lucide-react";

import type { PlaybookDetail } from "@/api/playbooks";
import type { CodeEditorDiagnostic } from "@/components/editor/CodeEditor";
import { InlineAlert } from "@/components/system/InlineAlert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PlaybookCompatibilityPanel } from "./PlaybookCompatibilityPanel";
import type { PlaybookEditorState } from "./playbookEditorState";
import { PlaybookBundleContentWorkspace } from "./playbooks/PlaybookBundleContentWorkspace";
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
  onChange: (patch: Partial<PlaybookEditorState>) => void;
  onSave: () => void;
  onBack: () => void;
  onRun: () => void;
  playbookId: number | null;
  onCompatibilityApplied: (playbook: PlaybookDetail) => void;
  onImportYaml: () => void;
  onImportProject: () => void;
  embedded?: boolean;
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
  onChange,
  onSave,
  onBack,
  onRun,
  playbookId,
  onCompatibilityApplied,
  onImportYaml,
  onImportProject,
  embedded = false,
}: PlaybookEditorProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const [yamlTab, setYamlTab] = useState<"working" | "original" | "changes">("working");
  const [yamlDiagnostics, setYamlDiagnostics] = useState<CodeEditorDiagnostic[]>([]);
  const [compatibilityTarget, setCompatibilityTarget] = useState<{
    path: string;
    content: string;
    isEntrypoint: boolean;
    editable: boolean;
  } | null>({ path: "", content: "", isEntrypoint: true, editable: true });
  const hasContent = Boolean(state.sourceYaml.trim());
  const compatibilitySource = compatibilityTarget?.isEntrypoint ? state.sourceYaml : compatibilityTarget?.content || "";
  const hasSyntaxErrors = yamlDiagnostics.some((diagnostic) => diagnostic.severity === "error");
  const canSave = Boolean(state.name.trim()) && hasContent && !hasSyntaxErrors;
  const save = () => {
    if (canSave && dirty && !saving && !readOnly) onSave();
  };
  const yamlWorkspace = (
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
  );

  return (
    <section className={embedded ? "w-full space-y-4" : "mx-auto w-full max-w-[1100px] space-y-4"}>
      {!embedded ? <header className="flex flex-col gap-3 border-b border-border/70 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <Button size="icon" variant="ghost" className="h-9 w-9 shrink-0" onClick={onBack} aria-label={tr("Назад к Ansible", "Back to Ansible")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="font-display text-xl font-semibold text-foreground">{playbookId ? tr("Проект Ansible", "Ansible project") : tr("Новый проект", "New project")}</h1>
            <p className="mt-0.5 text-xs text-muted-foreground">{tr("Напишите или вставьте YAML либо импортируйте готовый проект.", "Write or paste YAML, or import an existing project.")}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" className="h-9 gap-1.5" onClick={onImportYaml} disabled={readOnly}>
            <Upload className="h-3.5 w-3.5" />{tr("Загрузить YAML", "Load YAML")}
          </Button>
          <Button size="sm" variant="ghost" className="h-9 gap-1.5" onClick={onImportProject} disabled={readOnly}>
            <GitBranch className="h-3.5 w-3.5" />{tr("GitLab или архив", "GitLab or archive")}
          </Button>
        </div>
      </header> : (
        <div className="flex flex-wrap justify-end gap-2">
          <Button size="sm" variant="ghost" className="h-8 gap-1.5" onClick={onImportYaml} disabled={readOnly}>
            <Upload className="h-3.5 w-3.5" />{tr("Загрузить YAML", "Load YAML")}
          </Button>
          <Button size="sm" variant="ghost" className="h-8 gap-1.5" onClick={onImportProject} disabled={readOnly}>
            <GitBranch className="h-3.5 w-3.5" />{tr("GitLab или архив", "GitLab or archive")}
          </Button>
        </div>
      )}

      {saveError ? <InlineAlert tone="danger" title={tr("Не удалось сохранить", "Could not save")} description={saveError} /> : null}

      <div className="space-y-1.5">
        <Label htmlFor="playbook-name">{tr("Название", "Name")}</Label>
        <Input
          id="playbook-name"
          className="max-w-xl bg-card"
          disabled={metadataReadOnly}
          value={state.name}
          placeholder={tr("Например, обновление веб-серверов", "For example, update web servers")}
          onChange={(event) => onChange({ name: event.target.value })}
        />
      </div>

      {compatibilitySource.trim() && compatibilityTarget?.editable ? (
        <section
          id="playbook-ai-adaptation"
          className="scroll-mt-[10rem]"
          aria-label={tr("ИИ-проверка и адаптация", "AI check and adaptation")}
        >
          {canValidate ? (
            <PlaybookCompatibilityPanel
              lang={lang}
              playbookId={playbookId}
              sourcePath={compatibilityTarget.path || undefined}
              sourceYaml={compatibilitySource}
              report={state.activeCompatibilityRevision?.report || state.compatibility}
              canAdapt={canAdapt}
              onApplied={onCompatibilityApplied}
              onSourceAccepted={(sourceYaml, compatibility) => {
                if (compatibilityTarget.isEntrypoint) onChange({ sourceYaml, compatibility });
              }}
            />
          ) : (
            <InlineAlert tone="info" title={tr("ИИ-проверка недоступна", "AI check unavailable")} description={tr("У вас нет права проверять этот проект.", "You do not have permission to check this project.")} />
          )}
        </section>
      ) : null}

      {playbookId ? (
        <PlaybookBundleContentWorkspace
          lang={lang}
          playbookId={playbookId}
          readOnly={readOnly}
          entrypointEditor={yamlWorkspace}
          onCompatibilityTargetChange={setCompatibilityTarget}
        />
      ) : yamlWorkspace}

      {!embedded ? <footer className="flex flex-col-reverse gap-2 border-t border-border/70 pt-4 sm:flex-row sm:items-center sm:justify-end">
        <Button size="sm" variant="outline" className="h-9 gap-1.5" disabled={readOnly || !canSave || !dirty || saving} onClick={save}>
          {dirty ? <Save className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
          {saving ? tr("Сохраняем…", "Saving…") : dirty ? tr("Сохранить", "Save") : tr("Сохранено", "Saved")}
        </Button>
        <Button size="sm" className="h-9 gap-1.5 px-4" disabled={!playbookId || !canRun || !canSave || saving || dirty} onClick={onRun}>
          <Play className="h-3.5 w-3.5" />
          {tr("Выбрать серверы", "Choose servers")}
        </Button>
      </footer> : null}
    </section>
  );
}
