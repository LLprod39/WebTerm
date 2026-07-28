import { ChevronDown, GripVertical, ListChecks, Plus, X } from "lucide-react";

import type { PlaybookTask } from "@/api/playbooks";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { newLocalTaskId } from "../constants";
import type { PlaybookEditorState } from "../playbookEditorState";

interface PlaybookRunbookWorkspaceProps {
  tr: (ru: string, en: string) => string;
  state: PlaybookEditorState;
  readOnly: boolean;
  onChange: (patch: Partial<PlaybookEditorState>) => void;
}

export function PlaybookRunbookWorkspace({ tr, state, readOnly, onChange }: PlaybookRunbookWorkspaceProps) {
  const updateTask = (id: string, patch: Partial<PlaybookTask>) => {
    onChange({ tasks: state.tasks.map((task) => (task.id === id ? { ...task, ...patch } : task)) });
  };
  const addTask = () => {
    onChange({
      tasks: [
        ...state.tasks,
        { id: newLocalTaskId(), command: "", description: "", continue_on_error: false },
      ],
    });
  };
  const removeTask = (id: string) => onChange({ tasks: state.tasks.filter((task) => task.id !== id) });
  const moveTask = (index: number, direction: -1 | 1) => {
    const next = [...state.tasks];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    onChange({ tasks: next });
  };

  return (
    <section className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1">
      <div className="flex items-center justify-between gap-3 border-b border-border bg-surface-2/35 px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <ListChecks className="h-4 w-4 text-primary" />
          <div>
            <h3 className="text-sm font-semibold text-foreground">
              {tr("Задачи runbook", "Runbook tasks")} · {state.tasks.length}
            </h3>
            <p className="text-2xs text-muted-foreground">
              {tr("Этот список является исполняемым источником.", "This ordered list is the execution source.")}
            </p>
          </div>
        </div>
        <Button size="sm" variant="outline" className="h-8 gap-1.5" disabled={readOnly} onClick={addTask}>
          <Plus className="h-3.5 w-3.5" />
          {tr("Добавить", "Add")}
        </Button>
      </div>

      <div className="space-y-2 p-3">
        {state.tasks.map((task, index) => (
          <div key={task.id} className="flex items-start gap-2 rounded-sm border border-border bg-surface-0/55 p-3">
            <div className="flex shrink-0 flex-col items-center gap-1 pt-1">
              <button
                type="button"
                aria-label={tr(`Переместить задачу ${index + 1} вверх`, `Move task ${index + 1} up`)}
                className="flex h-7 w-7 items-center justify-center rounded-sm text-muted-foreground hover:bg-secondary disabled:opacity-20"
                disabled={readOnly || index === 0}
                onClick={() => moveTask(index, -1)}
              >
                <ChevronDown className="h-3 w-3 rotate-180" />
              </button>
              <GripVertical className="h-3 w-3 text-muted-foreground/40" aria-hidden />
              <button
                type="button"
                aria-label={tr(`Переместить задачу ${index + 1} вниз`, `Move task ${index + 1} down`)}
                className="flex h-7 w-7 items-center justify-center rounded-sm text-muted-foreground hover:bg-secondary disabled:opacity-20"
                disabled={readOnly || index === state.tasks.length - 1}
                onClick={() => moveTask(index, 1)}
              >
                <ChevronDown className="h-3 w-3" />
              </button>
            </div>
            <div className="min-w-0 flex-1 space-y-2">
              <div className="flex items-center gap-2">
                <span className="shrink-0 rounded-sm bg-secondary px-1.5 py-0.5 font-mono text-2xs text-muted-foreground">
                  #{index + 1}
                </span>
                <Input
                  value={task.description}
                  disabled={readOnly}
                  aria-label={tr(`Описание задачи ${index + 1}`, `Task ${index + 1} description`)}
                  onChange={(event) => updateTask(task.id, { description: event.target.value })}
                  placeholder={tr("Описание шага", "Step description")}
                  className="h-8 bg-card text-xs"
                />
              </div>
              <Input
                value={task.command}
                disabled={readOnly}
                aria-label={tr(`Команда задачи ${index + 1}`, `Task ${index + 1} command`)}
                onChange={(event) => updateTask(task.id, { command: event.target.value })}
                placeholder="systemctl reload nginx"
                className="h-10 border-border bg-background font-mono text-sm"
              />
              <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
                <Checkbox
                  disabled={readOnly}
                  checked={task.continue_on_error}
                  onCheckedChange={(checked) => updateTask(task.id, { continue_on_error: checked === true })}
                />
                {tr("Продолжать при ошибке", "Continue on error")}
              </label>
            </div>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              disabled={readOnly}
              aria-label={tr(`Удалить задачу ${index + 1}`, `Delete task ${index + 1}`)}
              onClick={() => removeTask(task.id)}
              className="h-9 w-9 shrink-0 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        ))}
        {state.tasks.length === 0 ? (
          <div className="rounded-sm border border-dashed border-border px-6 py-12 text-center text-sm text-muted-foreground">
            {tr("Добавьте хотя бы одну shell-команду.", "Add at least one shell command.")}
          </div>
        ) : null}
      </div>
    </section>
  );
}
