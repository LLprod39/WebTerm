import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  infrastructureApi,
  type ServerDetail,
  type ServerGroup,
  type ServerInput,
} from "@/api/infrastructure";
import {
  Button,
  ConfirmDialog,
  Drawer,
  Feedback,
  Field,
} from "@/components/ui";
interface Values {
  name: string;
  host: string;
  port: string;
  username: string;
  auth_method: string;
  password: string;
  ssh_private_key: string;
  group_id: string;
  tags: string;
  notes: string;
  corporate_context: string;
  sudo_auth_mode: string;
  sudo_password: string;
  network: string;
}
export function ServerForm({
  open,
  onOpenChange,
  server,
  groups = [],
  defaultGroupId = "",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  server?: ServerDetail;
  groups?: ServerGroup[];
  defaultGroupId?: string;
}) {
  const [formState, setFormState] = useState({ dirty: false, pending: false });
  const [discard, setDiscard] = useState(false);
  const close = () => {
    if (formState.pending) return;
    if (formState.dirty) setDiscard(true);
    else onOpenChange(false);
  };
  const done = () => {
    setFormState({ dirty: false, pending: false });
    setDiscard(false);
    onOpenChange(false);
  };
  return (
    <>
      <Drawer
        open={open}
        onOpenChange={(nextOpen) => (nextOpen ? onOpenChange(true) : close())}
        closeDisabled={formState.pending}
        title={server ? "Настроить сервер" : "Добавить сервер"}
        description="Параметры SSH-подключения и контекст для команды."
      >
        <ServerFormBody
          key={server?.id ?? "new"}
          server={server}
          groups={groups}
          defaultGroupId={defaultGroupId}
          onDone={done}
          onCancel={close}
          onStateChange={setFormState}
        />
      </Drawer>
      <ConfirmDialog
        open={discard}
        onOpenChange={setDiscard}
        title="Закрыть без сохранения?"
        description="Введённые параметры сервера будут потеряны."
        confirmLabel="Не сохранять"
        onConfirm={done}
      />
    </>
  );
}
function ServerFormBody({
  server,
  groups,
  defaultGroupId,
  onDone,
  onCancel,
  onStateChange,
}: {
  server?: ServerDetail;
  groups: ServerGroup[];
  defaultGroupId: string;
  onDone: () => void;
  onCancel: () => void;
  onStateChange: (state: { dirty: boolean; pending: boolean }) => void;
}) {
  const client = useQueryClient();
  const [form, setForm] = useState<Values>({
    name: server?.name ?? "",
    host: server?.host ?? "",
    port: String(server?.port ?? 22),
    username: server?.username ?? "",
    auth_method: server?.auth_method ?? "password",
    password: "",
    ssh_private_key: "",
    group_id: server?.group_id?.toString() ?? defaultGroupId,
    tags: server?.tags ?? "",
    notes: server?.notes ?? "",
    corporate_context: server?.corporate_context ?? "",
    sudo_auth_mode: server?.sudo_auth_mode ?? "none",
    sudo_password: "",
    network: JSON.stringify(server?.network_config ?? {}, null, 2),
  });
  const [validation, setValidation] = useState("");
  const [initialForm] = useState(form);
  const dirty = JSON.stringify(form) !== JSON.stringify(initialForm);
  const set = (key: keyof Values, value: string) =>
    setForm((f) => ({ ...f, [key]: value }));
  const mutation = useMutation({
    mutationFn: (body: ServerInput) =>
      server
        ? infrastructureApi.update(server.id, body)
        : infrastructureApi.create(body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["servers"] });
      void client.invalidateQueries({ queryKey: ["server"] });
      void client.invalidateQueries({ queryKey: ["monitoring"] });
      onDone();
    },
  });
  useEffect(() => {
    onStateChange({ dirty, pending: mutation.isPending });
  }, [dirty, mutation.isPending, onStateChange]);
  function submit(e: FormEvent) {
    e.preventDefault();
    if (mutation.isPending) return;
    setValidation("");
    let network: Record<string, unknown>;
    try {
      network = JSON.parse(form.network) as Record<string, unknown>;
      if (!network || typeof network !== "object" || Array.isArray(network))
        throw Error();
    } catch {
      setValidation("Настройки сети должны быть JSON-объектом.");
      return;
    }
    const port = Number(form.port);
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      setValidation("Укажите порт от 1 до 65535.");
      return;
    }
    if (!form.name.trim() || !form.host.trim() || !form.username.trim()) {
      setValidation("Укажите название, адрес и пользователя.");
      return;
    }
    if (
      form.sudo_auth_mode === "stored_password" &&
      !form.sudo_password &&
      !server?.has_saved_sudo_password
    ) {
      setValidation("Укажите пароль sudo.");
      return;
    }
    const body: ServerInput = {
      name: form.name.trim(),
      host: form.host.trim(),
      port,
      username: form.username.trim(),
      auth_method: form.auth_method,
      group_id: form.group_id ? Number(form.group_id) : null,
      tags: form.tags,
      notes: form.notes,
      corporate_context: form.corporate_context,
      sudo_auth_mode: form.sudo_auth_mode,
      network_config: network,
    };
    if (form.auth_method !== "key" && form.password)
      body.password = form.password;
    if (form.auth_method !== "password" && form.ssh_private_key)
      body.ssh_private_key = form.ssh_private_key;
    if (form.sudo_auth_mode === "stored_password" && form.sudo_password)
      body.sudo_password = form.sudo_password;
    mutation.mutate(body);
  }
  return (
    <form onSubmit={submit}>
      <fieldset
        className="stack"
        disabled={mutation.isPending}
        style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
      >
        <Field label="Название" htmlFor="server-name">
          <input
            id="server-name"
            required
            autoFocus
            value={form.name}
            onChange={(e) => set("name", e.target.value)}
            placeholder="Например, Production API"
          />
        </Field>
        <div className="form-grid">
          <Field label="Адрес сервера" htmlFor="server-host">
            <input
              id="server-host"
              required
              value={form.host}
              onChange={(e) => set("host", e.target.value)}
              placeholder="IP или hostname"
            />
          </Field>
          <Field label="SSH-порт" htmlFor="server-port">
            <input
              id="server-port"
              type="number"
              required
              min="1"
              max="65535"
              value={form.port}
              onChange={(e) => set("port", e.target.value)}
            />
          </Field>
        </div>
        {server &&
          (form.host.trim() !== server.host ||
            Number(form.port) !== server.port) && (
            <p className="notice">
              После смены адреса или порта потребуется заново подтвердить
              SSH-ключ сервера.
            </p>
          )}
        <Field label="Пользователь SSH" htmlFor="server-user">
          <input
            id="server-user"
            required
            autoComplete="off"
            value={form.username}
            onChange={(e) => set("username", e.target.value)}
            placeholder="deploy"
          />
        </Field>
        <Field label="Аутентификация" htmlFor="server-auth">
          <select
            id="server-auth"
            value={form.auth_method}
            onChange={(e) => set("auth_method", e.target.value)}
          >
            <option value="password">Пароль</option>
            <option value="key">SSH-ключ</option>
            <option value="key_password">SSH-ключ с парольной фразой</option>
          </select>
        </Field>
        {form.auth_method !== "key" && (
          <Field
            label={
              form.auth_method === "key_password"
                ? "Парольная фраза ключа"
                : "Пароль SSH"
            }
            description={
              server?.has_saved_password
                ? "Пароль сохранён. Оставьте пустым, чтобы сохранить его."
                : "Можно оставить пустым и ввести при подключении."
            }
            htmlFor="server-password"
          >
            <input
              id="server-password"
              type="password"
              autoComplete="new-password"
              value={form.password}
              onChange={(e) => set("password", e.target.value)}
            />
          </Field>
        )}
        {form.auth_method !== "password" && (
          <Field
            label="Приватный SSH-ключ"
            htmlFor="server-key"
            description={
              server?.key_path
                ? "Ключ уже настроен. Заполните для замены."
                : "Вставьте ключ в формате OpenSSH или PEM."
            }
          >
            <textarea
              id="server-key"
              className="mono"
              value={form.ssh_private_key}
              onChange={(e) => set("ssh_private_key", e.target.value)}
              autoComplete="off"
            />
          </Field>
        )}
        <Field label="Группа" htmlFor="server-group">
          <select
            id="server-group"
            value={form.group_id}
            onChange={(e) => set("group_id", e.target.value)}
          >
            <option value="">Без группы</option>
            {groups
              .filter(
                (g) => g.id != null && (g.role || g.id === server?.group_id),
              )
              .map((g) => (
                <option value={g.id!} key={g.id}>
                  {g.name}
                </option>
              ))}
          </select>
        </Field>
        <details>
          <summary className="muted">
            Контекст и дополнительные параметры
          </summary>
          <div className="stack" style={{ marginTop: 16 }}>
            <Field label="Теги" htmlFor="server-tags">
              <input
                id="server-tags"
                value={form.tags}
                onChange={(e) => set("tags", e.target.value)}
              />
            </Field>
            <Field label="Заметки" htmlFor="server-notes">
              <textarea
                id="server-notes"
                value={form.notes}
                onChange={(e) => set("notes", e.target.value)}
              />
            </Field>
            <Field label="Контекст для команды и AI" htmlFor="server-context">
              <textarea
                id="server-context"
                value={form.corporate_context}
                onChange={(e) => set("corporate_context", e.target.value)}
              />
            </Field>
            <Field label="Повышение привилегий" htmlFor="server-sudo">
              <select
                id="server-sudo"
                value={form.sudo_auth_mode}
                onChange={(e) => set("sudo_auth_mode", e.target.value)}
              >
                <option value="none">Без sudo</option>
                <option value="nopasswd">sudo без пароля</option>
                <option value="stored_password">Сохранённый пароль sudo</option>
              </select>
            </Field>
            {form.sudo_auth_mode === "stored_password" && (
              <Field label="Пароль sudo" htmlFor="server-sudo-pass">
                <input
                  id="server-sudo-pass"
                  type="password"
                  autoComplete="new-password"
                  value={form.sudo_password}
                  onChange={(e) => set("sudo_password", e.target.value)}
                />
              </Field>
            )}
            <Field
              label="Конфигурация сети"
              htmlFor="server-network"
              description="Параметры proxy и jump host в формате JSON."
            >
              <textarea
                id="server-network"
                className="mono"
                value={form.network}
                onChange={(e) => set("network", e.target.value)}
              />
            </Field>
          </div>
        </details>
        <Feedback error={validation ? new Error(validation) : mutation.error} />
        <div className="form-actions">
          <Button onClick={onCancel} disabled={mutation.isPending}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" loading={mutation.isPending}>
            {server ? "Сохранить изменения" : "Добавить сервер"}
          </Button>
        </div>
      </fieldset>
    </form>
  );
}
