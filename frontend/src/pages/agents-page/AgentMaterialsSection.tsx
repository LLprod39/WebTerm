import { AlertTriangle, Eye, FileCode2, FileText, ListChecks, Plus, Send, Trash2, Upload, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { AgentInputArtifact } from "@/lib/api";
import { localize } from "@/lib/i18n";

import {
  ARTIFACT_KINDS,
  type AgentTaskDraft,
  artifactKindIcon,
  artifactKindLabel,
  artifactSummary,
  parseTasksFromContent,
  tasksToContent,
} from "./agentPageUtils";

type AgentMaterialsSectionProps = {
  lang: string;
  inputArtifacts: AgentInputArtifact[];
  activeArtifact: AgentInputArtifact | null;
  activeArtifactIndex: number | null;
  setActiveArtifactIndex: (index: number | null) => void;
  addArtifact: (kind: AgentInputArtifact["kind"]) => void;
  removeArtifact: (index: number) => void;
  updateArtifact: (index: number, patch: Partial<AgentInputArtifact>) => void;
  updateArtifactTask: (artifactIndex: number, taskIndex: number, patch: Partial<AgentTaskDraft>) => void;
  addArtifactTask: (artifactIndex: number) => void;
  removeArtifactTask: (artifactIndex: number, taskIndex: number) => void;
  onMaterialFiles: (files: FileList | null) => void | Promise<void>;
  telegramEnabled: boolean;
  setTelegramEnabled: (enabled: boolean) => void;
  telegramChatId: string;
  setTelegramChatId: (chatId: string) => void;
};

export function AgentMaterialsSection({
  lang,
  inputArtifacts,
  activeArtifact,
  activeArtifactIndex,
  setActiveArtifactIndex,
  addArtifact,
  removeArtifact,
  updateArtifact,
  updateArtifactTask,
  addArtifactTask,
  removeArtifactTask,
  onMaterialFiles,
  telegramEnabled,
  setTelegramEnabled,
  telegramChatId,
  setTelegramChatId,
}: AgentMaterialsSectionProps) {
  return (
    <>
      <div className="space-y-3 rounded-lg border border-border/70 bg-background/25 p-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Upload className="h-4 w-4 text-primary" /> {localize(lang, "Материалы для контекста ИИ", "Materials for AI context")}
          </h4>
          <div className="flex flex-wrap gap-2">
            <label className="inline-flex min-h-8 cursor-pointer items-center rounded-md border border-primary/40 bg-primary/10 px-2 text-xs font-semibold text-primary transition-colors hover:bg-primary/15">
              <Upload className="mr-1 h-3 w-3" /> {localize(lang, "Файл", "File")}
              <input
                type="file"
                multiple
                className="hidden"
                accept=".txt,.md,.csv,.json,.yaml,.yml,.sh,.py,.js,.ts,.sql,.log,.ps1"
                onChange={(e) => {
                  void onMaterialFiles(e.currentTarget.files);
                  e.currentTarget.value = "";
                }}
              />
            </label>
            <button type="button" onClick={() => addArtifact("document")} className="min-h-8 rounded-md border border-border px-2 text-xs font-semibold text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground">
              <FileText className="mr-1 inline h-3 w-3" /> {localize(lang, "Документ", "Document")}
            </button>
            <button type="button" onClick={() => addArtifact("script")} className="min-h-8 rounded-md border border-border px-2 text-xs font-semibold text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground">
              <FileCode2 className="mr-1 inline h-3 w-3" /> {localize(lang, "Код как контекст", "Code as context")}
            </button>
            <button type="button" onClick={() => addArtifact("task_list")} className="min-h-8 rounded-md border border-border px-2 text-xs font-semibold text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground">
              <ListChecks className="mr-1 inline h-3 w-3" /> {localize(lang, "Задачи", "Tasks")}
            </button>
          </div>
        </div>

        <div role="note" className="flex items-start gap-3 rounded-sm border border-warning/30 bg-warning/10 px-3 py-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <p className="text-xs leading-5 text-muted-foreground">
            {localize(
              lang,
              "Сохраняются первые 12 КБ текста. Документы доступны для чтения, а распознанные shell/bash-скрипты запускаются только в отдельном ограниченном Docker-контейнере. Репозитории и Ansible используют соответствующую автоматизацию.",
              "The first 12 KB of text is stored. Documents are readable, while identifiable shell/bash scripts run only in a separate restricted Docker container. Repositories and Ansible use their dedicated automation flows.",
            )}
          </p>
        </div>

        {inputArtifacts.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border/70 px-3 py-4 text-xs text-muted-foreground">
            {localize(lang, "Материалы не обязательны. Добавьте регламент, список задач или небольшой текстовый фрагмент кода, если агенту нужен контекст.", "Materials are optional. Add a procedure, task list, or a small code excerpt when the agent needs context.")}
          </div>
        ) : (
          <div className="grid gap-3 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.35fr)]">
            <div className="space-y-2">
              {inputArtifacts.map((artifact, index) => {
                const KindIcon = artifactKindIcon(artifact.kind);
                const active = activeArtifactIndex === index;
                return (
                  <div key={`${artifact.kind}-${index}-${artifact.name}`} className={`rounded-lg border p-3 transition-colors ${active ? "border-primary bg-primary/10" : "border-border/70 bg-background/35"}`}>
                    <div className="flex items-start gap-3">
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-secondary/40 text-primary">
                        <KindIcon className="h-4 w-4" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-xs font-semibold text-foreground">
                          {artifact.name || artifactKindLabel(artifact.kind, lang)}
                        </div>
                        <div className="mt-0.5 flex flex-wrap gap-1.5 text-xs leading-4 text-muted-foreground">
                          <span>{artifactKindLabel(artifact.kind, lang)}</span>
                          <span>{artifactSummary(artifact, lang)}</span>
                        </div>
                      </div>
                    </div>
                    <div className="mt-3 flex items-center justify-end gap-2">
                      <Button type="button" size="xs" variant={active ? "default" : "outline"} className="gap-1" onClick={() => setActiveArtifactIndex(index)}>
                        <Eye className="h-3 w-3" /> {localize(lang, "Открыть", "Open")}
                      </Button>
                      <Button type="button" size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground" onClick={() => removeArtifact(index)} aria-label={localize(lang, "Удалить материал", "Remove material")}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>

            {activeArtifact && activeArtifactIndex !== null ? (
              <div className="space-y-3 rounded-lg border border-border/70 bg-background/35 p-3">
                <div className="grid gap-2 sm:grid-cols-[140px_1fr]">
                  <Select
                    value={activeArtifact.kind}
                    onValueChange={(value) => {
                      const nextKind = value as AgentInputArtifact["kind"];
                      const nextTasks = nextKind === "task_list" ? (activeArtifact.tasks?.length ? activeArtifact.tasks : parseTasksFromContent(activeArtifact.content || "")) : undefined;
                      updateArtifact(activeArtifactIndex, {
                        kind: nextKind,
                        tasks: nextKind === "task_list" ? (nextTasks?.length ? nextTasks : [{ title: "", details: "", done: false }]) : undefined,
                        content: nextKind === "task_list" ? activeArtifact.content : activeArtifact.content || tasksToContent(activeArtifact.tasks),
                      });
                    }}
                  >
                    <SelectTrigger className="h-9 bg-secondary/50 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ARTIFACT_KINDS.map((item) => (
                        <SelectItem key={item.kind} value={item.kind}>
                          {localize(lang, item.labelRu, item.labelEn)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Input value={activeArtifact.name} onChange={(e) => updateArtifact(activeArtifactIndex, { name: e.target.value })} className="h-9 bg-secondary/50 text-sm" />
                </div>
                {activeArtifact.kind === "task_list" ? (
                  <div className="space-y-2">
                    {(activeArtifact.tasks?.length ? activeArtifact.tasks : [{ title: "", details: "", done: false }]).map((task, taskIndex) => (
                      <div key={taskIndex} className="rounded-lg border border-border/60 bg-secondary/20 p-2">
                        <div className="grid gap-2 sm:grid-cols-[auto_1fr_auto] sm:items-center">
                          <input type="checkbox" checked={Boolean(task.done)} onChange={(e) => updateArtifactTask(activeArtifactIndex, taskIndex, { done: e.target.checked })} className="rounded" aria-label={localize(lang, "Задача выполнена", "Task done")} />
                          <Input value={task.title} onChange={(e) => updateArtifactTask(activeArtifactIndex, taskIndex, { title: e.target.value })} className="h-8 bg-background/60 text-xs" placeholder={localize(lang, "Название задачи", "Task title")} />
                          <Button type="button" size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground" onClick={() => removeArtifactTask(activeArtifactIndex, taskIndex)} aria-label={localize(lang, "Удалить задачу", "Remove task")}>
                            <X className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                        <Textarea value={task.details || ""} onChange={(e) => updateArtifactTask(activeArtifactIndex, taskIndex, { details: e.target.value })} rows={2} className="mt-2 bg-background/60 text-xs" />
                      </div>
                    ))}
                    <Button type="button" size="sm" variant="outline" className="w-full gap-1" onClick={() => addArtifactTask(activeArtifactIndex)}>
                      <Plus className="h-3.5 w-3.5" /> {localize(lang, "Добавить задачу", "Add task")}
                    </Button>
                  </div>
                ) : (
                  <>
                    {activeArtifact.kind === "script" ? (
                      <p className="rounded-sm border border-warning/25 bg-warning/5 px-3 py-2 text-xs leading-5 text-muted-foreground">
                        {localize(lang, "Shell/bash можно запустить без SSH в отдельном ограниченном Docker-контейнере с обычным интернет-доступом. Контейнер не получает файлы, секреты, Docker socket или сеть хоста; запуск всё равно требует подтверждения.", "Shell/bash can run without SSH in a restricted Docker container with regular internet access. It receives no host files, secrets, Docker socket, or host network; execution still requires approval.")}
                      </p>
                    ) : null}
                    <Textarea value={activeArtifact.content} onChange={(e) => updateArtifact(activeArtifactIndex, { content: e.target.value })} rows={activeArtifact.kind === "script" ? 10 : 8} className={`bg-secondary/50 text-xs ${activeArtifact.kind === "script" ? "font-mono" : ""}`} />
                  </>
                )}
              </div>
            ) : (
              <div className="flex min-h-[180px] items-center justify-center rounded-lg border border-dashed border-border/70 px-4 py-6 text-center text-xs text-muted-foreground">
                {localize(lang, "Выберите материал слева.", "Select a material on the left.")}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="rounded-lg border border-border/70 bg-background/25 p-4">
        <label className="flex cursor-pointer items-center gap-3">
          <input type="checkbox" checked={telegramEnabled} onChange={(e) => setTelegramEnabled(e.target.checked)} className="rounded" />
          <span className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Send className="h-4 w-4 text-primary" /> {localize(lang, "Уведомить о результате в Telegram", "Notify about the result in Telegram")}
          </span>
        </label>
        {telegramEnabled && <Input value={telegramChatId} onChange={(e) => setTelegramChatId(e.target.value)} className="mt-3 h-9 bg-background/60 text-sm" placeholder="Chat ID" />}
      </div>
    </>
  );
}
