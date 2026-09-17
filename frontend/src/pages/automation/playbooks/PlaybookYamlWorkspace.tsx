import { AlertTriangle, CheckCircle2, FileCode2 } from "lucide-react";

import { CodeEditor, type CodeEditorDiagnostic } from "@/components/editor/CodeEditor";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import type { PlaybookEditorState } from "../playbookEditorState";

interface PlaybookYamlWorkspaceProps {
  tr: (ru: string, en: string) => string;
  state: PlaybookEditorState;
  readOnly: boolean;
  yamlTab: "working" | "original" | "changes";
  diagnostics: CodeEditorDiagnostic[];
  onYamlTabChange: (tab: "working" | "original" | "changes") => void;
  onSourceChange: (sourceYaml: string) => void;
  onSave: () => void;
  onDiagnosticsChange: (diagnostics: CodeEditorDiagnostic[]) => void;
}

export function PlaybookYamlWorkspace({
  tr,
  state,
  readOnly,
  yamlTab,
  diagnostics,
  onYamlTabChange,
  onSourceChange,
  onSave,
  onDiagnosticsChange,
}: PlaybookYamlWorkspaceProps) {
  const syntaxErrors = diagnostics.filter((diagnostic) => diagnostic.severity === "error");

  return (
    <section className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1">
      <Tabs value={yamlTab} onValueChange={(value) => onYamlTabChange(value as "working" | "original" | "changes")}>
        <div className="flex flex-col gap-3 border-b border-border bg-surface-2/30 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <FileCode2 className="h-4 w-4 text-primary" />
              <h3 className="text-sm font-semibold text-foreground">
                {tr("Исполняемый Ansible YAML", "Executable Ansible YAML")}
              </h3>
            </div>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              {tr(
                "Редактируйте рабочую копию; оригинал всегда остаётся неизменным.",
                "Edit the working copy while the original remains immutable.",
              )}
            </p>
          </div>
          <TabsList aria-label={tr("Версии YAML", "YAML versions")} className="w-full sm:w-auto">
            <TabsTrigger value="working" className="flex-1 sm:flex-none">
              {tr("Рабочая копия", "Working copy")}
            </TabsTrigger>
            <TabsTrigger value="original" disabled={!state.originalSourceYaml} className="flex-1 sm:flex-none">
              {tr("Оригинал", "Original")}
            </TabsTrigger>
            <TabsTrigger value="changes" disabled={!state.originalSourceYaml} className="flex-1 sm:flex-none">
              {tr("Изменения", "Changes")}
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="working" className="m-0">
          <div className="h-[min(66vh,720px)] min-h-[520px] bg-terminal-bg">
            <CodeEditor
              content={state.sourceYaml}
              filename="playbook.yml"
              ariaLabel={tr("Редактор рабочего Ansible YAML", "Working Ansible YAML editor")}
              onChange={onSourceChange}
              onSave={onSave}
              onDiagnosticsChange={onDiagnosticsChange}
              readOnly={readOnly}
            />
          </div>
        </TabsContent>
        <TabsContent value="original" className="m-0">
          <div className="h-[min(66vh,720px)] min-h-[520px] bg-terminal-bg">
            <CodeEditor
              content={state.originalSourceYaml}
              filename="original-playbook.yml"
              ariaLabel={tr("Оригинальный Ansible YAML, только чтение", "Original Ansible YAML, read only")}
              readOnly
            />
          </div>
        </TabsContent>
        <TabsContent value="changes" className="m-0">
          <YamlChanges before={state.originalSourceYaml} after={state.sourceYaml} tr={tr} />
        </TabsContent>

        <div
          role="status"
          aria-live="polite"
          className={cn(
            "border-t px-4 py-2.5 text-xs",
            syntaxErrors.length ? "border-destructive/25 bg-destructive/5" : "border-border bg-surface-2/25",
          )}
        >
          {yamlTab === "original" ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <FileCode2 className="h-3.5 w-3.5" />
              {tr("Неизменяемый исходник · только чтение", "Immutable source · read only")}
            </div>
          ) : yamlTab === "changes" ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <FileCode2 className="h-3.5 w-3.5" />
              {tr("Сравнение оригинала с рабочей копией", "Original compared with working copy")}
            </div>
          ) : syntaxErrors.length ? (
            <div>
              <div className="flex items-center gap-2 font-medium text-destructive">
                <AlertTriangle className="h-3.5 w-3.5" />
                {tr("Ошибки синтаксиса YAML", "YAML syntax errors")}
              </div>
              <ul className="mt-2 space-y-1 pl-5 text-destructive">
                {syntaxErrors.slice(0, 6).map((diagnostic, index) => (
                  <li key={`${diagnostic.from}-${diagnostic.to}-${index}`}>
                    {tr("Строка", "Line")} {diagnostic.line}, {tr("столбец", "column")} {diagnostic.column}: {diagnostic.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-2 text-muted-foreground">
              <span className="inline-flex items-center gap-2 text-success">
                <CheckCircle2 className="h-3.5 w-3.5" />
                {tr("Синтаксических ошибок не найдено", "No syntax errors found")}
              </span>
              <span>{tr("Ctrl/Cmd+S · поиск · сворачивание", "Ctrl/Cmd+S · search · folding")}</span>
            </div>
          )}
        </div>
      </Tabs>
    </section>
  );
}

function YamlChanges({
  before,
  after,
  tr,
}: {
  before: string;
  after: string;
  tr: (ru: string, en: string) => string;
}) {
  if (before === after) {
    return (
      <div className="flex h-[min(66vh,720px)] min-h-[520px] items-center justify-center bg-terminal-bg p-6 text-sm text-muted-foreground">
        {tr("Рабочая копия совпадает с оригиналом.", "The working copy matches the original.")}
      </div>
    );
  }
  return (
    <div className="h-[min(66vh,720px)] min-h-[520px] overflow-auto bg-terminal-bg p-4 font-mono text-xs leading-5" role="region" aria-label={tr("Изменения YAML", "YAML changes")}>
      <p className="mb-3 font-sans text-xs text-muted-foreground">{tr("Неизменяемый оригинал → рабочая копия", "Immutable original → working copy")}</p>
      <pre className="whitespace-pre-wrap text-destructive">{before.split("\n").map((line) => `- ${line}`).join("\n")}</pre>
      <pre className="mt-3 whitespace-pre-wrap text-success">{after.split("\n").map((line) => `+ ${line}`).join("\n")}</pre>
    </div>
  );
}
