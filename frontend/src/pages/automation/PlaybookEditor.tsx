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
}: PlaybookEditorProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const [yamlTab, setYamlTab] = useState<"working" | "original">("working");
  const [yamlDiagnostics, setYamlDiagnostics] = useState<CodeEditorDiagnostic[]>([]);
  const hasContent = Boolean(state.sourceYaml.trim());
  const hasSyntaxErrors = yamlDiagnostics.some((diagnostic) => diagnostic.severity === "error");
  const canSave = Boolean(state.name.trim()) && hasContent && !hasSyntaxErrors;
  const save = () => {
    if (canSave && dirty && !saving && !readOnly) onSave();
  };

  return (
    <section className="mx-auto w-full max-w-[1100px] space-y-4">
      <header className="flex flex-col gap-3 border-b border-border/70 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <Button size="icon" variant="ghost" className="h-9 w-9 shrink-0" onClick={onBack} aria-label={tr("Назад к Ansible", "Back to Ansible")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="font-display text-xl font-semibold text-foreground">{playbookId ? "Ansible" : tr("Создать Ansible", "Create Ansible")}</h1>
            <p className="mt-0.5 text-xs text-muted-foreground">{tr("Напишите или вставьте playbook. Импорт — вторичный способ.", "Write or paste a playbook. Import is optional.")}</p>
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
      </header>

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

      {hasContent ? (
        canValidate ? (
          <PlaybookCompatibilityPanel
            lang={lang}
            playbookId={playbookId}
            sourceYaml={state.sourceYaml}
            report={state.activeCompatibilityRevision?.report || state.compatibility}
            canAdapt={canAdapt}
            onApplied={onCompatibilityApplied}
            onSourceAccepted={(sourceYaml, compatibility) => onChange({ sourceYaml, compatibility })}
          />
        ) : (
          <InlineAlert tone="info" title={tr("AI-проверка недоступна", "AI check unavailable")} description={tr("У вас нет права проверять этот Ansible.", "You do not have permission to check this Ansible.")} />
        )
      ) : null}

      <footer className="flex flex-col-reverse gap-2 border-t border-border/70 pt-4 sm:flex-row sm:items-center sm:justify-end">
        <Button size="sm" variant="outline" className="h-9 gap-1.5" disabled={readOnly || !canSave || !dirty || saving} onClick={save}>
          {dirty ? <Save className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
          {saving ? tr("Сохраняем…", "Saving…") : dirty ? tr("Сохранить", "Save") : tr("Сохранено", "Saved")}
        </Button>
        <Button size="sm" className="h-9 gap-1.5 px-4" disabled={!playbookId || !canRun || !canSave || saving || dirty} onClick={onRun}>
          <Play className="h-3.5 w-3.5" />
          {tr("Выбрать серверы", "Choose servers")}
        </Button>
      </footer>
    </section>
  );
}
