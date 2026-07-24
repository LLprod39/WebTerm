import { useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, FileCode2, GripVertical, Plus, Save, X } from "lucide-react";
import type {
  PlaybookCategory,
  PlaybookDetail,
  PlaybookTask,
  PlaybookVisibility,
} from "@/api/playbooks";
import { CodeEditor, type CodeEditorDiagnostic } from "@/components/editor/CodeEditor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { CATEGORIES, CATEGORY_META, newLocalTaskId } from "./constants";
import { PlaybookCompatibilityPanel } from "./PlaybookCompatibilityPanel";
import { isSourceBackedPlaybook, type PlaybookEditorState } from "./playbookEditorState";

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
  onChange,
  onSave,
  onBack,
  onRun,
  title,
  playbookId,
  onCompatibilityApplied,
}: PlaybookEditorProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const yamlMode = isSourceBackedPlaybook(state);
  const [yamlTab, setYamlTab] = useState<"working" | "original">("working");
  const [yamlDiagnostics, setYamlDiagnostics] = useState<CodeEditorDiagnostic[]>([]);

  const updateTask = (id: string, patch: Partial<PlaybookTask>) => {
    onChange({
      tasks: state.tasks.map((task) => (task.id === id ? { ...task, ...patch } : task)),
    });
  };

  const addTask = () => {
    onChange({
      tasks: [
        ...state.tasks,
        { id: newLocalTaskId(), command: "", description: "", continue_on_error: false },
      ],
    });
  };

  const removeTask = (id: string) => {
    onChange({ tasks: state.tasks.filter((task) => task.id !== id) });
  };

  const moveTask = (idx: number, dir: -1 | 1) => {
    const next = [...state.tasks];
    const target = idx + dir;
    if (target < 0 || target >= next.length) return;
    [next[idx], next[target]] = [next[target], next[idx]];
    onChange({ tasks: next });
  };

  const hasContent = yamlMode
    ? Boolean(state.sourceYaml.trim())
    : state.tasks.some((task) => Boolean(String(task?.command ?? "").trim()));
  const hasSyntaxErrors = yamlMode && yamlDiagnostics.some((diagnostic) => diagnostic.severity === "error");
  const canSave = Boolean(String(state.name ?? "").trim()) && hasContent && !hasSyntaxErrors;
  const save = () => {
    if (canSave && dirty && !saving && !readOnly) onSave();
  };

  const saveStatus = saving
    ? tr("Сохранение…", "Saving…")
    : readOnly
      ? tr("Только чтение", "Read only")
      : saveError
      ? tr("Ошибка сохранения", "Save failed")
      : dirty
        ? tr("Есть несохранённые изменения", "Unsaved changes")
        : playbookId
          ? tr("Сохранено", "Saved")
          : tr("Новый playbook", "New playbook");

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            className="h-9 px-2"
            onClick={onBack}
            aria-label={tr("Вернуться в каталог playbook", "Back to playbook catalog")}
          >
            ← {tr("Каталог", "Catalog")}
          </Button>
          <div>
            <h2 className="font-display text-lg font-semibold text-foreground">{title}</h2>
            <p
              role="status"
              aria-live="polite"
              className={`text-xs ${saveError ? "text-destructive" : dirty ? "text-amber-400" : "text-muted-foreground"}`}
            >
              {saveStatus}
              {saveError ? `: ${saveError}` : ""}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2" role="toolbar" aria-label={tr("Действия редактора", "Editor actions")}>
          <Button
            size="sm"
            variant="outline"
            className="h-9 gap-1.5"
            disabled={readOnly || !canSave || !dirty || saving}
            onClick={save}
          >
            {saving ? <span className="h-3.5 w-3.5 animate-pulse rounded-full bg-current" /> : dirty ? <Save className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
            {readOnly ? tr("Только чтение", "Read only") : saving ? tr("Сохранение…", "Saving…") : dirty ? tr("Сохранить", "Save") : tr("Сохранено", "Saved")}
          </Button>
          <Button size="sm" className="h-9 gap-1.5 shadow-elev-1" disabled={!canRun || !canSave || saving} onClick={onRun}>
            {tr("Запустить…", "Run…")}
          </Button>
        </div>
      </div>

      <div className="rounded-sm border border-border bg-card p-4 shadow-elev-1">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="playbook-name" className="text-2xs uppercase tracking-wider text-muted-foreground">
              {tr("Имя", "Name")} *
            </Label>
            <Input
              id="playbook-name"
              disabled={metadataReadOnly}
              value={state.name}
              onChange={(event) => onChange({ name: event.target.value })}
              placeholder={tr("например, Reload nginx fleet", "e.g. Reload nginx fleet")}
              className="h-10 bg-surface-0"
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="playbook-description" className="text-2xs uppercase tracking-wider text-muted-foreground">
              {tr("Описание", "Description")}
            </Label>
            <Textarea
              id="playbook-description"
              disabled={metadataReadOnly}
              value={state.description}
              onChange={(event) => onChange({ description: event.target.value })}
              placeholder={tr("Что делает этот playbook и когда его запускать", "What it does and when to run it")}
              className="min-h-[72px] bg-surface-0"
            />
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-4">
          {yamlMode ? (
            <>
              <div className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1">
                <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <FileCode2 className="h-4 w-4 text-primary" />
                      <h3 className="text-sm font-semibold text-foreground">
                        {tr("Исполняемый Ansible YAML", "Executable Ansible YAML")}
                      </h3>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {tr(
                        "Рабочая версия — единственный источник выполнения. Сохранение сбрасывает устаревшую compatibility-ревизию.",
                        "The working copy is the only execution source. Saving invalidates a stale compatibility revision.",
                      )}
                    </p>
                  </div>
                  <div role="tablist" aria-label={tr("Версии YAML", "YAML versions")} className="flex gap-1 rounded-sm bg-surface-0 p-1">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={yamlTab === "working"}
                      className={`rounded-sm px-2.5 py-1.5 text-xs ${yamlTab === "working" ? "bg-card text-foreground shadow-elev-1" : "text-muted-foreground"}`}
                      onClick={() => setYamlTab("working")}
                    >
                      {tr("Рабочая версия", "Working copy")}
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={yamlTab === "original"}
                      disabled={!state.originalSourceYaml}
                      className={`rounded-sm px-2.5 py-1.5 text-xs disabled:opacity-40 ${yamlTab === "original" ? "bg-card text-foreground shadow-elev-1" : "text-muted-foreground"}`}
                      onClick={() => setYamlTab("original")}
                    >
                      {tr("Оригинал", "Original")}
                    </button>
                  </div>
                </div>

                <div className="h-[480px] bg-[#0d1117]">
                  {yamlTab === "working" ? (
                    <CodeEditor
                      content={state.sourceYaml}
                      filename="playbook.yml"
                      ariaLabel={tr("Редактор рабочего Ansible YAML", "Working Ansible YAML editor")}
                      onChange={(sourceYaml) => onChange({ sourceYaml })}
                      onSave={save}
                      onDiagnosticsChange={setYamlDiagnostics}
                      readOnly={readOnly}
                    />
                  ) : (
                    <CodeEditor
                      content={state.originalSourceYaml}
                      filename="original-playbook.yml"
                      ariaLabel={tr("Оригинальный Ansible YAML, только чтение", "Original Ansible YAML, read only")}
                      readOnly
                    />
                  )}
                </div>

                <div className="border-t border-border px-4 py-2 text-xs text-muted-foreground">
                  {yamlTab === "original"
                    ? tr("Снимок с сервера при открытии редактора · только чтение", "Server snapshot captured when the editor opened · read only")
                    : tr("YAML · Ctrl/Cmd+S сохранить · поиск и сворачивание доступны", "YAML · Ctrl/Cmd+S to save · search and folding available")}
                </div>
              </div>

              <div
                role="status"
                aria-live="polite"
                className={`rounded-sm border p-3 text-xs ${hasSyntaxErrors ? "border-destructive/30 bg-destructive/5" : "border-border bg-card"}`}
              >
                <div className="flex items-center gap-2 font-medium text-foreground">
                  {hasSyntaxErrors ? <AlertTriangle className="h-4 w-4 text-destructive" /> : <CheckCircle2 className="h-4 w-4 text-emerald-400" />}
                  {hasSyntaxErrors
                    ? tr("Ошибки синтаксиса YAML", "YAML syntax errors")
                    : tr("Синтаксических ошибок не найдено", "No syntax errors found")}
                </div>
                {hasSyntaxErrors ? (
                  <ul className="mt-2 space-y-1 pl-6 text-destructive">
                    {yamlDiagnostics.slice(0, 6).map((diagnostic, index) => (
                      <li key={`${diagnostic.from}-${diagnostic.to}-${index}`}>
                        {tr("Строка", "Line")} {diagnostic.line}, {tr("столбец", "column")} {diagnostic.column}: {diagnostic.message}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>

              <div className="rounded-sm border border-border bg-card p-4 shadow-elev-1">
                <h3 className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">
                  {tr("Производный outline · только чтение", "Derived outline · read only")} ({state.tasks.length})
                </h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  {tr(
                    "Эти строки помогают ориентироваться и не являются отдельным исполняемым списком команд.",
                    "These rows are only a navigation aid, not a separately executable command list.",
                  )}
                </p>
                <ol className="mt-3 space-y-2">
                  {state.tasks.filter((task) => task.description || task.command).map((task, index) => (
                    <li key={task.id} className="rounded-sm border border-border bg-surface-0/60 px-3 py-2 text-xs">
                      <span className="mr-2 font-mono text-muted-foreground">#{index + 1}</span>
                      <span className="text-foreground">{task.description || task.command}</span>
                    </li>
                  ))}
                </ol>
              </div>

              {dirty ? (
                <div className="rounded-sm border border-amber-500/25 bg-amber-500/5 p-3 text-xs text-muted-foreground">
                  {tr(
                    "Сначала сохраните YAML, затем запускайте проверку или адаптацию — так они будут работать с этой версией.",
                    "Save the YAML before compatibility checks or adaptation so they use this exact version.",
                  )}
                </div>
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
              ) : null}
            </>
          ) : (
            <div className="rounded-sm border border-border bg-card p-4 shadow-elev-1 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">
                    {tr("Runbook задачи", "Runbook tasks")} ({state.tasks.length})
                  </h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {tr("Этот список — исполняемый источник runbook.", "This structured list is the runbook execution source.")}
                  </p>
                </div>
                <Button size="sm" variant="outline" className="h-8 gap-1" disabled={readOnly} onClick={addTask}>
                  <Plus className="h-3.5 w-3.5" />
                  {tr("Добавить", "Add")}
                </Button>
              </div>
              <div className="space-y-2">
                {state.tasks.map((task, idx) => (
                  <div key={task.id} className="flex items-start gap-2 rounded-sm border border-border bg-surface-0/60 p-3">
                    <div className="flex shrink-0 flex-col items-center gap-1 pt-1">
                      <button
                        type="button"
                        aria-label={tr(`Переместить задачу ${idx + 1} вверх`, `Move task ${idx + 1} up`)}
                        className="flex h-7 w-7 items-center justify-center rounded-sm text-muted-foreground hover:bg-secondary disabled:opacity-20"
                        disabled={readOnly || idx === 0}
                        onClick={() => moveTask(idx, -1)}
                      >
                        <ChevronDown className="h-3 w-3 rotate-180" />
                      </button>
                      <GripVertical className="h-3 w-3 text-muted-foreground/40" aria-hidden="true" />
                      <button
                        type="button"
                        aria-label={tr(`Переместить задачу ${idx + 1} вниз`, `Move task ${idx + 1} down`)}
                        className="flex h-7 w-7 items-center justify-center rounded-sm text-muted-foreground hover:bg-secondary disabled:opacity-20"
                        disabled={readOnly || idx === state.tasks.length - 1}
                        onClick={() => moveTask(idx, 1)}
                      >
                        <ChevronDown className="h-3 w-3" />
                      </button>
                    </div>
                    <div className="min-w-0 flex-1 space-y-2">
                      <div className="flex items-center gap-2">
                        <span className="shrink-0 rounded-sm bg-secondary px-1.5 py-0.5 font-mono text-2xs text-muted-foreground">
                          #{idx + 1}
                        </span>
                        <Input
                          value={task.description}
                          disabled={readOnly}
                          aria-label={tr(`Описание задачи ${idx + 1}`, `Task ${idx + 1} description`)}
                          onChange={(event) => updateTask(task.id, { description: event.target.value })}
                          placeholder={tr("Описание шага", "Step description")}
                          className="h-8 bg-card text-xs"
                        />
                      </div>
                      <Input
                        value={task.command}
                        disabled={readOnly}
                        aria-label={tr(`Команда задачи ${idx + 1}`, `Task ${idx + 1} command`)}
                        onChange={(event) => updateTask(task.id, { command: event.target.value })}
                        placeholder="systemctl reload nginx"
                        className="h-10 border-border bg-background font-mono text-sm"
                      />
                      <label className="flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground">
                        <input
                          type="checkbox"
                          disabled={readOnly}
                          checked={task.continue_on_error}
                          onChange={(event) => updateTask(task.id, { continue_on_error: event.target.checked })}
                          className="rounded"
                        />
                        {tr("Продолжать при ошибке", "Continue on error")}
                      </label>
                    </div>
                    <button
                      type="button"
                      disabled={readOnly}
                      aria-label={tr(`Удалить задачу ${idx + 1}`, `Delete task ${idx + 1}`)}
                      onClick={() => removeTask(task.id)}
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
                {state.tasks.length === 0 ? (
                  <p className="py-6 text-center text-sm text-muted-foreground">
                    {tr("Добавьте хотя бы одну shell-команду", "Add at least one shell command")}
                  </p>
                ) : null}
              </div>
            </div>
          )}
        </div>

        <aside className="space-y-4">
          <div className="rounded-sm border border-border bg-card p-4 shadow-elev-1 space-y-3">
            <h3 className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">{tr("Мета", "Meta")}</h3>
            <div className="rounded-sm border border-border bg-surface-0 px-2.5 py-2 text-xs">
              <span className="text-muted-foreground">{tr("Исполняемый формат", "Execution format")}: </span>
              <span className="font-medium text-foreground">{yamlMode ? "Ansible YAML" : "WebTerm runbook"}</span>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="playbook-category" className="text-2xs text-muted-foreground">{tr("Категория", "Category")}</Label>
              <select
                id="playbook-category"
                disabled={metadataReadOnly}
                value={state.category}
                onChange={(event) => onChange({ category: event.target.value as PlaybookCategory })}
                className="flex h-9 w-full rounded-sm border border-border bg-surface-0 px-2 text-sm"
              >
                {CATEGORIES.map((category) => (
                  <option key={category} value={category}>
                    {lang === "ru" ? CATEGORY_META[category].labelRu : CATEGORY_META[category].labelEn}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="playbook-visibility" className="text-2xs text-muted-foreground">{tr("Видимость", "Visibility")}</Label>
              <select
                id="playbook-visibility"
                disabled={metadataReadOnly}
                value={state.visibility}
                onChange={(event) => onChange({ visibility: event.target.value as PlaybookVisibility })}
                className="flex h-9 w-full rounded-sm border border-border bg-surface-0 px-2 text-sm"
              >
                <option value="private">{tr("Личный", "Private")}</option>
                <option value="shared">{tr("Общий", "Shared")}</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="playbook-tags" className="text-2xs text-muted-foreground">{tr("Теги (через запятую)", "Tags (comma-separated)")}</Label>
              <Input
                id="playbook-tags"
                disabled={metadataReadOnly}
                value={state.tagsText}
                onChange={(event) => onChange({ tagsText: event.target.value })}
                placeholder="nginx, prod"
                className="h-9 bg-surface-0"
              />
            </div>
          </div>

          <div className="rounded-sm border border-primary/25 bg-primary/5 p-4 text-xs leading-relaxed text-muted-foreground">
            <p className="mb-1 font-display text-sm font-semibold text-foreground">
              {tr("Как это работает", "How it works")}
            </p>
            <ul className="list-disc space-y-1 pl-4">
              {yamlMode ? (
                <>
                  <li>{tr("Запускается только сохранённый YAML", "Only the saved YAML is executed")}</li>
                  <li>{tr("Outline и shell-проекция не исполняются", "The outline and shell projection are never executed")}</li>
                  <li>{tr("Изменение YAML сбрасывает старую compatibility-ревизию", "Changing YAML invalidates the old compatibility revision")}</li>
                </>
              ) : (
                <>
                  <li>{tr("Каждая задача выполняется через ansible.builtin.shell", "Each task runs via ansible.builtin.shell")}</li>
                  <li>{tr("Порядок и continue-on-error сохраняются", "Order and continue-on-error are preserved")}</li>
                </>
              )}
              <li>{tr("Inventory строится из ваших серверов и групп", "Inventory is built from your servers and groups")}</li>
            </ul>
          </div>
        </aside>
      </div>
    </section>
  );
}
