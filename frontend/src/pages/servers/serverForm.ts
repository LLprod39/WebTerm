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
    tags: "",
    notes: "",
    group_id: null,
    is_active: true,
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

export function asPayload(form: ServerForm) {
  const payload: Record<string, unknown> = {
    name: form.name,
    server_type: form.server_type,
    host: form.host,
    port: form.port,
    username: form.username,
    auth_method: form.auth_method,
    key_path: form.key_path,
    password: form.password,
    tags: form.tags,
    notes: form.notes,
    group_id: form.group_id,
    is_active: form.is_active,
    ai_read_only: form.ai_read_only,
  };
  const privateKey = form.ssh_private_key.trim();
  if (form.auth_method !== "password" && privateKey) {
    payload.ssh_private_key = privateKey;
  }
  return payload;
}
