import { useCallback, useMemo, useState, type ChangeEvent } from "react";

import {
  createServer,
  deleteServer,
  fetchServerDetails,
  testServer,
  updateServer,
  type FrontendServer,
} from "@/lib/api";
import { notify } from "@/lib/notify";

import { asPayload, initialForm } from "./serverForm";
import type { ServerForm } from "./types";
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
    const targetId = serverDeleteTarget.id;
    await deleteServer(targetId);
    if (editingServer?.id === targetId) {
      setDialogOpen(false);
      setEditingServer(null);
    }
    setServerDeleteTarget(null);
    onServerDeleted?.(targetId);
    await reload();
  }, [editingServer?.id, onServerDeleted, reload, serverDeleteTarget]);

  const testConnection = useCallback(async (server: FrontendServer) => {
    setTestingConnection(true);
    try {
      const result = await testServer(server.id, {});
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
  }, [reload, t, tr]);

  const testConnectionById = useCallback(async (serverId: number, name: string) => {
    setTestingConnection(true);
    try {
      const result = await testServer(serverId, {});
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
  }, [reload, t, tr]);

  const saveAndTestServer = useCallback(async () => {
    const serverName = form.name.trim() || editingServer?.name || t("srv.create_server");
    const savedId = await saveServer();
    if (!savedId) return;
    await testConnectionById(savedId, serverName);
  }, [editingServer?.name, form.name, saveServer, t, testConnectionById]);

  return {
    clearServerDeleteTarget,
    confirmDeleteServer,
    dialogOpen,
    editingServer,
    form,
    formValidation,
    handlePrivateKeyFile,
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
