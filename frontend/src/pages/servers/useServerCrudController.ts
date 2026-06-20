import { useCallback, useMemo, useState, type ChangeEvent } from "react";

import {
  createServer,
  deleteServer,
  fetchServerDetails,
  testServer,
  updateServer,
  type FrontendServer,
} from "@/lib/api";

import { asPayload, initialForm } from "./serverForm";
import type { ServerForm } from "./types";

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

  const sudoPasswordRequired = useMemo(
    () =>
      form.sudo_auth_mode === "stored_password" &&
      !form.sudo_password.trim() &&
      !(editingServer?.has_saved_sudo_password ?? false),
    [editingServer?.has_saved_sudo_password, form.sudo_auth_mode, form.sudo_password],
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
    setSaving(true);
    try {
      if (editingServer) await updateServer(editingServer.id, asPayload(form));
      else await createServer(asPayload(form));
      setDialogOpen(false);
      await reload();
    } finally {
      setSaving(false);
    }
  }, [editingServer, form, reload]);

  const handlePrivateKeyFile = useCallback(async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      setForm((state) => ({ ...state, ssh_private_key: text }));
    } catch (error) {
      console.error(error);
      alert(t("srv.private_key_read_error"));
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
    const result = await testServer(server.id, {});
    if (result.success) {
      alert(tr("srv.connection_success", { name: server.name }));
    } else {
      alert(tr("srv.connection_failed", { error: result.error || t("srv.unknown_error") }));
    }
    await reload();
  }, [reload, t, tr]);

  return {
    clearServerDeleteTarget,
    confirmDeleteServer,
    dialogOpen,
    editingServer,
    form,
    handlePrivateKeyFile,
    openCreate,
    openEdit,
    requestDeleteServer,
    saveServer,
    saving,
    serverDeleteTarget,
    setDialogOpen,
    setForm,
    sudoPasswordRequired,
    testConnection,
  };
}
