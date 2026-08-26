import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { runValidatedPlaybook, type PlaybookRunRequest } from "@/api/playbook-preflight";
import {
  cancelPlaybookRun,
  createPlaybook,
  deletePlaybook,
  duplicatePlaybook,
  fetchAnsibleStatus,
  getPlaybook,
  getPlaybookRunRetryContext,
  installPlaybookTemplate,
  listPlaybookRuns,
  listPlaybookTemplates,
  listPlaybooks,
  updatePlaybook,
  type PlaybookCategory,
  type PlaybookDetail,
  type PlaybookRun,
  type PlaybookRunRetryContext,
  type PlaybookSummary,
  type PlaybookTemplate,
} from "@/api/playbooks";
import { fetchFrontendBootstrap, type FrontendGroup, type FrontendServer } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { notify } from "@/lib/notify";
import {
  buildPlaybookPayload,
  detailToPlaybookEditor,
  emptyPlaybookEditor,
  isPlaybookEditorDirty,
  isPlaybookEditorContentDirty,
  isPlaybookEditorMetadataDirty,
  markPlaybookEditorMetadataSaved,
  type PlaybookEditorState,
} from "../playbookEditorState";
import type { PlaybooksWorkspaceProps } from "./types";
import { usePlaybookRunPolling } from "./usePlaybookRunPolling";
import { usePlaybookWorkspaceVersioning } from "./usePlaybookWorkspaceVersioning";
import { usePlaybooksWorkspaceNavigation } from "./usePlaybooksWorkspaceNavigation";

export function usePlaybooksWorkspace({
  servers: serversProp,
  groups: groupsProp,
  enabled = true,
  initialView,
  onViewChange,
}: PlaybooksWorkspaceProps) {
  const { lang } = useI18n();
  const tr = useCallback((ru: string, en: string) => (lang === "ru" ? ru : en), [lang]);
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<PlaybookCategory | "all">("all");
  const [editor, setEditor] = useState<PlaybookEditorState>(emptyPlaybookEditor);
  const [openedPlaybook, setOpenedPlaybook] = useState<PlaybookDetail | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [activeRun, setActiveRun] = useState<PlaybookRun | null>(null);
  const [retryContext, setRetryContext] = useState<PlaybookRunRetryContext | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PlaybookSummary | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const editorDirty = useMemo(() => isPlaybookEditorDirty(editor), [editor]);
  const { view, setView } = usePlaybooksWorkspaceNavigation({
    initialView,
    onViewChange,
    editorDirty,
    setSaveError,
    tr,
  });
  const { runLoadError, retryRunLoad } = usePlaybookRunPolling({
    view,
    queryClient,
    setActiveRun,
  });

  useEffect(() => {
    if (view.mode !== "run-wizard") setRetryContext(null);
  }, [view.mode]);

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
    refetchInterval: enabled ? 15_000 : false,
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
  const workspacePlaybookId =
    view.mode === "edit" || view.mode === "run-wizard" ? view.playbookId : null;
  const workspace = usePlaybookWorkspaceVersioning({
    enabled:
      enabled &&
      Boolean(workspacePlaybookId) &&
      openedPlaybook?.id === workspacePlaybookId,
    playbookId: workspacePlaybookId,
    playbook: openedPlaybook,
    editor,
    setEditor,
    tr,
  });

  const openNew = () => {
    setEditor(emptyPlaybookEditor());
    setOpenedPlaybook(null);
    setSaveError(null);
    setView({ mode: "edit", playbookId: null });
  };

  const openEdit = async (id: number) => {
    try {
      const res = await getPlaybook(id);
      setEditor(detailToPlaybookEditor(res.playbook));
      setOpenedPlaybook(res.playbook);
      setSaveError(null);
      setView({ mode: "edit", playbookId: id });
    } catch (err) {
      notify.error({ title: tr("Не удалось открыть playbook", "Failed to open playbook"), description: String(err) });
    }
  };

  useEffect(() => {
    const playbookId = view.mode === "edit" || view.mode === "run-wizard" ? view.playbookId : null;
    if (!enabled || !playbookId || openedPlaybook?.id === playbookId) return;
    let cancelled = false;
    void getPlaybook(playbookId)
      .then((res) => {
        if (cancelled) return;
        setEditor(detailToPlaybookEditor(res.playbook));
        setOpenedPlaybook(res.playbook);
        setSaveError(null);
      })
      .catch((error) => {
        if (cancelled) return;
        notify.error({
          title: tr("Не удалось открыть playbook", "Failed to open playbook"),
          description: String(error),
        });
        setView({ mode: "catalog" });
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, openedPlaybook?.id, setView, tr, view]);

  const updateEditor = useCallback((patch: Partial<PlaybookEditorState>) => {
    setSaveError(null);
    setEditor((previous) => ({ ...previous, ...patch }));
  }, []);

  const onCompatibilityApplied = useCallback((playbook: PlaybookDetail) => {
    setOpenedPlaybook(playbook);
    setSaveError(null);
    setEditor((current) => ({
      ...current,
      compatibility: playbook.compatibility || {},
      activeCompatibilityRevision: playbook.active_compatibility_revision || null,
    }));
    // Apply updates the draft/revision graph. The refreshed draft, not the
    // currently published playbook payload, remains the editor source of truth.
    void Promise.all([
      queryClient.invalidateQueries({ queryKey: ["playbook-workspace", "draft", playbook.id] }),
      queryClient.invalidateQueries({ queryKey: ["playbook-workspace", "revisions", playbook.id] }),
      queryClient.invalidateQueries({ queryKey: ["playbooks"] }),
    ]);
  }, [queryClient]);

  const leaveEditor = useCallback(() => {
    if (
      editorDirty &&
      !window.confirm(
        tr(
          "Есть несохранённые изменения. Выйти без сохранения?",
          "You have unsaved changes. Leave without saving?",
        ),
      )
    ) {
      return;
    }
    setSaveError(null);
    setView({ mode: "catalog" });
  }, [editorDirty, setView, tr]);

  const onSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const payload = buildPlaybookPayload(editor);
      if (!payload.name || (!payload.source_yaml?.trim() && !payload.tasks?.length)) {
        const message = tr("Имя и исполняемый контент обязательны", "Name and executable content are required");
        setSaveError(message);
        notify.error({ title: message });
        return;
      }
      if (view.mode === "edit" && view.playbookId) {
        if (isPlaybookEditorContentDirty(editor)) {
          const draft = await workspace.saveDraftNow();
          if (!draft) throw new Error(tr("Черновик не сохранён", "Draft was not saved"));
        }
        if (isPlaybookEditorMetadataDirty(editor)) {
          const { source_yaml: _sourceYaml, tasks: _tasks, kind: _kind, ...metadata } = payload;
          const res = await updatePlaybook(view.playbookId, metadata);
          setOpenedPlaybook(res.playbook);
          setEditor((current) => markPlaybookEditorMetadataSaved(current));
        }
        notify.success({ title: tr("Сохранено", "Saved") });
      } else {
        const res = await createPlaybook(payload);
        setEditor(detailToPlaybookEditor(res.playbook));
        setOpenedPlaybook(res.playbook);
        setView({ mode: "edit", playbookId: res.playbook.id });
        notify.success({ title: tr("Создано", "Created") });
      }
      await queryClient.invalidateQueries({ queryKey: ["playbooks"] });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setSaveError(message);
      notify.error({ title: tr("Ошибка сохранения", "Save failed"), description: message });
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

  const onInstallTemplate = async (tmpl: PlaybookTemplate) => {
    try {
      const res = await installPlaybookTemplate(tmpl.slug);
      notify.success({ title: tr("Шаблон добавлен", "Template installed") });
      setEditor(detailToPlaybookEditor(res.playbook));
      setOpenedPlaybook(res.playbook);
      setSaveError(null);
      setView({ mode: "edit", playbookId: res.playbook.id });
      await queryClient.invalidateQueries({ queryKey: ["playbooks"] });
    } catch (err) {
      notify.error({ title: tr("Ошибка", "Error"), description: String(err) });
    }
  };

  const startRunWizard = async (playbookId: number) => {
    try {
      setRetryContext(null);
      const res = await getPlaybook(playbookId);
      setEditor(detailToPlaybookEditor(res.playbook));
      setOpenedPlaybook(res.playbook);
      setView({ mode: "run-wizard", playbookId });
    } catch (err) {
      notify.error({ title: tr("Не удалось открыть", "Failed to open"), description: String(err) });
    }
  };

  const ensureSavedThenWizard = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const payload = buildPlaybookPayload(editor);
      if (!payload.name || (!payload.source_yaml?.trim() && !payload.tasks?.length)) {
        const message = tr("Имя и исполняемый контент обязательны", "Name and executable content are required");
        setSaveError(message);
        notify.error({ title: message });
        return;
      }
      if (view.mode === "edit" && view.playbookId) {
        if (isPlaybookEditorContentDirty(editor)) {
          const draft = await workspace.saveDraftNow();
          if (!draft) throw new Error(tr("Черновик не сохранён", "Draft was not saved"));
        }
        if (isPlaybookEditorMetadataDirty(editor)) {
          const { source_yaml: _sourceYaml, tasks: _tasks, kind: _kind, ...metadata } = payload;
          const res = await updatePlaybook(view.playbookId, metadata);
          setOpenedPlaybook(res.playbook);
          setEditor((current) => markPlaybookEditorMetadataSaved(current));
        }
        setRetryContext(null);
        setView({ mode: "run-wizard", playbookId: view.playbookId });
      } else {
        const res = await createPlaybook(payload);
        setEditor(detailToPlaybookEditor(res.playbook));
        setOpenedPlaybook(res.playbook);
        setView({ mode: "run-wizard", playbookId: res.playbook.id });
      }
      await queryClient.invalidateQueries({ queryKey: ["playbooks"] });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setSaveError(message);
      notify.error({ title: tr("Ошибка", "Error"), description: message });
    } finally {
      setSaving(false);
    }
  };

  const onConfirmRun = async (opts: PlaybookRunRequest) => {
    const playbookId =
      view.mode === "run-wizard" ? view.playbookId : view.mode === "edit" ? view.playbookId : null;
    if (!playbookId) return;
    setRunning(true);
    try {
      const res = await runValidatedPlaybook(playbookId, opts);
      setRetryContext(null);
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
      const response = await getPlaybookRunRetryContext(view.runId);
      const context = response.retry_context;
      if (!context.can_retry || !context.playbook_id) {
        throw new Error(context.blockers.map((blocker) => blocker.message).join(" ") || tr("Безопасный повтор недоступен", "Safe retry is unavailable"));
      }
      const playbook = await getPlaybook(context.playbook_id);
      setEditor(detailToPlaybookEditor(playbook.playbook));
      setOpenedPlaybook(playbook.playbook);
      setRetryContext(context);
      setView({ mode: "run-wizard", playbookId: context.playbook_id });
    } catch (err) {
      notify.error({ title: tr("Повтор недоступен", "Retry unavailable"), description: String(err) });
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
    view,
    setView,
    search,
    setSearch,
    categoryFilter,
    setCategoryFilter,
    editor,
    setEditor,
    openedPlaybook,
    setOpenedPlaybook,
    updateEditor,
    editorDirty,
    saving,
    saveError,
    running,
    cancelling,
    activeRun,
    retryContext,
    setActiveRun,
    runLoadError,
    retryRunLoad,
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
    leaveEditor,
    onSave,
    onDelete,
    onDuplicate,
    onInstallTemplate,
    startRunWizard,
    ensureSavedThenWizard,
    onConfirmRun,
    onCancelRun,
    onRerunFailed,
    onCompatibilityApplied,
    groupsWithId,
    workspace,
  };
}

export type PlaybooksWorkspaceController = ReturnType<typeof usePlaybooksWorkspace>;
