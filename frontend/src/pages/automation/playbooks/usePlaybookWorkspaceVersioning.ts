import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createPlaybookBinding,
  createPlaybookRevision,
  createPlaybookShare,
  deletePlaybookBinding,
  deletePlaybookShare,
  getPlaybookDraft,
  getPlaybookRevision,
  listPlaybookBindings,
  listPlaybookRevisions,
  listPlaybookShares,
  publishPlaybookRevision,
  rollbackPlaybookRevision,
  updatePlaybookBinding,
  updatePlaybookDraft,
  type PlaybookBindingProfile,
  type PlaybookDetail,
  type PlaybookDraft,
  type PlaybookRevision,
  type SavePlaybookBindingPayload,
} from "@/api/playbooks";
import { fetchAuthSession } from "@/lib/api";
import { notify } from "@/lib/notify";
import {
  applyDraftToPlaybookEditor,
  isPlaybookEditorContentDirty,
  markPlaybookEditorContentSaved,
  playbookEditorContentFingerprint,
  type PlaybookEditorState,
} from "../playbookEditorState";
import {
  bindingsKey,
  buildDraftContentPayload,
  draftKey,
  inferPlaybookCapabilities,
  revisionsKey,
  sharesKey,
  type DraftQueryPayload,
} from "./playbookWorkspaceVersioningState";

type AutosaveStatus = "idle" | "loading" | "dirty" | "saving" | "saved" | "conflict" | "error" | "readonly";

interface DraftConflictState {
  serverDraft: PlaybookDraft;
  message: string;
}

interface VersioningArgs {
  enabled: boolean;
  playbookId: number | null;
  playbook: PlaybookDetail | null;
  editor: PlaybookEditorState;
  setEditor: Dispatch<SetStateAction<PlaybookEditorState>>;
  tr: (ru: string, en: string) => string;
}

export function usePlaybookWorkspaceVersioning({
  enabled,
  playbookId,
  playbook,
  editor,
  setEditor,
  tr,
}: VersioningArgs) {
  const queryClient = useQueryClient();
  const editorRef = useRef(editor);
  const savePromiseRef = useRef<Promise<PlaybookDraft | null> | null>(null);
  const appliedDraftRef = useRef("");
  const failedFingerprintRef = useRef("");
  const [autosaveStatus, setAutosaveStatus] = useState<AutosaveStatus>("idle");
  const [autosaveError, setAutosaveError] = useState("");
  const [conflict, setConflict] = useState<DraftConflictState | null>(null);
  const [revisionBusy, setRevisionBusy] = useState<"create" | "publish" | "rollback" | "detail" | null>(null);
  const [selectedRevision, setSelectedRevision] = useState<PlaybookRevision | null>(null);
  const [bindingBusy, setBindingBusy] = useState(false);
  const [shareBusy, setShareBusy] = useState(false);
  editorRef.current = editor;

  const sessionQuery = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    enabled,
  });
  const draftQuery = useQuery({
    queryKey: draftKey(playbookId),
    queryFn: () => getPlaybookDraft(playbookId as number),
    enabled: enabled && Boolean(playbookId) && (playbook?.capabilities?.can_edit ?? true),
    retry: false,
  });
  const revisionsQuery = useQuery({
    queryKey: revisionsKey(playbookId),
    queryFn: () => listPlaybookRevisions(playbookId as number),
    enabled: enabled && Boolean(playbookId),
    retry: false,
  });
  const bindingsQuery = useQuery({
    queryKey: bindingsKey(playbookId),
    queryFn: () => listPlaybookBindings(playbookId as number),
    enabled:
      enabled &&
      Boolean(playbookId) &&
      (playbook?.capabilities
        ? playbook.capabilities.can_edit || playbook.capabilities.can_run
        : true),
    retry: false,
  });
  const sharesQuery = useQuery({
    queryKey: sharesKey(playbookId),
    queryFn: () => listPlaybookShares(playbookId as number),
    enabled: enabled && Boolean(playbookId) && (playbook?.capabilities?.can_share ?? true),
    retry: false,
  });

  const capabilities = useMemo(
    () =>
      inferPlaybookCapabilities({
        playbook,
        currentUserId: sessionQuery.data?.user?.id || null,
        draftAccessible: draftQuery.isSuccess,
        bindingsAccessible: bindingsQuery.isSuccess,
        sharesAccessible: sharesQuery.isSuccess,
      }),
    [
      bindingsQuery.isSuccess,
      draftQuery.isSuccess,
      playbook,
      sessionQuery.data?.user?.id,
      sharesQuery.isSuccess,
    ],
  );
  const capabilityReady = Boolean(
    playbook?.capabilities ||
      capabilities.is_owner ||
      (!sessionQuery.isPending && !draftQuery.isPending && !bindingsQuery.isPending && !sharesQuery.isPending),
  );
  const canEditContent = capabilities.can_edit && draftQuery.isSuccess;
  const contentDirty = isPlaybookEditorContentDirty(editor);
  const currentDraft = draftQuery.data?.draft || null;
  const baseRevision = revisionsQuery.data?.revisions.find((item) => item.id === currentDraft?.base_revision_id);
  const hasUnrevisionedChanges = Boolean(currentDraft && (!baseRevision || currentDraft.content_hash !== baseRevision.content_hash));
  const hasUnpublishedRevision = Boolean(
    currentDraft?.base_revision_id && currentDraft.base_revision_id !== revisionsQuery.data?.published_revision_id,
  );

  useEffect(() => {
    appliedDraftRef.current = "";
    setConflict(null);
    setAutosaveError("");
    failedFingerprintRef.current = "";
    setSelectedRevision(null);
  }, [playbookId]);

  useEffect(() => {
    const draft = draftQuery.data?.draft;
    if (!draft || !playbookId) return;
    const key = `${playbookId}:${draft.id}:${draft.version}:${draft.content_hash}`;
    if (appliedDraftRef.current === key) return;
    setEditor((previous) => {
      if (isPlaybookEditorContentDirty(previous)) return previous;
      return applyDraftToPlaybookEditor(previous, draft);
    });
    appliedDraftRef.current = key;
  }, [draftQuery.data?.draft, playbookId, setEditor]);

  const performDraftSave = useCallback(
    async (expectedDraft: PlaybookDraft, snapshot: PlaybookEditorState): Promise<PlaybookDraft | null> => {
      if (!playbookId || !capabilities.can_edit) return null;
      const submittedFingerprint = playbookEditorContentFingerprint(snapshot);
      setAutosaveStatus("saving");
      setAutosaveError("");
      try {
        const response = await updatePlaybookDraft(
          playbookId,
          buildDraftContentPayload(snapshot, expectedDraft.version),
        );
        queryClient.setQueryData(draftKey(playbookId), response);
        setEditor((current) =>
          playbookEditorContentFingerprint(current) === submittedFingerprint
            ? markPlaybookEditorContentSaved(current)
            : current,
        );
        setConflict(null);
        failedFingerprintRef.current = "";
        setAutosaveStatus(
          playbookEditorContentFingerprint(editorRef.current) === submittedFingerprint ? "saved" : "dirty",
        );
        return response.draft;
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        if (/conflict|changed by another editor/i.test(message)) {
          try {
            const latest = await getPlaybookDraft(playbookId);
            queryClient.setQueryData(draftKey(playbookId), latest);
            setConflict({ serverDraft: latest.draft, message });
            setAutosaveStatus("conflict");
          } catch {
            failedFingerprintRef.current = submittedFingerprint;
            setAutosaveError(message);
            setAutosaveStatus("error");
          }
        } else {
          failedFingerprintRef.current = submittedFingerprint;
          setAutosaveError(message);
          setAutosaveStatus("error");
        }
        return null;
      }
    },
    [capabilities.can_edit, playbookId, queryClient, setEditor],
  );

  const saveDraftNow = useCallback(async (): Promise<PlaybookDraft | null> => {
    if (!playbookId || !canEditContent) return null;
    const currentDraft = queryClient.getQueryData<DraftQueryPayload>(draftKey(playbookId))?.draft;
    if (!currentDraft) return null;
    if (!isPlaybookEditorContentDirty(editorRef.current)) return currentDraft;
    if (savePromiseRef.current) return savePromiseRef.current;
    const promise = performDraftSave(currentDraft, editorRef.current).finally(() => {
      savePromiseRef.current = null;
    });
    savePromiseRef.current = promise;
    return promise;
  }, [canEditContent, performDraftSave, playbookId, queryClient]);

  useEffect(() => {
    if (!playbookId) return;
    if (!capabilityReady || !capabilities.can_edit) {
      setAutosaveStatus(capabilityReady ? "readonly" : "loading");
      return;
    }
    if (!draftQuery.data?.draft) {
      setAutosaveStatus("loading");
      return;
    }
    if (conflict || autosaveStatus === "saving") return;
    if (
      autosaveStatus === "error" &&
      failedFingerprintRef.current === playbookEditorContentFingerprint(editorRef.current)
    ) {
      return;
    }
    if (!contentDirty) {
      setAutosaveStatus((current) => (current === "error" ? current : "saved"));
      return;
    }
    setAutosaveStatus("dirty");
    const timer = window.setTimeout(() => void saveDraftNow(), 900);
    return () => window.clearTimeout(timer);
  }, [
    autosaveStatus,
    capabilities.can_edit,
    capabilityReady,
    conflict,
    contentDirty,
    draftQuery.data?.draft,
    playbookId,
    saveDraftNow,
  ]);

  const retryDraftSave = useCallback(async () => {
    failedFingerprintRef.current = "";
    setAutosaveError("");
    setAutosaveStatus("dirty");
    return saveDraftNow();
  }, [saveDraftNow]);

  const acceptServerDraft = useCallback(() => {
    if (!conflict) return;
    setEditor((current) => applyDraftToPlaybookEditor(current, conflict.serverDraft));
    setConflict(null);
    setAutosaveError("");
    setAutosaveStatus("saved");
  }, [conflict, setEditor]);

  const keepLocalDraft = useCallback(async () => {
    if (!conflict) return;
    const saved = await performDraftSave(conflict.serverDraft, editorRef.current);
    if (saved) setConflict(null);
  }, [conflict, performDraftSave]);

  const createRevision = useCallback(
    async (message: string) => {
      if (!playbookId || !capabilities.can_edit) return null;
      setRevisionBusy("create");
      try {
        const draft = await saveDraftNow();
        if (!draft) return null;
        const response = await createPlaybookRevision(playbookId, {
          expected_version: draft.version,
          message: message.trim(),
        });
        queryClient.setQueryData(draftKey(playbookId), {
          success: true,
          draft: { ...draft, base_revision_id: response.revision.id },
        });
        await queryClient.invalidateQueries({ queryKey: revisionsKey(playbookId) });
        notify.success({ title: tr("Ревизия создана", "Revision created") });
        return response.revision;
      } catch (error) {
        notify.error({ title: tr("Не удалось создать ревизию", "Failed to create revision"), description: String(error) });
        return null;
      } finally {
        setRevisionBusy(null);
      }
    },
    [capabilities.can_edit, playbookId, queryClient, saveDraftNow, tr],
  );

  const publishRevision = useCallback(
    async (revisionId: number) => {
      if (!playbookId || !capabilities.can_publish) return;
      setRevisionBusy("publish");
      try {
        await publishPlaybookRevision(playbookId, revisionId);
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: revisionsKey(playbookId) }),
          queryClient.invalidateQueries({ queryKey: ["playbooks"] }),
        ]);
        notify.success({ title: tr("Ревизия опубликована", "Revision published") });
      } catch (error) {
        notify.error({ title: tr("Публикация не удалась", "Publish failed"), description: String(error) });
      } finally {
        setRevisionBusy(null);
      }
    },
    [capabilities.can_publish, playbookId, queryClient, tr],
  );

  const rollbackRevision = useCallback(
    async (revisionId: number) => {
      if (!playbookId || !capabilities.can_publish) return;
      setRevisionBusy("rollback");
      try {
        await rollbackPlaybookRevision(playbookId, revisionId);
        const latest = await getPlaybookDraft(playbookId);
        queryClient.setQueryData(draftKey(playbookId), latest);
        setEditor((current) => applyDraftToPlaybookEditor(current, latest.draft));
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: revisionsKey(playbookId) }),
          queryClient.invalidateQueries({ queryKey: ["playbooks"] }),
        ]);
        notify.success({ title: tr("Создана и опубликована rollback-ревизия", "Rollback revision published") });
      } catch (error) {
        notify.error({ title: tr("Rollback не удался", "Rollback failed"), description: String(error) });
      } finally {
        setRevisionBusy(null);
      }
    },
    [capabilities.can_publish, playbookId, queryClient, setEditor, tr],
  );

  const openRevision = useCallback(
    async (revisionId: number) => {
      if (!playbookId) return;
      setRevisionBusy("detail");
      try {
        const response = await getPlaybookRevision(playbookId, revisionId);
        setSelectedRevision(response.revision);
      } finally {
        setRevisionBusy(null);
      }
    },
    [playbookId],
  );

  const saveBinding = useCallback(
    async (payload: SavePlaybookBindingPayload, current?: PlaybookBindingProfile | null) => {
      if (!playbookId || !(capabilities.can_edit || capabilities.can_run)) return false;
      setBindingBusy(true);
      try {
        if (current) {
          await updatePlaybookBinding(playbookId, current.id, { ...payload, expected_version: current.version });
        } else {
          await createPlaybookBinding(playbookId, payload);
        }
        await queryClient.invalidateQueries({ queryKey: bindingsKey(playbookId) });
        notify.success({ title: tr("Профиль привязки сохранён", "Binding profile saved") });
        return true;
      } catch (error) {
        notify.error({ title: tr("Не удалось сохранить привязку", "Failed to save binding"), description: String(error) });
        return false;
      } finally {
        setBindingBusy(false);
      }
    },
    [capabilities.can_edit, capabilities.can_run, playbookId, queryClient, tr],
  );

  const removeBinding = useCallback(
    async (bindingId: number) => {
      if (!playbookId) return;
      setBindingBusy(true);
      try {
        await deletePlaybookBinding(playbookId, bindingId);
        await queryClient.invalidateQueries({ queryKey: bindingsKey(playbookId) });
      } finally {
        setBindingBusy(false);
      }
    },
    [playbookId, queryClient],
  );

  const saveShare = useCallback(
    async (payload: Parameters<typeof createPlaybookShare>[1]) => {
      if (!playbookId || !capabilities.can_share) return false;
      setShareBusy(true);
      try {
        await createPlaybookShare(playbookId, payload);
        await queryClient.invalidateQueries({ queryKey: sharesKey(playbookId) });
        notify.success({ title: tr("Доступ сохранён", "Access saved") });
        return true;
      } catch (error) {
        notify.error({ title: tr("Не удалось сохранить доступ", "Failed to save access"), description: String(error) });
        return false;
      } finally {
        setShareBusy(false);
      }
    },
    [capabilities.can_share, playbookId, queryClient, tr],
  );

  const removeShare = useCallback(
    async (shareId: number) => {
      if (!playbookId || !capabilities.can_share) return;
      setShareBusy(true);
      try {
        await deletePlaybookShare(playbookId, shareId);
        await queryClient.invalidateQueries({ queryKey: sharesKey(playbookId) });
      } finally {
        setShareBusy(false);
      }
    },
    [capabilities.can_share, playbookId, queryClient],
  );

  return {
    capabilities,
    capabilityReady,
    canEditContent,
    autosaveStatus,
    autosaveError,
    conflict,
    draft: draftQuery.data?.draft || null,
    hasUnrevisionedChanges,
    hasUnpublishedRevision,
    revisions: revisionsQuery.data?.revisions || [],
    publishedRevisionId: revisionsQuery.data?.published_revision_id || null,
    revisionsLoading: revisionsQuery.isPending,
    revisionBusy,
    selectedRevision,
    setSelectedRevision,
    bindings: bindingsQuery.data?.bindings || [],
    bindingsLoading: bindingsQuery.isPending,
    bindingsAccessible: bindingsQuery.isSuccess,
    bindingBusy,
    shares: sharesQuery.data?.shares || [],
    sharesAccessible: sharesQuery.isSuccess,
    shareBusy,
    saveDraftNow,
    retryDraftSave,
    acceptServerDraft,
    keepLocalDraft,
    createRevision,
    publishRevision,
    rollbackRevision,
    openRevision,
    saveBinding,
    removeBinding,
    saveShare,
    removeShare,
  };
}

export type PlaybookWorkspaceVersioningController = ReturnType<typeof usePlaybookWorkspaceVersioning>;
