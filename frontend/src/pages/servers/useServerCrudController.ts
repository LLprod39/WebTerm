import { useCallback, useMemo, useState, type ChangeEvent } from "react";

import {
  createServer,
  deleteServer,
  fetchServerDetails,
  testServer,
  updateServer,
  type FrontendServer,
  type TestServerResponse,
} from "@/lib/api";
import { localize } from "@/lib/i18n";
import { notify } from "@/lib/notify";
import { notifyWithUndo } from "@/lib/notify-undo";

import { asPayload, initialForm } from "./serverForm";
import type { ServerForm, SSHHostKeyEnrollmentTarget } from "./types";
import { validateServerForm } from "./serverValidation";

type Translate = (key: string) => string;
type TranslateWithVars = (key: string, vars?: Record<string, string | number>) => string;

interface UseServerCrudControllerParams {
  onServerDeleted?: (serverId: number) => void;
  reload: () => Promise<void>;
  t: Translate;
  tr: TranslateWithVars;
}

export function useServerCrudController({
  onServerDeleted,
  reload,
  t,
  tr,
}: UseServerCrudControllerParams) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingServer, setEditingServer] = useState<FrontendServer | null>(null);
  const [serverDeleteTarget, setServerDeleteTarget] = useState<FrontendServer | null>(null);
  const [form, setForm] = useState<ServerForm>(initialForm());
  const [saving, setSaving] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [hostKeyEnrollmentTarget, setHostKeyEnrollmentTarget] = useState<SSHHostKeyEnrollmentTarget | null>(null);

  const captureHostKeyConfirmation = useCallback((
    serverId: number,
    serverName: string,
    result: TestServerResponse,
  ) => {
    if (
      !result.host_key?.fingerprint_sha256
      || ![
        "host_key_confirmation_required",
        "host_key_rotation_confirmation_required",
        "host_key_fingerprint_mismatch",
      ].includes(result.code || "")
    ) {
      return false;
    }
    setHostKeyEnrollmentTarget({
      serverId,
      serverName,
      algorithm: result.host_key.algorithm || "SSH",
      fingerprintSha256: result.host_key.fingerprint_sha256,
      trustedFingerprints: result.trusted_fingerprints || [],
      isRotation: result.code === "host_key_rotation_confirmation_required" || Boolean(result.is_rotation),
    });
    return true;
  }, []);

  const formValidation = useMemo(
    () => validateServerForm(form, t, editingServer?.has_saved_sudo_password ?? false),
    [editingServer?.has_saved_sudo_password, form, t],
  );

  const openCreate = useCallback(() => {
    setEditingServer(null);
    setForm(initialForm());
    setDialogOpen(true);
  }, []);

  const openEdit = useCallback(async (server: FrontendServer) => {
    setEditingServer(server);
    const details = await fetchServerDetails(server.id);
    setForm({
      name: details.name,
      server_type: details.server_type,
      host: details.host,
      port: details.port,
      username: details.username,
      auth_method: details.auth_method,
      key_path: details.key_path || "",
      ssh_private_key: "",
      password: "",
      sudo_auth_mode: details.sudo_auth_mode || "none",
      sudo_password: "",
      tags: details.tags || "",
      notes: details.notes || "",
      group_id: details.group_id,
      is_active: details.is_active,
      ai_read_only: details.ai_read_only ?? false,
    });
    setDialogOpen(true);
  }, []);

  const requestDeleteServer = useCallback((server: FrontendServer) => {
    setServerDeleteTarget(server);
  }, []);

  const clearServerDeleteTarget = useCallback(() => {
    setServerDeleteTarget(null);
  }, []);

  const saveServer = useCallback(async () => {
    const validation = validateServerForm(form, t, editingServer?.has_saved_sudo_password ?? false);
    if (!validation.isValid) {
      notify.error({ title: t("srv.form_incomplete"), description: validation.summary });
      return null;
    }

    setSaving(true);
    try {
      let savedId = editingServer?.id ?? null;
      if (editingServer) await updateServer(editingServer.id, asPayload(form));
      else {
        const created = await createServer(asPayload(form));
        savedId = created.server_id;
      }
      notify.success({
        title: editingServer ? t("srv.server_updated") : t("srv.server_created"),
      });
      setDialogOpen(false);
      await reload();
      return savedId;
    } catch (error) {
      notify.error({
        title: t("srv.save_failed"),
        description: error instanceof Error ? error.message : t("srv.unknown_error"),
      });
      return null;
    } finally {
      setSaving(false);
    }
  }, [editingServer, form, reload, t]);

  const handlePrivateKeyFile = useCallback(async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      setForm((state) => ({ ...state, ssh_private_key: text }));
    } catch (error) {
      console.error(error);
      notify.error({ title: t("srv.private_key_read_error") });
    } finally {
      event.currentTarget.value = "";
    }
  }, [t]);

  const confirmDeleteServer = useCallback(async () => {
    if (!serverDeleteTarget?.id) return;
    const target = serverDeleteTarget;
    const targetId = target.id;
    // Close confirm dialog; hard delete is delayed 5s so the operator can Undo.
    setServerDeleteTarget(null);
    if (editingServer?.id === targetId) {
      setDialogOpen(false);
      setEditingServer(null);
    }

    const lang = document.documentElement.lang === "en" ? "en" : "ru";
    notifyWithUndo({
      lang,
      title: localize(lang, `Удаление «${target.name}»…`, `Deleting “${target.name}”…`),
      description: localize(lang, "Нажмите «Отменить», чтобы оставить сервер", "Click Undo to keep the server"),
      durationMs: 5000,
      onCommit: async () => {
        try {
          await deleteServer(targetId);
          onServerDeleted?.(targetId);
          await reload();
          notify.success({
            title: localize(lang, `Сервер «${target.name}» удалён`, `Server “${target.name}” deleted`),
          });
        } catch (error) {
          notify.error({
            title: t("srv.save_failed"),
            description: error instanceof Error ? error.message : t("srv.unknown_error"),
          });
        }
      },
      onUndo: () => {
        notify.info({
          title: localize(lang, `«${target.name}» сохранён`, `“${target.name}” kept`),
        });
      },
    });
  }, [editingServer?.id, onServerDeleted, reload, serverDeleteTarget, t]);

  const testConnection = useCallback(async (server: FrontendServer) => {
    setTestingConnection(true);
    try {
      const result = await testServer(server.id, {});
      if (captureHostKeyConfirmation(server.id, server.name, result)) return;
      if (result.success) {
        notify.success({ title: tr("srv.connection_success", { name: server.name }) });
      } else {
        notify.error({
          title: t("srv.connection_failed_title"),
          description: tr("srv.connection_failed", { error: result.error || t("srv.unknown_error") }),
        });
      }
      await reload();
    } catch (error) {
      notify.error({
        title: t("srv.connection_failed_title"),
        description: error instanceof Error ? error.message : t("srv.unknown_error"),
      });
    } finally {
      setTestingConnection(false);
    }
  }, [captureHostKeyConfirmation, reload, t, tr]);

  const testConnectionById = useCallback(async (serverId: number, name: string) => {
    setTestingConnection(true);
    try {
      const result = await testServer(serverId, {});
      if (captureHostKeyConfirmation(serverId, name, result)) return;
      if (result.success) {
        notify.success({ title: tr("srv.connection_success", { name }) });
      } else {
        notify.error({
          title: t("srv.connection_failed_title"),
          description: tr("srv.connection_failed", { error: result.error || t("srv.unknown_error") }),
        });
      }
      await reload();
    } catch (error) {
      notify.error({
        title: t("srv.connection_failed_title"),
        description: error instanceof Error ? error.message : t("srv.unknown_error"),
      });
    } finally {
      setTestingConnection(false);
    }
  }, [captureHostKeyConfirmation, reload, t, tr]);

  const closeHostKeyEnrollment = useCallback(() => {
    if (!testingConnection) setHostKeyEnrollmentTarget(null);
  }, [testingConnection]);

  const confirmHostKeyEnrollment = useCallback(async (fingerprint: string) => {
    const target = hostKeyEnrollmentTarget;
    if (!target || fingerprint !== target.fingerprintSha256) return;
    setTestingConnection(true);
    try {
      const result = await testServer(target.serverId, {
        enroll_host_key: true,
        expected_host_key_fingerprint: fingerprint,
        replace_host_key: target.isRotation,
      });
      if (captureHostKeyConfirmation(target.serverId, target.serverName, result)) return;
      if (result.success) {
        setHostKeyEnrollmentTarget(null);
        notify.success({ title: tr("srv.connection_success", { name: target.serverName }) });
        await reload();
      } else {
        notify.error({
          title: t("srv.connection_failed_title"),
          description: tr("srv.connection_failed", { error: result.error || t("srv.unknown_error") }),
        });
      }
    } catch (error) {
      notify.error({
        title: t("srv.connection_failed_title"),
        description: error instanceof Error ? error.message : t("srv.unknown_error"),
      });
    } finally {
      setTestingConnection(false);
    }
  }, [captureHostKeyConfirmation, hostKeyEnrollmentTarget, reload, t, tr]);

  const saveAndTestServer = useCallback(async () => {
    const serverName = form.name.trim() || editingServer?.name || t("srv.create_server");
    const savedId = await saveServer();
    if (!savedId) return;
    await testConnectionById(savedId, serverName);
  }, [editingServer?.name, form.name, saveServer, t, testConnectionById]);

  return {
    clearServerDeleteTarget,
    closeHostKeyEnrollment,
    confirmDeleteServer,
    confirmHostKeyEnrollment,
    dialogOpen,
    editingServer,
    form,
    formValidation,
    handlePrivateKeyFile,
    hostKeyEnrollmentTarget,
    openCreate,
    openEdit,
    requestDeleteServer,
    saveServer,
    saveAndTestServer,
    saving,
    serverDeleteTarget,
    setDialogOpen,
    setForm,
    testConnection,
    testingConnection,
  };
}
