import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2, UserPlus } from "lucide-react";
import { serverGroupsApi, type GroupMember } from "@/api/server-groups";
import {
  Button,
  ConfirmDialog,
  DataTable,
  ErrorState,
  Feedback,
  Field,
  LoadingState,
} from "@/components/ui";

const roles: Record<string, string> = {
  owner: "Владелец",
  admin: "Администратор",
  member: "Участник",
  viewer: "Наблюдатель",
};
export function GroupMembers({ groupId }: { groupId: number }) {
  const client = useQueryClient();
  const [identity, setIdentity] = useState("");
  const [role, setRole] = useState<"admin" | "member" | "viewer">("member");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<GroupMember | null>(null);
  const [confirmRole, setConfirmRole] = useState(false);
  const [removing, setRemoving] = useState<GroupMember | null>(null);
  const query = useQuery({
    queryKey: ["group-members", groupId],
    queryFn: ({ signal }) => serverGroupsApi.members(groupId, signal),
  });
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["group-members", groupId] });
    void client.invalidateQueries({ queryKey: ["servers"] });
  };
  const add = useMutation({
    mutationKey: ["server-group", groupId],
    mutationFn: () => serverGroupsApi.addMember(groupId, identity.trim(), role),
    onSuccess: () => {
      refresh();
      setIdentity("");
      setEditing(null);
      setFormOpen(false);
      setConfirmRole(false);
    },
  });
  const remove = useMutation({
    mutationKey: ["server-group", groupId],
    mutationFn: () => serverGroupsApi.removeMember(groupId, removing!.user_id),
    onSuccess: () => {
      refresh();
      setRemoving(null);
    },
  });
  if (query.isPending) return <LoadingState />;
  if (query.error)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  const owner = query.data!.owner;
  const normalized = identity.trim().toLowerCase();
  const ownerIdentity =
    normalized === owner.username.toLowerCase() ||
    (!!owner.email && normalized === owner.email.toLowerCase());
  const duplicate =
    !editing &&
    query.data!.members.some(
      (member) =>
        member.user_id !== owner.user_id &&
        (member.username.toLowerCase() === normalized ||
          (!!member.email && member.email.toLowerCase() === normalized)),
    );
  const pending = add.isPending || remove.isPending;
  const addError =
    add.error?.message === "User not found"
      ? new Error("Пользователь не найден. Проверьте точный логин или email.")
      : add.error;
  const unchanged = !!editing && editing.role === role;
  function openForm(member: GroupMember | null) {
    setEditing(member);
    setIdentity(member?.username ?? "");
    setRole(
      member?.role === "admin" || member?.role === "viewer"
        ? member.role
        : "member",
    );
    setFormOpen(true);
    add.reset();
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (ownerIdentity || duplicate || unchanged || !identity.trim() || pending)
      return;
    if (editing || role === "admin") setConfirmRole(true);
    else add.mutate();
  }
  return (
    <div className="stack">
      <div className="notice">
        <strong>Владелец группы: {owner.username}</strong>
        <span>{owner.email}</span>
      </div>
      <DataTable
        rows={query.data!.members.filter(
          (member) => member.user_id !== owner.user_id,
        )}
        rowKey={(member) => member.user_id}
        searchValue={(member) => `${member.username} ${member.email}`}
        searchPlaceholder="Найти участника…"
        hideSinglePagePagination
        toolbar={
          <Button
            variant="primary"
            disabled={pending}
            onClick={() => openForm(null)}
          >
            <UserPlus size={15} />
            Добавить участника
          </Button>
        }
        emptyTitle="Пока только владелец"
        emptyDescription="Добавьте коллегу по логину или адресу электронной почты."
        columns={[
          {
            key: "name",
            label: "Пользователь",
            sortValue: (member) => member.username,
            render: (member) => (
              <div className="table-name">
                <div>
                  {member.username}
                  <small>{member.email}</small>
                </div>
              </div>
            ),
          },
          {
            key: "role",
            label: "Роль",
            sortValue: (member) => roles[member.role] ?? member.role,
            render: (member) => roles[member.role] ?? member.role,
          },
          {
            key: "actions",
            label: "",
            render: (member) => (
              <div className="table-actions">
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label={`Изменить роль ${member.username}`}
                  title={`Изменить роль ${member.username}`}
                  disabled={pending}
                  onClick={() => openForm(member)}
                >
                  <Pencil size={14} />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label={`Отозвать доступ ${member.username}`}
                  title={`Отозвать доступ ${member.username}`}
                  disabled={pending}
                  onClick={() => {
                    remove.reset();
                    setRemoving(member);
                  }}
                >
                  <Trash2 size={14} />
                </Button>
              </div>
            ),
          },
        ]}
      />
      <Feedback
        success={
          add.isSuccess
            ? "Доступ сохранён."
            : remove.isSuccess
              ? "Доступ отозван."
              : undefined
        }
      />
      {formOpen && (
        <form onSubmit={submit}>
          <fieldset
            className="stack"
            disabled={pending}
            style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
          >
            <h3>
              {editing ? `Изменить роль ${editing.username}` : "Новый участник"}
            </h3>
            <Field
              label="Точный логин или email"
              htmlFor="group-member-identity"
              error={
                ownerIdentity
                  ? "Роль владельца не меняется через список участников."
                  : duplicate
                    ? "Участник уже добавлен. Измените его роль в списке выше."
                    : undefined
              }
            >
              <input
                id="group-member-identity"
                required
                readOnly={!!editing}
                value={identity}
                autoComplete="off"
                onChange={(event) => {
                  setIdentity(event.target.value);
                  add.reset();
                }}
              />
            </Field>
            <Field label="Роль" htmlFor="group-member-role">
              <select
                id="group-member-role"
                value={role}
                onChange={(event) => setRole(event.target.value as typeof role)}
              >
                <option value="viewer">Наблюдатель</option>
                <option value="member">Участник</option>
                <option value="admin">Администратор</option>
              </select>
            </Field>
            {role === "admin" && (
              <p className="muted text-sm">
                Администратор управляет участниками, правилами и массовыми
                изменениями группы.
              </p>
            )}
            {!confirmRole && <Feedback error={addError} />}
            <div className="row">
              <Button
                type="submit"
                variant="primary"
                loading={add.isPending}
                disabled={
                  ownerIdentity || duplicate || unchanged || !identity.trim()
                }
              >
                {editing ? "Сохранить роль" : "Добавить"}
              </Button>
              <Button
                onClick={() => {
                  setFormOpen(false);
                  add.reset();
                }}
              >
                Отмена
              </Button>
            </div>
          </fieldset>
        </form>
      )}
      <ConfirmDialog
        open={confirmRole}
        onOpenChange={(open) => {
          if (!add.isPending) setConfirmRole(open);
        }}
        title={
          editing
            ? "Изменить роль участника?"
            : "Предоставить права администратора?"
        }
        description={
          <div className="stack">
            <p>
              {identity}: {editing ? `${roles[editing.role]} → ` : ""}
              {roles[role]}.
            </p>
            {role === "admin" && (
              <p>
                Пользователь сможет управлять участниками, правилами и массовыми
                изменениями группы.
              </p>
            )}
            <Feedback error={addError} />
          </div>
        }
        confirmLabel={editing ? "Изменить роль" : "Предоставить доступ"}
        pending={add.isPending}
        onConfirm={() => {
          if (!pending) add.mutate();
        }}
      />
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(open) => {
          if (!open && !remove.isPending) setRemoving(null);
        }}
        title="Отозвать доступ к группе?"
        description={
          <div className="stack">
            <p>
              Участник {removing?.username} потеряет доступ через эту группу.
              Прямые разрешения на отдельные серверы сохранятся.
            </p>
            <Feedback error={remove.error} />
          </div>
        }
        confirmLabel="Отозвать доступ"
        pending={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </div>
  );
}
