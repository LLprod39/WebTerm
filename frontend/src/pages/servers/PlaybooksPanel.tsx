import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { BookOpen, CheckCircle2, ChevronDown, ChevronRight, Copy, Download, FileJson, GripVertical, Loader2, Play, Plus, Save, Server, Settings, Trash2, Upload, X, XCircle } from "lucide-react";
import { StatusIndicator } from "@/components/StatusIndicator";
import { ServerOsBadge } from "@/components/servers/ServerOsBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { executeServerCommand, type FrontendServer } from "@/lib/api";
import { localize } from "@/lib/i18n";
import { resolveServerOs } from "@/lib/server-os";
import { formatCommandOutput } from "./formatters";
import { exportPlaybookAsJson, loadPlaybooks, newPlaybookId, newTaskId, parseAnsiblePlaybook, savePlaybooks } from "./playbooks";
import type { Playbook, PlaybookRunResult, PlaybookTask } from "./types";
interface UsePlaybooksPanelParams { servers: FrontendServer[]; t: (key: string) => string; tr: (key: string, vars?: Record<string, string | number>) => string; lang: string; }
export function usePlaybooksPanel({ servers, t, tr, lang }: UsePlaybooksPanelParams) {
  const [playbooks, setPlaybooks] = useState<Playbook[]>(loadPlaybooks);
  const [activePlaybook, setActivePlaybook] = useState<Playbook | null>(null);
  const [playbookName, setPlaybookName] = useState("");
  const [playbookDesc, setPlaybookDesc] = useState("");
  const [playbookTasks, setPlaybookTasks] = useState<PlaybookTask[]>([]);
  const [playbookTargets, setPlaybookTargets] = useState<Set<number>>(new Set());
  const [playbookRunning, setPlaybookRunning] = useState(false);
  const [playbookResults, setPlaybookResults] = useState<PlaybookRunResult[]>([]);
  const [playbookView, setPlaybookView] = useState<"list" | "edit" | "run">("list");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const addPlaybookTask = () => {
    setPlaybookTasks((prev) => [...prev, { id: newTaskId(), command: "", description: "", continueOnError: false }]);
  };
  const updatePlaybookTask = (id: string, patch: Partial<PlaybookTask>) => {
    setPlaybookTasks((prev) => prev.map((task) => (task.id === id ? { ...task, ...patch } : task)));
  };
  const removePlaybookTask = (id: string) => {
    setPlaybookTasks((prev) => prev.filter((task) => task.id !== id));
  };
  const moveTask = (idx: number, dir: -1 | 1) => {
    setPlaybookTasks((prev) => {
      const next = [...prev];
      const target = idx + dir;
      if (target < 0 || target >= next.length) return prev;
      [next[idx], next[target]] = [next[target], next[idx]];
      return next;
    });
  };
  const toggleTarget = (id: number) => {
    setPlaybookTargets((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const selectAllTargets = () => {
    setPlaybookTargets(new Set(servers.filter((server) => server.status === "online").map((server) => server.id)));
  };
  const clearTargets = () => setPlaybookTargets(new Set());

  const openNewPlaybook = () => {
    setActivePlaybook(null);
    setPlaybookName("");
    setPlaybookDesc("");
    setPlaybookTasks([{ id: newTaskId(), command: "", description: "", continueOnError: false }]);
    setPlaybookTargets(new Set());
    setPlaybookResults([]);
    setPlaybookView("edit");
  };

  const openEditPlaybook = (playbook: Playbook) => {
    setActivePlaybook(playbook);
    setPlaybookName(playbook.name);
    setPlaybookDesc(playbook.description);
    setPlaybookTasks([...playbook.tasks]);
    setPlaybookTargets(new Set());
    setPlaybookResults([]);
    setPlaybookView("edit");
  };

  const onSavePlaybook = () => {
    if (!playbookName.trim() || playbookTasks.length === 0) return;
    const playbook: Playbook = {
      id: activePlaybook?.id || newPlaybookId(),
      name: playbookName.trim(),
      description: playbookDesc.trim(),
      tasks: playbookTasks.filter((task) => task.command.trim()),
      createdAt: activePlaybook?.createdAt || new Date().toISOString(),
    };
    const updated = activePlaybook
      ? playbooks.map((item) => (item.id === activePlaybook.id ? playbook : item))
      : [...playbooks, playbook];
    setPlaybooks(updated);
    savePlaybooks(updated);
    setActivePlaybook(playbook);
  };

  const onDeletePlaybook = (id: string) => {
    if (!confirm(t("pb.delete_confirm"))) return;
    const updated = playbooks.filter((playbook) => playbook.id !== id);
    setPlaybooks(updated);
    savePlaybooks(updated);
    if (activePlaybook?.id === id) setPlaybookView("list");
  };

  const onDuplicatePlaybook = (playbook: Playbook) => {
    const duplicate: Playbook = {
      ...playbook,
      id: newPlaybookId(),
      name: tr("pb.copy_name", { name: playbook.name }),
      createdAt: new Date().toISOString(),
      tasks: playbook.tasks.map((task) => ({ ...task, id: newTaskId() })),
    };
    const updated = [...playbooks, duplicate];
    setPlaybooks(updated);
    savePlaybooks(updated);
  };

  const onImportFile = async (file: File) => {
    try {
      const text = await file.text();
      const playbook = parseAnsiblePlaybook(text, file.name);
      const updated = [...playbooks, playbook];
      setPlaybooks(updated);
      savePlaybooks(updated);
      setActivePlaybook(playbook);
      setPlaybookName(playbook.name);
      setPlaybookDesc(playbook.description);
      setPlaybookTasks([...playbook.tasks]);
      setPlaybookTargets(new Set());
      setPlaybookResults([]);
      setPlaybookView("edit");
    } catch (err) {
      alert(tr("pb.parse_failed", { error: err instanceof Error ? err.message : String(err) }));
    }
  };

  const onFileInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) void onImportFile(file);
    event.target.value = "";
  };

  const onDropPlaybook = (event: DragEvent) => {
    event.preventDefault();
    const file = event.dataTransfer.files[0];
    if (file) void onImportFile(file);
  };

  const onRunPlaybook = async () => {
    const validTasks = playbookTasks.filter((task) => task.command.trim());
    const targetIds = Array.from(playbookTargets);
    if (!validTasks.length || !targetIds.length) return;

    setPlaybookRunning(true);
    setPlaybookView("run");

    const results: PlaybookRunResult[] = targetIds.map((serverId) => {
      const server = servers.find((item) => item.id === serverId);
      return {
        serverId,
        serverName: server?.name || `Server #${serverId}`,
        taskResults: validTasks.map((task) => ({
          taskId: task.id,
          command: task.command,
          status: "pending" as const,
          output: "",
        })),
      };
    });
    setPlaybookResults([...results]);

    for (let serverIndex = 0; serverIndex < results.length; serverIndex += 1) {
      const serverResult = results[serverIndex];
      let shouldSkip = false;
      for (let taskIndex = 0; taskIndex < validTasks.length; taskIndex += 1) {
        const task = validTasks[taskIndex];
        if (shouldSkip) {
          serverResult.taskResults[taskIndex].status = "skipped";
          serverResult.taskResults[taskIndex].output = t("pb.skipped_due_previous_error");
          setPlaybookResults([...results]);
          continue;
        }

        serverResult.taskResults[taskIndex].status = "running";
        setPlaybookResults([...results]);

        try {
          const response = await executeServerCommand(serverResult.serverId, task.command, "");
          if (response.success) {
            serverResult.taskResults[taskIndex].status = "success";
            serverResult.taskResults[taskIndex].output = formatCommandOutput(response.output);
            serverResult.taskResults[taskIndex].exitCode = 0;
          } else {
            serverResult.taskResults[taskIndex].status = "error";
            serverResult.taskResults[taskIndex].output = response.error || t("pb.command_failed");
            serverResult.taskResults[taskIndex].exitCode = 1;
            if (!task.continueOnError) shouldSkip = true;
          }
        } catch (err) {
          serverResult.taskResults[taskIndex].status = "error";
          serverResult.taskResults[taskIndex].output = String(err);
          serverResult.taskResults[taskIndex].exitCode = 1;
          if (!task.continueOnError) shouldSkip = true;
        }
        setPlaybookResults([...results]);
      }
    }

    setPlaybookRunning(false);
  };

  return {
    activePlaybook, addPlaybookTask, clearTargets, fileInputRef, lang, moveTask, onDeletePlaybook, onDropPlaybook,
    onDuplicatePlaybook, onFileInputChange, onRunPlaybook, onSavePlaybook, openEditPlaybook, openNewPlaybook,
    playbookDesc, playbookName, playbookResults, playbookRunning, playbookTargets, playbookTasks, playbookView,
    playbooks, removePlaybookTask, selectAllTargets, servers, setPlaybookDesc, setPlaybookName, setPlaybookView,
    t, toggleTarget, tr, updatePlaybookTask,
  };
}

type PlaybooksPanelProps = ReturnType<typeof usePlaybooksPanel>;

export function PlaybooksPanel({
  activePlaybook, addPlaybookTask, clearTargets, fileInputRef, lang, moveTask, onDeletePlaybook, onDropPlaybook,
  onDuplicatePlaybook, onFileInputChange, onRunPlaybook, onSavePlaybook, openEditPlaybook, openNewPlaybook,
  playbookDesc, playbookName, playbookResults, playbookRunning, playbookTargets, playbookTasks, playbookView,
  playbooks, removePlaybookTask, selectAllTargets, servers, setPlaybookDesc, setPlaybookName, setPlaybookView,
  t, toggleTarget, tr, updatePlaybookTask,
}: PlaybooksPanelProps) {
  return (
    <>
      <input ref={fileInputRef} type="file" accept=".yml,.yaml,.json" className="hidden" onChange={onFileInputChange} />

      {playbookView === "list" && (
        <section className="bg-card border border-border rounded-lg p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-foreground">{t("pb.title")}</h2>
              <p className="text-xs text-muted-foreground mt-0.5">{t("pb.subtitle")}</p>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" className="h-10 gap-1.5 text-xs" onClick={() => fileInputRef.current?.click()}>
                <Upload className="h-3.5 w-3.5" /> {t("pb.import")}
              </Button>
              <Button size="sm" className="h-10 gap-1.5 text-xs" onClick={openNewPlaybook}>
                <Plus className="h-3.5 w-3.5" /> {t("pb.new")}
              </Button>
            </div>
          </div>

          <div
            onDragOver={(event) => event.preventDefault()}
            onDrop={onDropPlaybook}
            className="border-2 border-dashed border-border rounded-lg p-6 text-center transition-colors hover:border-primary/40 hover:bg-primary/5 cursor-pointer"
            onClick={() => fileInputRef.current?.click()}
          >
            <FileJson className="h-8 w-8 mx-auto mb-2 text-muted-foreground/40" />
            <p className="text-xs text-muted-foreground">
              {t("pb.drop_help")} <span className="text-primary underline">{t("pb.browse")}</span>
            </p>
            <p className="text-[10px] text-muted-foreground/60 mt-1">{t("pb.supports")}</p>
          </div>

          {playbooks.length === 0 ? (
            <div className="text-center py-6 text-muted-foreground">
              <p className="text-sm">{t("pb.empty_title")}</p>
              <p className="text-xs mt-1">{t("pb.empty_help")}</p>
            </div>
          ) : (
            <div className="space-y-2">
              {playbooks.map((playbook) => (
                <div key={playbook.id} className="flex items-center gap-4 px-4 py-3 rounded-lg border border-border bg-secondary/10 hover:bg-secondary/30 transition-colors">
                  <BookOpen className="h-4 w-4 text-primary shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">{playbook.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {tr(playbook.tasks.length === 1 ? "pb.task_count_one" : "pb.task_count_other", { count: playbook.tasks.length })} · {new Date(playbook.createdAt).toLocaleDateString()}
                      {playbook.description && ` · ${playbook.description}`}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <Button size="xs" variant="outline" className="h-9 gap-1" onClick={() => openEditPlaybook(playbook)}>
                      <Settings className="h-3 w-3" /> {t("pb.edit")}
                    </Button>
                    <Button size="icon" variant="outline" className="h-9 w-9" title={t("pb.export_json")} aria-label={t("pb.export_json")} onClick={() => exportPlaybookAsJson(playbook)}>
                      <Download className="h-3 w-3" />
                    </Button>
                    <Button size="icon" variant="outline" className="h-9 w-9" onClick={() => onDuplicatePlaybook(playbook)} aria-label={localize(lang, "Дублировать плейбук", "Duplicate playbook")}>
                      <Copy className="h-3 w-3" />
                    </Button>
                    <Button size="icon" variant="outline" className="h-9 w-9 border-destructive/30 text-destructive hover:bg-destructive/10" onClick={() => onDeletePlaybook(playbook.id)} aria-label={localize(lang, "Удалить плейбук", "Delete playbook")}>
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {playbookView === "edit" && (
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <Button size="icon" variant="ghost" className="h-9 w-9" onClick={() => setPlaybookView("list")} aria-label={localize(lang, "Вернуться к списку плейбуков", "Back to playbook list")}>
              <ChevronRight className="h-4 w-4 rotate-180" />
            </Button>
            <h2 className="text-sm font-semibold text-foreground">
              {activePlaybook ? t("pb.edit_title") : t("pb.new_title")}
            </h2>
          </div>

          <div className="bg-card border border-border rounded-lg p-4 space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{t("pb.name")} *</Label>
                <Input placeholder={t("pb.name_placeholder")} value={playbookName} onChange={(event) => setPlaybookName(event.target.value)} className="bg-secondary/50 h-9" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{t("pb.description")}</Label>
                <Input placeholder={t("pb.description_placeholder")} value={playbookDesc} onChange={(event) => setPlaybookDesc(event.target.value)} className="bg-secondary/50 h-9" />
              </div>
            </div>
          </div>

          <div className="bg-card border border-border rounded-lg p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{tr("pb.tasks_title", { count: playbookTasks.length })}</h3>
              <Button size="xs" variant="outline" className="h-9 gap-1" onClick={addPlaybookTask}>
                <Plus className="h-3 w-3" /> {t("pb.add_task")}
              </Button>
            </div>

            <div className="space-y-2">
              {playbookTasks.map((task, idx) => (
                <div key={task.id} className="flex items-start gap-2 p-3 rounded-lg border border-border bg-secondary/10">
                  <div className="flex flex-col gap-1 pt-1.5 shrink-0">
                    <button type="button" onClick={() => moveTask(idx, -1)} disabled={idx === 0} className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-20">
                      <ChevronDown className="h-3 w-3 rotate-180" />
                    </button>
                    <GripVertical className="h-3 w-3 text-muted-foreground/40 mx-auto" />
                    <button type="button" onClick={() => moveTask(idx, 1)} disabled={idx === playbookTasks.length - 1} className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-20">
                      <ChevronDown className="h-3 w-3" />
                    </button>
                  </div>
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-muted-foreground bg-secondary rounded px-1.5 py-0.5 shrink-0">#{idx + 1}</span>
                      <Input
                        placeholder={t("pb.task_description_placeholder")}
                        value={task.description}
                        onChange={(event) => updatePlaybookTask(task.id, { description: event.target.value })}
                        className="h-8 flex-1 bg-secondary/50 text-xs"
                      />
                    </div>
                    <Input
                      placeholder={t("pb.task_command_placeholder")}
                      value={task.command}
                      onChange={(event) => updatePlaybookTask(task.id, { command: event.target.value })}
                      className="bg-background h-9 font-mono text-sm border-border"
                    />
                    <label className="text-[11px] flex items-center gap-1.5 text-muted-foreground cursor-pointer">
                      <input
                        type="checkbox"
                        checked={task.continueOnError}
                        onChange={(event) => updatePlaybookTask(task.id, { continueOnError: event.target.checked })}
                        className="rounded"
                      />
                      {t("pb.continue_on_error")}
                    </label>
                  </div>
                  <button type="button" onClick={() => removePlaybookTask(task.id)} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive">
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-card border border-border rounded-lg p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                {tr("pb.targets_title", { count: playbookTargets.size })}
              </h3>
              <div className="flex gap-1.5">
                <Button size="xs" variant="outline" className="h-8" onClick={selectAllTargets}>{t("pb.select_online")}</Button>
                <Button size="xs" variant="outline" className="h-8" onClick={clearTargets}>{t("pb.clear")}</Button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {servers.map((server) => (
                <button
                  key={server.id}
                  onClick={() => toggleTarget(server.id)}
                  className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg border text-left transition-all text-xs ${
                    playbookTargets.has(server.id)
                      ? "border-primary bg-primary/5 text-foreground"
                      : "border-border bg-secondary/10 text-muted-foreground hover:text-foreground hover:border-border"
                  }`}
                >
                  <ServerOsBadge kind={resolveServerOs(server)} size="sm" />
                  <StatusIndicator status={server.status} showLabel={false} />
                  <span className="font-medium truncate">{server.name}</span>
                  <span className="text-[10px] font-mono ml-auto opacity-60">{server.host}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2 justify-end">
            <Button size="sm" variant="outline" className="h-9 gap-1.5" onClick={onSavePlaybook} disabled={!playbookName.trim() || playbookTasks.length === 0}>
              <Save className="h-3.5 w-3.5" /> {t("pb.save")}
            </Button>
            <Button
              size="sm"
              className="h-9 gap-1.5 px-6"
              onClick={onRunPlaybook}
              disabled={playbookRunning || playbookTargets.size === 0 || playbookTasks.filter((task) => task.command.trim()).length === 0}
            >
              <Play className="h-3.5 w-3.5" /> {tr(playbookTargets.size === 1 ? "pb.run_on_one" : "pb.run_on_many", { count: playbookTargets.size })}
            </Button>
          </div>
        </section>
      )}

      {playbookView === "run" && (
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" className="h-8 px-2" onClick={() => setPlaybookView("edit")}>
              <ChevronRight className="h-4 w-4 rotate-180" />
            </Button>
            <h2 className="text-sm font-semibold text-foreground">
              {t("pb.run_results")} {playbookRunning && <Loader2 className="inline h-3.5 w-3.5 ml-1.5 animate-spin text-primary" />}
            </h2>
            <span className="text-xs text-muted-foreground ml-auto">
              {tr(playbookResults.length === 1 ? "pb.server_count_one" : "pb.server_count_other", { count: playbookResults.length })}
            </span>
          </div>

          {playbookResults.map((serverResult) => {
            const allDone = serverResult.taskResults.every((taskResult) => taskResult.status !== "pending" && taskResult.status !== "running");
            const allOk = serverResult.taskResults.every((taskResult) => taskResult.status === "success");
            const hasError = serverResult.taskResults.some((taskResult) => taskResult.status === "error");
            return (
              <div key={serverResult.serverId} className="bg-card border border-border rounded-lg overflow-hidden">
                <div className={`flex items-center gap-3 px-4 py-3 border-b border-border ${allDone ? (allOk ? "bg-primary/5" : hasError ? "bg-destructive/5" : "bg-secondary/20") : ""}`}>
                  <Server className="h-4 w-4 text-primary" />
                  <span className="text-sm font-medium text-foreground">{serverResult.serverName}</span>
                  <div className="ml-auto flex items-center gap-1.5">
                    {allDone && allOk && <CheckCircle2 className="h-4 w-4 text-primary" />}
                    {allDone && hasError && <XCircle className="h-4 w-4 text-destructive" />}
                    {!allDone && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                  </div>
                </div>
                <div className="divide-y divide-border">
                  {serverResult.taskResults.map((taskResult, taskIndex) => (
                    <div key={taskResult.taskId} className="px-4 py-3">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-[10px] font-mono text-muted-foreground bg-secondary rounded px-1.5 py-0.5">#{taskIndex + 1}</span>
                        <code className="text-xs font-mono text-foreground">{taskResult.command}</code>
                        <span className="ml-auto">
                          {taskResult.status === "success" && <CheckCircle2 className="h-3.5 w-3.5 text-primary" />}
                          {taskResult.status === "error" && <XCircle className="h-3.5 w-3.5 text-destructive" />}
                          {taskResult.status === "running" && <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />}
                          {taskResult.status === "pending" && <span className="h-3.5 w-3.5 rounded-full bg-muted-foreground/20 inline-block" />}
                          {taskResult.status === "skipped" && <span className="text-[10px] text-muted-foreground">{t("pb.skipped")}</span>}
                        </span>
                      </div>
                      {taskResult.output && (
                        <pre className="mt-2 p-2.5 rounded bg-background border border-border text-[11px] font-mono text-muted-foreground overflow-x-auto max-h-32 whitespace-pre-wrap">{taskResult.output}</pre>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </section>
      )}
    </>
  );
}
