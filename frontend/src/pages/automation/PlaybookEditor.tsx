import { ChevronDown, GripVertical, Plus, Save, X } from "lucide-react";
import type {
  PlaybookCategory,
  PlaybookCompatibilityReport,
  PlaybookCompatibilityRevision,
  PlaybookDetail,
  PlaybookKind,
  PlaybookTask,
  PlaybookVisibility,
} from "@/api/playbooks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { CATEGORIES, CATEGORY_META, newLocalTaskId } from "./constants";
import { PlaybookCompatibilityPanel } from "./PlaybookCompatibilityPanel";

export interface PlaybookEditorState {
  name: string;
  description: string;
  kind: PlaybookKind;
  category: PlaybookCategory;
  visibility: PlaybookVisibility;
  tagsText: string;
  tasks: PlaybookTask[];
  sourceYaml: string;
  compatibility: PlaybookCompatibilityReport;
  activeCompatibilityRevision: PlaybookCompatibilityRevision | null;
}

interface PlaybookEditorProps {
  lang: string;
  state: PlaybookEditorState;
  saving: boolean;
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
  onChange,
  onSave,
  onBack,
  onRun,
  title,
  playbookId,
  onCompatibilityApplied,
}: PlaybookEditorProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);

  const updateTask = (id: string, patch: Partial<PlaybookTask>) => {
    onChange({
      tasks: state.tasks.map((t) => (t.id === id ? { ...t, ...patch } : t)),
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
    onChange({ tasks: state.tasks.filter((t) => t.id !== id) });
  };

  const moveTask = (idx: number, dir: -1 | 1) => {
    const next = [...state.tasks];
    const target = idx + dir;
    if (target < 0 || target >= next.length) return;
    [next[idx], next[target]] = [next[target], next[idx]];
    onChange({ tasks: next });
  };

  const canSave =
    Boolean(String(state.name ?? "").trim()) &&
    (Boolean(state.sourceYaml.trim()) || state.tasks.some((t) => Boolean(String(t?.command ?? "").trim())));

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" className="h-9 px-2" onClick={onBack}>
            ← {tr("Каталог", "Catalog")}
          </Button>
          <h2 className="font-display text-lg font-semibold text-foreground">{title}</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" className="h-9 gap-1.5" disabled={!canSave || saving} onClick={onSave}>
            <Save className="h-3.5 w-3.5" />
            {saving ? tr("Сохранение…", "Saving…") : tr("Сохранить", "Save")}
          </Button>
          <Button size="sm" className="h-9 gap-1.5 shadow-elev-1" disabled={!canSave} onClick={onRun}>
            {tr("Запустить…", "Run…")}
          </Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
        <div className="space-y-4">
          {state.sourceYaml ? (
            <>
              <div className="rounded-sm border border-border bg-card p-4 shadow-elev-1 space-y-3">
                <div>
                  <h3 className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">
                    {tr("Оригинальный Ansible YAML", "Original Ansible YAML")}
                  </h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {tr(
                      "Хранится неизменным. Для выполнения используется только проверенная ревизия или runtime-привязка inventory.",
                      "Preserved unchanged. Execution uses a validated revision or runtime inventory binding.",
                    )}
                  </p>
                </div>
                <Textarea value={state.sourceYaml} readOnly className="min-h-80 bg-background font-mono text-xs" />
              </div>
              <PlaybookCompatibilityPanel
                lang={lang}
                playbookId={playbookId}
                sourceYaml={state.sourceYaml}
                report={state.activeCompatibilityRevision?.report || state.compatibility}
                activeRevision={state.activeCompatibilityRevision}
                onApplied={onCompatibilityApplied}
              />
            </>
          ) : (
          <div className="rounded-sm border border-border bg-card p-4 shadow-elev-1 space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5 sm:col-span-2">
                <Label className="text-2xs uppercase tracking-wider text-muted-foreground">{tr("Имя", "Name")} *</Label>
                <Input
                  value={state.name}
                  onChange={(e) => onChange({ name: e.target.value })}
                  placeholder={tr("например, Reload nginx fleet", "e.g. Reload nginx fleet")}
                  className="h-10 bg-surface-0"
                />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <Label className="text-2xs uppercase tracking-wider text-muted-foreground">{tr("Описание", "Description")}</Label>
                <Textarea
                  value={state.description}
                  onChange={(e) => onChange({ description: e.target.value })}
                  placeholder={tr("Что делает этот playbook и когда его запускать", "What it does and when to run it")}
                  className="min-h-[72px] bg-surface-0"
                />
              </div>
            </div>
          </div>
          )}

          <div className="rounded-sm border border-border bg-card p-4 shadow-elev-1 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">
                {tr("Задачи", "Tasks")} ({state.tasks.length})
              </h3>
              <Button size="sm" variant="outline" className="h-8 gap-1" onClick={addTask}>
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
                      className="flex h-7 w-7 items-center justify-center rounded-sm text-muted-foreground hover:bg-secondary disabled:opacity-20"
                      disabled={idx === 0}
                      onClick={() => moveTask(idx, -1)}
                    >
                      <ChevronDown className="h-3 w-3 rotate-180" />
                    </button>
                    <GripVertical className="h-3 w-3 text-muted-foreground/40" />
                    <button
                      type="button"
                      className="flex h-7 w-7 items-center justify-center rounded-sm text-muted-foreground hover:bg-secondary disabled:opacity-20"
                      disabled={idx === state.tasks.length - 1}
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
                        onChange={(e) => updateTask(task.id, { description: e.target.value })}
                        placeholder={tr("Описание шага", "Step description")}
                        className="h-8 bg-card text-xs"
                      />
                    </div>
                    <Input
                      value={task.command}
                      onChange={(e) => updateTask(task.id, { command: e.target.value })}
                      placeholder="systemctl reload nginx"
                      className="h-10 border-border bg-background font-mono text-sm"
                    />
                    <label className="flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground">
                      <input
                        type="checkbox"
                        checked={task.continue_on_error}
                        onChange={(e) => updateTask(task.id, { continue_on_error: e.target.checked })}
                        className="rounded"
                      />
                      {tr("Продолжать при ошибке", "Continue on error")}
                    </label>
                  </div>
                  <button
                    type="button"
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
        </div>

        <aside className="space-y-4">
          <div className="rounded-sm border border-border bg-card p-4 shadow-elev-1 space-y-3">
            <h3 className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">{tr("Мета", "Meta")}</h3>
            <div className="space-y-1.5">
              <Label className="text-2xs text-muted-foreground">{tr("Категория", "Category")}</Label>
              <select
                value={state.category}
                onChange={(e) => onChange({ category: e.target.value as PlaybookCategory })}
                className="flex h-9 w-full rounded-sm border border-border bg-surface-0 px-2 text-sm"
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {lang === "ru" ? CATEGORY_META[c].labelRu : CATEGORY_META[c].labelEn}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-2xs text-muted-foreground">{tr("Видимость", "Visibility")}</Label>
              <select
                value={state.visibility}
                onChange={(e) => onChange({ visibility: e.target.value as PlaybookVisibility })}
                className="flex h-9 w-full rounded-sm border border-border bg-surface-0 px-2 text-sm"
              >
                <option value="private">{tr("Личный", "Private")}</option>
                <option value="shared">{tr("Общий", "Shared")}</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-2xs text-muted-foreground">{tr("Теги (через запятую)", "Tags (comma-separated)")}</Label>
              <Input
                value={state.tagsText}
                onChange={(e) => onChange({ tagsText: e.target.value })}
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
              <li>{tr("Каждая задача выполняется через ansible.builtin.shell", "Each task runs via ansible.builtin.shell")}</li>
              <li>{tr("Inventory строится из ваших серверов и групп", "Inventory is built from your servers & groups")}</li>
              <li>{tr("Импортированный YAML проходит compatibility gate", "Imported YAML passes a compatibility gate")}</li>
              <li>{tr("Привязка hosts не меняет оригинал", "Host binding never changes the original")}</li>
            </ul>
          </div>
        </aside>
      </div>
    </section>
  );
}
