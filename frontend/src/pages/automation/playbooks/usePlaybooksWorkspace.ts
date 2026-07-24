import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

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
import { type PlaybookEditorState } from "../PlaybookEditor";
import { detailToPlaybookEditor, emptyPlaybookEditor } from "../playbookEditorState";
import type { PlaybooksView, PlaybooksWorkspaceProps } from "./types";

export function usePlaybooksWorkspace({
  servers: serversProp,
  groups: groupsProp,
  enabled = true,
}: PlaybooksWorkspaceProps) {
  const { lang } = useI18n();
  const tr = useCallback((ru: string, en: string) => (lang === "ru" ? ru : en), [lang]);
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [view, setView] = useState<PlaybooksView>({ mode: "catalog" });
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

  return {
    lang,
    tr,
    queryClient,
    fileInputRef,
    view,
    setView,
    search,
    setSearch,
    categoryFilter,
    setCategoryFilter,
    editor,
    setEditor,
    saving,
    running,
    cancelling,
    activeRun,
    setActiveRun,
    deleteTarget,
    setDeleteTarget,
    showHistory,
    setShowHistory,
    servers,
    playbooksQuery,
    playbooks,
    templates,
    recentRuns,
    ansible,
    ansibleAvailable,
    openNew,
    openEdit,
    onSave,
    onDelete,
    onDuplicate,
    onImportFile,
    onInstallTemplate,
    startRunWizard,
    ensureSavedThenWizard,
    onConfirmRun,
    onCancelRun,
    onRerunFailed,
    groupsWithId,
  };
}

export type PlaybooksWorkspaceController = ReturnType<typeof usePlaybooksWorkspace>;
