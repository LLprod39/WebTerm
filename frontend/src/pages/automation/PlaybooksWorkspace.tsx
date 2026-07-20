import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  History,
  Plus,
  Search,
  Upload,
  Wand2,
} from "lucide-react";
import {
  cancelPlaybookRun,
  createPlaybook,
  deletePlaybook,
  duplicatePlaybook,
  fetchAnsibleStatus,
  getPlaybook,
  getPlaybookRun,
  importPlaybook,
  installPlaybookTemplate,
  listPlaybookRuns,
  listPlaybookTemplates,
  listPlaybooks,
  rerunFailedPlaybookHosts,
  runPlaybook,
  updatePlaybook,
  type PlaybookCategory,
  type PlaybookInventoryBindings,
  type PlaybookRun,
  type PlaybookSummary,
  type PlaybookTemplate,
} from "@/api/playbooks";
import { fetchFrontendBootstrap, type FrontendGroup, type FrontendServer } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { notify } from "@/lib/notify";
import { DeleteDialog } from "@/components/system/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn, relativeTime } from "@/lib/utils";
import { GuidedBuilder } from "./GuidedBuilder";
import { PlaybookCard } from "./PlaybookCard";
import { PlaybookEditor, type PlaybookEditorState } from "./PlaybookEditor";
import { RunResultsView } from "./RunResultsView";
import { RunWizard } from "./RunWizard";
import { CATEGORIES, CATEGORY_META, RUN_STATUS_META } from "./constants";
import { detailToPlaybookEditor, emptyPlaybookEditor } from "./playbookEditorState";

type View =
  | { mode: "catalog" }
  | { mode: "guided" }
  | { mode: "edit"; playbookId: number | null }
  | { mode: "run-wizard"; playbookId: number }
  | { mode: "run-results"; runId: number };

export interface PlaybooksWorkspaceProps {
  /** When provided, skip bootstrap fetch for inventory targets */
  servers?: FrontendServer[];
  groups?: FrontendGroup[];
  /** Load data only when tab is active */
  enabled?: boolean;
}

export function PlaybooksWorkspace({
  servers: serversProp,
  groups: groupsProp,
  enabled = true,
}: PlaybooksWorkspaceProps) {
  const { lang } = useI18n();
  const tr = useCallback((ru: string, en: string) => (lang === "ru" ? ru : en), [lang]);
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [view, setView] = useState<View>({ mode: "catalog" });
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<PlaybookCategory | "all">("all");
  const [editor, setEditor] = useState<PlaybookEditorState>(emptyPlaybookEditor);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [activeRun, setActiveRun] = useState<PlaybookRun | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PlaybookSummary | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const needBootstrap = serversProp === undefined || groupsProp === undefined;
  const bootstrapQuery = useQuery({
    queryKey: ["frontend", "bootstrap"],
    queryFn: fetchFrontendBootstrap,
    staleTime: 30_000,
    enabled: enabled && needBootstrap,
  });

  const servers: FrontendServer[] = serversProp ?? bootstrapQuery.data?.servers ?? [];
  const groups: FrontendGroup[] = (groupsProp ?? bootstrapQuery.data?.groups ?? []).filter(
    (g) => g.id != null,
  );

  const playbooksQuery = useQuery({
    queryKey: ["playbooks", categoryFilter, search],
    queryFn: () =>
      listPlaybooks({
        category: categoryFilter === "all" ? undefined : categoryFilter,
        q: search.trim() || undefined,
      }),
    enabled,
  });

  const templatesQuery = useQuery({
    queryKey: ["playbook-templates"],
    queryFn: listPlaybookTemplates,
    staleTime: 60_000,
    enabled,
  });

  const ansibleQuery = useQuery({
    queryKey: ["playbook-ansible-status"],
    queryFn: fetchAnsibleStatus,
    staleTime: 30_000,
    enabled,
  });

  const runsQuery = useQuery({
    queryKey: ["playbook-runs"],
    queryFn: listPlaybookRuns,
    enabled: enabled && (showHistory || view.mode === "run-results"),
  });

  const playbooks = playbooksQuery.data?.playbooks || [];
  const templates = templatesQuery.data?.templates || [];
  const recentRuns = runsQuery.data?.runs || [];
  const ansible = ansibleQuery.data?.ansible;
  const ansibleAvailable = Boolean(ansible?.available);

  useEffect(() => {
    if (view.mode !== "run-results") return;
    const runId = view.runId;
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const res = await getPlaybookRun(runId);
        if (cancelled) return;
        setActiveRun(res.run);
        if (res.run.status === "pending" || res.run.status === "running") {
          timer = window.setTimeout(() => void tick(), 1200);
        } else {
          // Terminal status — stop polling and refresh lists once
          void queryClient.invalidateQueries({ queryKey: ["playbooks"] });
          void queryClient.invalidateQueries({ queryKey: ["playbook-runs"] });
        }
      } catch {
        if (!cancelled) timer = window.setTimeout(() => void tick(), 3000);
      }
    };
    void tick();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [view, queryClient]);

  const openNew = () => {
    setEditor(emptyPlaybookEditor());
    setView({ mode: "edit", playbookId: null });
  };

  const openEdit = async (id: number) => {
    try {
      const res = await getPlaybook(id);
      setEditor(detailToPlaybookEditor(res.playbook));
      setView({ mode: "edit", playbookId: id });
    } catch (err) {
      notify.error({ title: tr("Не удалось открыть playbook", "Failed to open playbook"), description: String(err) });
    }
  };

  const buildPayload = () => {
    const tags = editor.tagsText
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    const tasks = editor.tasks
      .filter((t) => t.command.trim())
      .map((t) => ({
        id: t.id,
        command: t.command.trim(),
        description: t.description.trim(),
        continue_on_error: t.continue_on_error,
      }));
    return {
      name: editor.name.trim(),
      description: editor.description.trim(),
      kind: editor.kind,
      category: editor.category,
      visibility: editor.visibility,
      tags,
      tasks,
    };
  };

  const onSave = async () => {
    setSaving(true);
    try {
      const payload = buildPayload();
      if (!payload.name || (payload.tasks.length === 0 && !editor.sourceYaml)) {
        notify.error({ title: tr("Имя и задачи обязательны", "Name and tasks required") });
        return;
      }
      if (view.mode === "edit" && view.playbookId) {
        const res = await updatePlaybook(view.playbookId, payload);
        setEditor(detailToPlaybookEditor(res.playbook));
        notify.success({ title: tr("Сохранено", "Saved") });
      } else {
        const res = await createPlaybook(payload);
        setEditor(detailToPlaybookEditor(res.playbook));
        setView({ mode: "edit", playbookId: res.playbook.id });
        notify.success({ title: tr("Создано", "Created") });
      }
      await queryClient.invalidateQueries({ queryKey: ["playbooks"] });
    } catch (err) {
      notify.error({ title: tr("Ошибка сохранения", "Save failed"), description: String(err) });
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deletePlaybook(deleteTarget.id);
      notify.success({ title: tr("Удалено", "Deleted") });
      setDeleteTarget(null);
      if (view.mode === "edit" && view.playbookId === deleteTarget.id) setView({ mode: "catalog" });
      await queryClient.invalidateQueries({ queryKey: ["playbooks"] });
    } catch (err) {
      notify.error({ title: tr("Не удалось удалить", "Delete failed"), description: String(err) });
    }
  };

  const onDuplicate = async (id: number) => {
    try {
      await duplicatePlaybook(id);
      notify.success({ title: tr("Копия создана", "Duplicated") });
      await queryClient.invalidateQueries({ queryKey: ["playbooks"] });
    } catch (err) {
      notify.error({ title: tr("Ошибка", "Error"), description: String(err) });
    }
  };

  const onImportFile = async (file: File) => {
    try {
      const content = await file.text();
      const res = await importPlaybook({ content, filename: file.name, save: true });
      if (!res.success || !res.playbook) throw new Error(res.error || "Import failed");
      const fidelity = res.playbook.fidelity;
      const score = typeof fidelity?.score === "number" ? Math.round(fidelity.score * 100) : null;
      notify.success({
        title: tr("Импортировано", "Imported"),
        description:
          score !== null
            ? `${score}% · ${fidelity?.runnable}/${fidelity?.total} runnable`
            : res.playbook.name,
      });
      setEditor(detailToPlaybookEditor(res.playbook));
      setView({ mode: "edit", playbookId: res.playbook.id });
      await queryClient.invalidateQueries({ queryKey: ["playbooks"] });
    } catch (err) {
      notify.error({ title: tr("Импорт не удался", "Import failed"), description: String(err) });
    }
  };

  const onInstallTemplate = async (tmpl: PlaybookTemplate) => {
    try {
      const res = await installPlaybookTemplate(tmpl.slug);
      notify.success({ title: tr("Шаблон добавлен", "Template installed") });
      setEditor(detailToPlaybookEditor(res.playbook));
      setView({ mode: "edit", playbookId: res.playbook.id });
      await queryClient.invalidateQueries({ queryKey: ["playbooks"] });
    } catch (err) {
      notify.error({ title: tr("Ошибка", "Error"), description: String(err) });
    }
  };

  const startRunWizard = async (playbookId: number) => {
    try {
      const res = await getPlaybook(playbookId);
      setEditor(detailToPlaybookEditor(res.playbook));
      setView({ mode: "run-wizard", playbookId });
    } catch (err) {
      notify.error({ title: tr("Не удалось открыть", "Failed to open"), description: String(err) });
    }
  };

  const ensureSavedThenWizard = async () => {
    setSaving(true);
    try {
      const payload = buildPayload();
      if (!payload.name || (payload.tasks.length === 0 && !editor.sourceYaml)) {
        notify.error({ title: tr("Имя и задачи обязательны", "Name and tasks required") });
        return;
      }
      if (view.mode === "edit" && view.playbookId) {
        await updatePlaybook(view.playbookId, payload);
        setView({ mode: "run-wizard", playbookId: view.playbookId });
      } else {
        const res = await createPlaybook(payload);
        setView({ mode: "run-wizard", playbookId: res.playbook.id });
      }
      await queryClient.invalidateQueries({ queryKey: ["playbooks"] });
    } catch (err) {
      notify.error({ title: tr("Ошибка", "Error"), description: String(err) });
    } finally {
      setSaving(false);
    }
  };

  const onConfirmRun = async (opts: {
    server_ids: number[];
    group_ids: number[];
    concurrency: number;
    dry_run: boolean;
    become: boolean;
    inventory_bindings: PlaybookInventoryBindings;
  }) => {
    const playbookId =
      view.mode === "run-wizard" ? view.playbookId : view.mode === "edit" ? view.playbookId : null;
    if (!playbookId) return;
    setRunning(true);
    try {
      const res = await runPlaybook(playbookId, { ...opts, engine: "ansible" });
      setActiveRun(res.run);
      setView({ mode: "run-results", runId: res.run.id });
      await queryClient.invalidateQueries({ queryKey: ["playbook-runs"] });
    } catch (err) {
      notify.error({ title: tr("Запуск не удался", "Run failed"), description: String(err) });
    } finally {
      setRunning(false);
    }
  };

  const onCancelRun = async () => {
    if (view.mode !== "run-results") return;
    setCancelling(true);
    try {
      const res = await cancelPlaybookRun(view.runId);
      setActiveRun(res.run);
    } catch (err) {
      notify.error({ title: tr("Не удалось отменить", "Cancel failed"), description: String(err) });
    } finally {
      setCancelling(false);
    }
  };

  const onRerunFailed = async () => {
    if (view.mode !== "run-results") return;
    try {
      const res = await rerunFailedPlaybookHosts(view.runId);
      setActiveRun(res.run);
      setView({ mode: "run-results", runId: res.run.id });
    } catch (err) {
      notify.error({ title: tr("Re-run failed", "Re-run failed"), description: String(err) });
    }
  };

  const groupsWithId = useMemo(
    () => groups.filter((g): g is FrontendGroup & { id: number } => g.id != null),
    [groups],
  );

  return (
    <div className="space-y-3">
      <input
        ref={fileInputRef}
        type="file"
        accept=".yml,.yaml,.json"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void onImportFile(file);
          e.target.value = "";
        }}
      />

      {view.mode === "catalog" ? (
        <>
          {/* Header */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-center gap-2.5">
              <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
                Playbooks
              </h2>
              {!playbooksQuery.isLoading ? (
                <span className="rounded-full border border-border bg-secondary/40 px-2 py-0.5 font-mono text-2xs text-muted-foreground">
                  {playbooks.length}
                </span>
              ) : null}
              {ansible ? (
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-2xs",
                    ansibleAvailable
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                      : "border-amber-500/30 bg-amber-500/10 text-amber-300",
                  )}
                  title={ansibleAvailable ? [ansible.method, ansible.version].filter(Boolean).join(" · ") : undefined}
                >
                  <span
                    aria-hidden
                    className={cn("h-1.5 w-1.5 rounded-full", ansibleAvailable ? "bg-emerald-400" : "bg-amber-400")}
                  />
                  Ansible
                  {ansibleAvailable && ansible.version ? (
                    <span className="font-mono opacity-70">{ansible.version}</span>
                  ) : null}
                </span>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <Button
                size="sm"
                variant={showHistory ? "secondary" : "ghost"}
                className="h-8 gap-1.5 text-muted-foreground hover:text-foreground"
                onClick={() => {
                  setShowHistory((v) => !v);
                  void queryClient.invalidateQueries({ queryKey: ["playbook-runs"] });
                }}
              >
                <History className="h-3.5 w-3.5" />
                {tr("Запуски", "Runs")}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-8 gap-1.5 text-muted-foreground hover:text-foreground"
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="h-3.5 w-3.5" />
                {tr("Импорт", "Import")}
              </Button>
              <div aria-hidden className="mx-1 hidden h-5 w-px bg-border sm:block" />
              <Button size="sm" variant="outline" className="h-8 gap-1.5" onClick={() => setView({ mode: "guided" })}>
                <Wand2 className="h-3.5 w-3.5" />
                {tr("Мастер", "Wizard")}
              </Button>
              <Button size="sm" className="h-8 gap-1.5 shadow-elev-1" onClick={openNew}>
                <Plus className="h-3.5 w-3.5" />
                {tr("Новый playbook", "New playbook")}
              </Button>
            </div>
          </div>

          {/* Warning only when ansible is missing on the backend */}
          {!ansibleAvailable && ansible ? (
            <div className="rounded-sm border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-foreground">
              <span className="font-medium">{tr("Ansible не найден на backend", "Ansible not found on backend")}</span>
              {ansible.message ? (
                <p className="mt-0.5 text-2xs text-muted-foreground">{ansible.message}</p>
              ) : null}
            </div>
          ) : null}

          {showHistory ? (
            <div className="overflow-hidden rounded-md border border-border bg-card">
              <div className="flex items-center gap-2 border-b border-border px-3 py-2">
                <History className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">
                  {tr("Недавние запуски", "Recent runs")}
                </span>
              </div>
              <div className="max-h-56 divide-y divide-border/70 overflow-y-auto">
                {recentRuns.length === 0 ? (
                  <p className="px-3 py-5 text-center text-xs text-muted-foreground">
                    {tr("Запусков пока не было", "No runs yet")}
                  </p>
                ) : (
                  recentRuns.slice(0, 15).map((run) => {
                    const meta = RUN_STATUS_META[run.status];
                    return (
                      <button
                        key={run.id}
                        type="button"
                        onClick={() => {
                          setActiveRun(run);
                          setView({ mode: "run-results", runId: run.id });
                        }}
                        className="flex w-full items-center gap-3 px-3 py-2 text-left text-xs transition-colors hover:bg-secondary/40"
                      >
                        <span
                          aria-hidden
                          className={cn("h-1.5 w-1.5 shrink-0 rounded-full", meta?.dot || "bg-muted-foreground/60")}
                        />
                        <span className="min-w-0 flex-1 truncate font-medium text-foreground">
                          {run.playbook_name}
                        </span>
                        <span className={cn("shrink-0", meta?.className || "text-muted-foreground")}>
                          {meta ? (lang === "ru" ? meta.labelRu : meta.labelEn) : run.status}
                        </span>
                        <span className="shrink-0 font-mono text-muted-foreground/60">
                          {run.started_at ? relativeTime(run.started_at) : `#${run.id}`}
                        </span>
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          ) : null}

          {/* Search + category filters */}
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
            <div className="relative w-full min-w-0 lg:max-w-xs">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={tr("Поиск playbook…", "Search playbooks…")}
                className="h-8 bg-card pl-8 text-sm"
              />
            </div>
            <div className="flex flex-wrap items-center gap-1">
              <button
                type="button"
                onClick={() => setCategoryFilter("all")}
                className={cn(
                  "h-7 rounded-full border px-2.5 text-xs font-medium transition-colors",
                  categoryFilter === "all"
                    ? "border-primary/40 bg-primary/10 text-primary"
                    : "border-border bg-card text-muted-foreground hover:border-border hover:text-foreground",
                )}
              >
                {tr("Все", "All")}
              </button>
              {CATEGORIES.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setCategoryFilter(c)}
                  className={cn(
                    "h-7 rounded-full border px-2.5 text-xs font-medium transition-colors",
                    categoryFilter === c
                      ? CATEGORY_META[c].kicker
                      : "border-border bg-card text-muted-foreground hover:text-foreground",
                  )}
                >
                  {lang === "ru" ? CATEGORY_META[c].labelRu : CATEGORY_META[c].labelEn}
                </button>
              ))}
            </div>
          </div>

          {/* Templates — quick start */}
          {templates.length > 0 ? (
            <div className="rounded-md border border-border/70 bg-surface-0/40 px-3 py-2.5">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-2xs font-medium uppercase tracking-wider text-muted-foreground">
                  {tr("Быстрый старт", "Quick start")}
                </span>
                {templates.map((tmpl) => (
                  <button
                    key={tmpl.slug}
                    type="button"
                    onClick={() => void onInstallTemplate(tmpl)}
                    className="inline-flex h-7 items-center gap-1 rounded-full border border-border bg-card px-2.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                    title={tmpl.description}
                  >
                    <Plus className="h-3 w-3 opacity-60" />
                    {tmpl.name}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {/* Drop zone + list */}
          {playbooksQuery.isLoading ? (
            <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3" aria-busy="true">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-40 animate-pulse rounded-md border border-border/60 bg-card/60" />
              ))}
            </div>
          ) : playbooks.length === 0 ? (
            <div
              className="rounded-md border border-dashed border-border bg-card/40 px-6 py-14 text-center"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const file = e.dataTransfer.files[0];
                if (file) void onImportFile(file);
              }}
            >
              {search.trim() || categoryFilter !== "all" ? (
                <>
                  <Search className="mx-auto mb-3 h-8 w-8 text-muted-foreground/35" />
                  <p className="font-display text-sm font-semibold text-foreground">
                    {tr("Ничего не найдено", "Nothing found")}
                  </p>
                  <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">
                    {tr("Попробуйте изменить запрос или сбросить фильтры", "Try a different query or reset the filters")}
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="mt-4 h-8"
                    onClick={() => {
                      setSearch("");
                      setCategoryFilter("all");
                    }}
                  >
                    {tr("Сбросить фильтры", "Reset filters")}
                  </Button>
                </>
              ) : (
                <>
                  <BookOpen className="mx-auto mb-3 h-8 w-8 text-muted-foreground/35" />
                  <p className="font-display text-sm font-semibold text-foreground">
                    {tr("Пока нет ни одного playbook", "No playbooks yet")}
                  </p>
                  <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">
                    {tr(
                      "Соберите первый через мастер, начните с шаблона или перетащите сюда готовый .yml",
                      "Build your first one with the wizard, start from a template, or drop a .yml file here",
                    )}
                  </p>
                  <div className="mt-4 flex flex-wrap justify-center gap-2">
                    <Button size="sm" className="h-8 gap-1" onClick={() => setView({ mode: "guided" })}>
                      <Wand2 className="h-3.5 w-3.5" />
                      {tr("Мастер", "Wizard")}
                    </Button>
                    <Button size="sm" variant="outline" className="h-8 gap-1" onClick={openNew}>
                      <Plus className="h-3.5 w-3.5" />
                      {tr("Создать", "Create")}
                    </Button>
                    <Button size="sm" variant="outline" className="h-8 gap-1" onClick={() => fileInputRef.current?.click()}>
                      <Upload className="h-3.5 w-3.5" />
                      {tr("Импорт YAML", "Import YAML")}
                    </Button>
                  </div>
                </>
              )}
            </div>
          ) : (
            <div
              className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const file = e.dataTransfer.files[0];
                if (file) void onImportFile(file);
              }}
            >
              {playbooks.map((pb) => (
                <PlaybookCard
                  key={pb.id}
                  playbook={pb}
                  lang={lang}
                  onOpen={() => void openEdit(pb.id)}
                  onRun={() => void startRunWizard(pb.id)}
                  onDuplicate={() => void onDuplicate(pb.id)}
                  onDelete={() => setDeleteTarget(pb)}
                />
              ))}
            </div>
          )}
        </>
      ) : null}

      {view.mode === "guided" ? (
        <GuidedBuilder
          lang={lang}
          onBack={() => setView({ mode: "catalog" })}
          onCreated={(pb) => {
            setEditor(detailToPlaybookEditor(pb));
            setView({ mode: "edit", playbookId: pb.id });
            void queryClient.invalidateQueries({ queryKey: ["playbooks"] });
          }}
        />
      ) : null}

      {view.mode === "edit" ? (
        <PlaybookEditor
          lang={lang}
          state={editor}
          saving={saving}
          onChange={(patch) => setEditor((prev) => ({ ...prev, ...patch }))}
          onSave={() => void onSave()}
          onBack={() => setView({ mode: "catalog" })}
          onRun={() => {
            if (view.playbookId) setView({ mode: "run-wizard", playbookId: view.playbookId });
            else void ensureSavedThenWizard();
          }}
          title={view.playbookId ? tr("Редактирование", "Edit playbook") : tr("Новый playbook", "New playbook")}
          playbookId={view.playbookId}
          onCompatibilityApplied={(playbook) => setEditor(detailToPlaybookEditor(playbook))}
        />
      ) : null}

      {view.mode === "run-wizard" ? (
        <RunWizard
          lang={lang}
          playbookName={editor.name || "Playbook"}
          servers={servers}
          groups={groupsWithId}
          running={running}
          ansibleAvailable={ansibleAvailable}
          playbookId={view.playbookId}
          compatibility={editor.activeCompatibilityRevision?.report || editor.compatibility}
          onBack={() => setView({ mode: "edit", playbookId: view.playbookId })}
          onConfirm={(opts) => void onConfirmRun(opts)}
        />
      ) : null}

      {view.mode === "run-results" && activeRun ? (
        <RunResultsView
          lang={lang}
          run={activeRun}
          onBack={() => setView({ mode: "catalog" })}
          onCancel={() => void onCancelRun()}
          onRerunFailed={() => void onRerunFailed()}
          cancelling={cancelling}
        />
      ) : null}

      {view.mode === "run-results" && !activeRun ? (
        <div className="py-12 text-center text-sm text-muted-foreground">{tr("Загрузка run…", "Loading run…")}</div>
      ) : null}

      <DeleteDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title={tr("Удалить playbook?", "Delete playbook?")}
        description={
          deleteTarget
            ? tr(`«${deleteTarget.name}» будет удалён.`, `"${deleteTarget.name}" will be deleted.`)
            : ""
        }
        confirmLabel={tr("Удалить", "Delete")}
        cancelLabel={tr("Отмена", "Cancel")}
        onConfirm={() => void onDelete()}
      />
    </div>
  );
}

export default PlaybooksWorkspace;
