import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  useIsMutating,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import type { ServerDetail } from "@/api/infrastructure";
import {
  serverWorkspaceApi,
  type Share,
  type ShareInput,
} from "@/api/server-workspace";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
  EmptyState,
  ErrorState,
  Feedback,
  Field,
  Panel,
  Skeleton,
  StatusBadge,
} from "@/components/ui";
import { useUnsavedEditsBlocker } from "@/features/automation/unsaved";
import { formatDate } from "@/lib/utils";

type Permissions = Omit<ShareInput, "user" | "expires_at">;
const capabilities: [keyof Permissions, string][] = [
  ["can_connect_terminal", "SSH-терминал"],
  ["can_execute_command", "Выполнение команд"],
  ["can_read_files", "Чтение файлов"],
  ["can_write_files", "Изменение файлов"],
  ["share_context", "Контекст сервера для AI"],
];
const defaults: Permissions = {
  can_connect_terminal: true,
  can_execute_command: false,
  can_read_files: false,
  can_write_files: false,
  share_context: false,
};
function accessError(error: Error | null) {
  if (!error) return null;
  const messages: Record<string, string> = {
    "User not found":
      "Пользователь не найден. Проверьте точный логин или email.",
    "Cannot share server with yourself": "Вы уже владелец этого сервера.",
    "active target user not found":
      "Активный пользователь не найден. Проверьте логин или email.",
    "target user already owns this server":
      "Этот пользователь уже владеет сервером.",
    "target user must be an owner, admin, or operator in the server project":
      "Пользователь должен быть владельцем, администратором или оператором проекта сервера.",
    "email matches multiple users; use the exact username":
      "Этот email указан у нескольких пользователей. Введите точный логин.",
    "expires_at must be in the future":
      "Выберите дату окончания доступа в будущем.",
  };
  return messages[error.message] ? new Error(messages[error.message]) : error;
}
function localDate(iso: string | null) {
  if (!iso) return "";
  const date = new Date(iso);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
function ShareEditor({
  server,
  item,
  shares,
  onClose,
  onSaved,
}: {
  server: ServerDetail;
  item: Share | null;
  shares: Share[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [target, setTarget] = useState(item?.username ?? "");
  const [expires, setExpires] = useState(localDate(item?.expires_at ?? null));
  const [permissions, setPermissions] = useState<Permissions>(() =>
    item
      ? (Object.fromEntries(
          capabilities.map(([key]) => [key, item[key]]),
        ) as Permissions)
      : { ...defaults },
  );
  const [initial] = useState(() =>
    JSON.stringify({ target, expires, permissions }),
  );
  const [discard, setDiscard] = useState(false);
  const [validation, setValidation] = useState("");
  const dirty = initial !== JSON.stringify({ target, expires, permissions });
  const share = useMutation({
    mutationKey: ["server-workspace", server.id],
    mutationFn: (body: ShareInput) => serverWorkspaceApi.share(server.id, body),
    onSuccess: onSaved,
  });
  const blocker = useUnsavedEditsBlocker(dirty || share.isPending);
  const duplicate =
    !item &&
    shares.some((s) =>
      [s.username, s.email, String(s.user_id)].some(
        (value) => value && value.toLowerCase() === target.trim().toLowerCase(),
      ),
    );
  function close() {
    if (share.isPending) return;
    if (dirty) setDiscard(true);
    else onClose();
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (share.isPending || !target.trim() || duplicate || (item && !dirty))
      return;
    if (
      expires &&
      (!Number.isFinite(new Date(expires).getTime()) ||
        new Date(expires).getTime() <= Date.now())
    ) {
      setValidation("Выберите дату окончания доступа в будущем.");
      return;
    }
    setValidation("");
    share.mutate({
      user: item ? String(item.user_id) : target.trim(),
      ...permissions,
      expires_at: expires ? new Date(expires).toISOString() : null,
    });
  }
  return (
    <>
      <Drawer
        open
        onOpenChange={(open) => !open && close()}
        closeDisabled={share.isPending}
        title={item ? `Доступ: ${item.username}` : "Предоставить доступ"}
        description={server.name}
      >
        <form onSubmit={submit}>
          <fieldset
            className="stack"
            disabled={share.isPending}
            style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}
          >
            <Field label="Логин или email пользователя" htmlFor="share-target">
              <input
                id="share-target"
                required
                autoFocus
                readOnly={!!item}
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              />
            </Field>
            {duplicate && (
              <p role="alert" className="text-sm text-danger">
                Доступ уже предоставлен. Закройте форму и нажмите «Изменить»
                рядом с пользователем.
              </p>
            )}
            <div className="stack">
              <strong className="text-sm">Разрешения</strong>
              {capabilities.map(([key, label]) => (
                <label key={key} className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={permissions[key]}
                    disabled={
                      key === "can_read_files" && permissions.can_write_files
                    }
                    onChange={(e) =>
                      setPermissions((p) => ({
                        ...p,
                        [key]: e.target.checked,
                        ...(key === "can_write_files" && e.target.checked
                          ? { can_read_files: true }
                          : {}),
                      }))
                    }
                  />
                  {label}
                </label>
              ))}
              {permissions.can_write_files && (
                <p className="muted text-sm">
                  Изменение файлов включает чтение, загрузку и удаление.
                </p>
              )}
            </div>
            <details open={expires ? true : undefined}>
              <summary>
                Срок доступа{!expires ? " · без ограничения" : ""}
              </summary>
              <div className="stack" style={{ paddingTop: 12 }}>
                <Field
                  label="Действует до"
                  htmlFor="share-expiry"
                  description="Оставьте пустым для бессрочного доступа."
                >
                  <input
                    type="datetime-local"
                    id="share-expiry"
                    value={expires}
                    onChange={(e) => {
                      setExpires(e.target.value);
                      setValidation("");
                    }}
                  />
                </Field>
                {expires && (
                  <Button
                    size="sm"
                    onClick={() => {
                      setExpires("");
                      setValidation("");
                    }}
                  >
                    Убрать срок
                  </Button>
                )}
              </div>
            </details>
            <Feedback
              error={
                validation ? new Error(validation) : accessError(share.error)
              }
            />
            <div className="row">
              <Button
                type="submit"
                variant="primary"
                loading={share.isPending}
                disabled={!target.trim() || duplicate || (!!item && !dirty)}
              >
                {item ? "Сохранить доступ" : "Предоставить доступ"}
              </Button>
              <Button onClick={close}>Отмена</Button>
            </div>
          </fieldset>
        </form>
      </Drawer>
      <ConfirmDialog
        open={discard || blocker.state === "blocked"}
        onOpenChange={(open) => {
          if (!open && !share.isPending) {
            setDiscard(false);
            if (blocker.state === "blocked") blocker.reset();
          }
        }}
        title={
          share.isPending ? "Доступ сохраняется" : "Закрыть без сохранения?"
        }
        description={
          share.isPending
            ? "Дождитесь завершения запроса."
            : "Изменения разрешений не будут сохранены."
        }
        confirmLabel="Не сохранять"
        pending={share.isPending}
        onConfirm={() => {
          if (share.isPending) return;
          if (blocker.state === "blocked") blocker.proceed();
          else onClose();
        }}
      />
    </>
  );
}
export function ServerAccess({ server }: { server: ServerDetail }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [editor, setEditor] = useState<Share | "new" | null>(null);
  const [removing, setRemoving] = useState<Share | null>(null);
  const [transfer, setTransfer] = useState(false);
  const [newOwner, setNewOwner] = useState("");
  const [notice, setNotice] = useState("");
  const pending =
    useIsMutating({ mutationKey: ["server-workspace", server.id] }) > 0;
  const query = useQuery({
    queryKey: ["server-shares", server.id],
    queryFn: ({ signal }) => serverWorkspaceApi.shares(server.id, signal),
    enabled: server.capabilities.admin_share,
  });
  const invalidate = () =>
    void client.invalidateQueries({ queryKey: ["server-shares", server.id] });
  const revoke = useMutation({
    mutationKey: ["server-workspace", server.id],
    mutationFn: () => serverWorkspaceApi.revoke(server.id, removing!.id),
    onSuccess: () => {
      setRemoving(null);
      setNotice("Доступ отозван.");
      invalidate();
    },
  });
  const owner = useMutation({
    mutationKey: ["server-workspace", server.id],
    mutationFn: () => serverWorkspaceApi.transfer(server.id, newOwner.trim()),
    onSuccess: () => {
      setTransfer(false);
      void client.invalidateQueries({ queryKey: ["server", server.id] });
      void client.invalidateQueries({ queryKey: ["servers"] });
      navigate("/infrastructure/servers", { replace: true });
    },
  });
  if (!server.capabilities.admin_share)
    return (
      <EmptyState
        title="Доступом управляет владелец"
        description="Вы можете использовать предоставленные вам возможности этого сервера."
      />
    );
  return (
    <div className="stack">
      <Panel
        title="Кому доступен сервер"
        actions={
          <Button
            variant="primary"
            disabled={pending || !query.data}
            onClick={() => {
              setNotice("");
              setEditor("new");
            }}
          >
            <Plus size={14} />
            Предоставить доступ
          </Button>
        }
      >
        {query.isPending ? (
          <Skeleton />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : (
          <DataTable
            rows={query.data?.shares ?? []}
            rowKey={(s) => s.id}
            hideSinglePagePagination
            searchValue={(s) => `${s.username} ${s.email}`}
            searchPlaceholder="Найти пользователя…"
            emptyTitle="Персональный доступ не предоставлен"
            emptyDescription="Добавьте пользователя и выберите его разрешения."
            columns={[
              {
                key: "user",
                label: "Пользователь",
                sortValue: (s) => s.username,
                render: (s) => (
                  <div>
                    <strong>{s.username}</strong>
                    {s.email && <small>{s.email}</small>}
                  </div>
                ),
              },
              {
                key: "rights",
                label: "Разрешения",
                render: (s) => (
                  <span className="text-sm muted">
                    {capabilities
                      .filter(([key]) => s[key])
                      .map(([, label]) => label)
                      .join(", ") || "Только параметры подключения"}
                  </span>
                ),
              },
              {
                key: "expiry",
                label: "Действует до",
                sortValue: (s) => s.expires_at || "9999",
                render: (s) => (
                  <div>
                    {s.expires_at ? formatDate(s.expires_at) : "Без срока"}
                    {!s.is_active && (
                      <StatusBadge status="expired">Истёк</StatusBadge>
                    )}
                  </div>
                ),
              },
              {
                key: "actions",
                label: "",
                render: (s) => (
                  <div className="row">
                    <Button
                      size="icon"
                      variant="ghost"
                      disabled={pending}
                      aria-label={`Изменить доступ ${s.username}`}
                      onClick={() => {
                        setNotice("");
                        setEditor(s);
                      }}
                    >
                      <Pencil size={14} />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      disabled={pending}
                      aria-label={`Отозвать доступ ${s.username}`}
                      onClick={() => {
                        revoke.reset();
                        setRemoving(s);
                      }}
                    >
                      <Trash2 size={14} />
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        )}
      </Panel>
      <Feedback success={notice || undefined} />
      <details className="panel">
        <summary className="section-body">Передача владения сервером</summary>
        <form
          className="section-body"
          onSubmit={(event) => {
            event.preventDefault();
            if (newOwner.trim() && !pending) {
              owner.reset();
              setTransfer(true);
            }
          }}
        >
          <fieldset
            className="stack"
            disabled={pending}
            style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}
          >
            <p className="muted text-sm">
              Новый владелец получит полный контроль. Текущие подключения
              закроются, ваши права изменятся. Пользователь должен иметь право
              управления в проекте сервера.
            </p>
            <Field
              label="Логин или email нового владельца"
              htmlFor="server-new-owner"
            >
              <input
                id="server-new-owner"
                required
                value={newOwner}
                onChange={(e) => setNewOwner(e.target.value)}
              />
            </Field>
            <Button type="submit" variant="danger" disabled={!newOwner.trim()}>
              Передать владение
            </Button>
          </fieldset>
        </form>
      </details>
      {editor !== null && (
        <ShareEditor
          key={editor === "new" ? "new" : editor.id}
          server={server}
          item={editor === "new" ? null : editor}
          shares={query.data?.shares ?? []}
          onClose={() => setEditor(null)}
          onSaved={() => {
            setEditor(null);
            setNotice("Доступ сохранён.");
            invalidate();
          }}
        />
      )}
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(open) => {
          if (!open && !revoke.isPending) setRemoving(null);
        }}
        title="Отозвать доступ?"
        description={
          <div className="stack">
            <p>
              Пользователь «{removing?.username}» потеряет персональный доступ к
              серверу.
            </p>
            <Feedback error={accessError(revoke.error)} />
          </div>
        }
        confirmLabel="Отозвать доступ"
        onConfirm={() => !revoke.isPending && revoke.mutate()}
        pending={revoke.isPending}
      />
      <ConfirmDialog
        open={transfer}
        onOpenChange={(open) => {
          if (!owner.isPending) setTransfer(open);
        }}
        title="Передать владение сервером?"
        description={
          <div className="stack">
            <p>
              Новый владелец: {newOwner.trim()}. Подключения будут закрыты, ваши
              текущие права изменятся.
            </p>
            <Feedback error={accessError(owner.error)} />
          </div>
        }
        typedText={server.name}
        confirmLabel="Передать владение"
        onConfirm={() => !owner.isPending && owner.mutate()}
        pending={owner.isPending}
      />
    </div>
  );
}
