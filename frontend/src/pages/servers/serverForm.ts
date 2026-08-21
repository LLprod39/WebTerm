import type { ServerForm, ServerGroupForm } from "./types";

export function initialForm(): ServerForm {
  return {
    name: "",
    server_type: "ssh",
    host: "",
    port: 22,
    username: "root",
    auth_method: "password",
    key_path: "",
    ssh_private_key: "",
    password: "",
    sudo_auth_mode: "none",
    sudo_password: "",
    tags: "",
    notes: "",
    group_id: null,
    is_active: true,
    // Release default: authorized automation can work immediately. Users may
    // still opt a sensitive server into the per-server read-only boundary.
    ai_read_only: false,
  };
}

export function initialGroupForm(): ServerGroupForm {
  return {
    name: "",
    description: "",
    color: "#3b82f6",
  };
}

export function enforcePilotServerAccess(form: ServerForm): ServerForm {
  return {
    ...form,
    ai_read_only: true,
    sudo_auth_mode: "none",
    sudo_password: "",
  };
}

export function asPayload(form: ServerForm, canConfigureElevatedAccess = false) {
  const effectiveForm = canConfigureElevatedAccess ? form : enforcePilotServerAccess(form);
  const payload: Record<string, unknown> = {
    name: effectiveForm.name,
    server_type: effectiveForm.server_type,
    host: effectiveForm.host,
    port: effectiveForm.port,
    username: effectiveForm.username,
    auth_method: effectiveForm.auth_method,
    key_path: effectiveForm.key_path,
    password: effectiveForm.password,
    sudo_auth_mode: effectiveForm.sudo_auth_mode,
    sudo_password: effectiveForm.sudo_password,
    tags: effectiveForm.tags,
    notes: effectiveForm.notes,
    group_id: effectiveForm.group_id,
    is_active: effectiveForm.is_active,
    ai_read_only: effectiveForm.ai_read_only,
  };
  const privateKey = effectiveForm.ssh_private_key.trim();
  if (effectiveForm.auth_method !== "password" && privateKey) {
    payload.ssh_private_key = privateKey;
  }
  return payload;
}
