import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import {
  useIsMutating,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { Folder, Plus, Pencil, Trash2, ChevronDown } from "lucide-react";
import * as Dropdown from "@radix-ui/react-dropdown-menu";
import {
  infrastructureApi,
  type ServerGroup,
  type ServerRow,
} from "@/api/infrastructure";
import { GroupMembers } from "./GroupMembers";
import { GroupContext } from "./GroupContext";
import { GroupBulkOperations } from "./GroupBulkOperations";
import { GroupServers } from "./GroupServers";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
  Feedback,
  Field,
  Panel,
  Tabs,
} from "@/components/ui";
export function ServerGroups({
  groups,
  servers,
}: {
  groups: ServerGroup[];
  servers: ServerRow[];
}) {
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const selected = groups.find(
    (group) => group.id != null && String(group.id) === params.get("group"),
  );
  const requestedTab = params.get("group_view") ?? "servers";
  const tab =
    (requestedTab === "context" && selected?.role) ||
    (["members", "bulk"].includes(requestedTab) && selected?.can_edit)
      ? requestedTab
      : "servers";
  const pendingGroup =
    useIsMutating({ mutationKey: ["server-group", selected?.id] }) > 0;
  function openGroup(group: ServerGroup | null) {
    if (pendingGroup) return;
    const next = new URLSearchParams(params);
    next.delete("bulk_operation");
    next.delete("group_view");
    if (group?.id) next.set("group", String(group.id));
    else next.delete("group");
    setParams(next, { replace: true });
  }
  function setTab(value: string) {
    if (pendingGroup) return;
    const next = new URLSearchParams(params);
    next.set("group_view", value);
    setParams(next, { replace: true });
  }
  const [editing, setEditing] = useState<ServerGroup | null | undefined>();
  const [removing, setRemoving] = useState<ServerGroup | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [discard, setDiscard] = useState(false);
  const duplicateName = groups.some(
    (group) =>
      group.role === "owner" &&
      group.id !== editing?.id &&
      group.name === name.trim(),
  );
  const invalidate = () =>
    void client.invalidateQueries({ queryKey: ["servers"] });
  const save = useMutation({
    mutationFn: () =>
      editing?.id
        ? infrastructureApi.groupUpdate(editing.id, {
            name: name.trim(),
            description,
          })
        : infrastructureApi.groupCreate({ name: name.trim(), description }),
    onSuccess: () => {
      invalidate();
      setEditing(undefined);
    },
  });
  const remove = useMutation({
    mutationFn: () => infrastructureApi.groupRemove(removing!.id!),
    onSuccess: () => {
      invalidate();
      setRemoving(null);
    },
  });
  function edit(group: ServerGroup | null) {
    setName(group?.name ?? "");
    setDescription(group?.description ?? "");
    save.reset();
    setEditing(group);
  }
  function closeEditor() {
    if (save.isPending) return;
    if (
      name !== (editing?.name ?? "") ||
      description !== (editing?.description ?? "")
    )
      setDiscard(true);
    else setEditing(undefined);
  }
  function submit(e: FormEvent) {
    e.preventDefault();
    if (name.trim() && !duplicateName && !save.isPending) save.mutate();
  }
  return (
    <>
      <Panel>
        <DataTable
          rows={groups.filter((g) => g.id != null)}
          rowKey={(g) => g.id!}
          searchValue={(g) => `${g.name} ${g.description}`}
          searchPlaceholder="Найти группу…"
          hideSinglePagePagination
          toolbar={
            <Button variant="primary" onClick={() => edit(null)}>
              <Plus size={14} />
              Создать группу
            </Button>
          }
          emptyTitle="Объедините серверы в группы"
          emptyDescription="Отделите окружения, сервисы или команды."
          columns={[
            {
              key: "name",
              label: "Группа",
              sortValue: (g) => g.name,
              render: (g) => (
                <div className="table-name">
                  <Folder size={18} />
                  <div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => openGroup(g)}
                    >
                      {g.name}
                    </Button>
                    <small>{g.description}</small>
                  </div>
                </div>
              ),
            },
            {
              key: "count",
              label: "Серверы",
              sortValue: (g) => g.server_count,
              render: (g) => g.server_count,
            },
            {
              key: "role",
              label: "Ваша роль",
              render: (g) =>
                ({
                  owner: "Владелец",
                  admin: "Администратор",
                  member: "Участник",
                  viewer: "Наблюдатель",
                })[g.role] ?? "Доступ к отдельным серверам",
            },
            {
              key: "actions",
              label: "",
              render: (g) => (
                <div className="table-actions">
                  {g.can_edit && (
                    <>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={`Настроить ${g.name}`}
                        onClick={() => edit(g)}
                      >
                        <Pencil size={14} />
                      </Button>
                      {g.role === "owner" && (
                        <Button
                          size="icon"
                          variant="ghost"
                          aria-label={`Удалить ${g.name}`}
                          onClick={() => {
                            remove.reset();
                            setRemoving(g);
                          }}
                        >
                          <Trash2 size={14} />
                        </Button>
                      )}
                    </>
                  )}
                </div>
              ),
            },
          ]}
        />
      </Panel>
      <Drawer
        wide
        open={!!selected}
        onOpenChange={(open) => {
          if (!open) openGroup(null);
        }}
        closeDisabled={pendingGroup}
        title={selected?.name ?? "Группа"}
        description="Серверы, участники и правила работы группы."
      >
        {selected && (
          <div className="stack">
            <div className="row spread">
              <Tabs
                value={tab}
                disabled={pendingGroup}
                onChange={setTab}
                items={[
                  {
                    value: "servers",
                    label: "Серверы",
                    count: selected.server_count,
                  },
                  ...(selected.can_edit
                    ? [{ value: "members", label: "Доступ" }]
                    : []),
                ]}
              />
              {!!selected.role && (
                <Dropdown.Root>
                  <Dropdown.Trigger asChild>
                    <Button
                      variant="ghost"
                      disabled={pendingGroup}
                      aria-label="Ещё в группе"
                    >
                      {tab === "context"
                        ? "Правила AI"
                        : tab === "bulk"
                          ? "Массовые изменения"
                          : "Ещё"}
                      <ChevronDown size={14} />
                    </Button>
                  </Dropdown.Trigger>
                  <Dropdown.Portal>
                    <Dropdown.Content className="menu-content" align="end">
                      <Dropdown.Item
                        className="menu-item"
                        onSelect={() => setTab("context")}
                      >
                        Правила AI
                      </Dropdown.Item>
                      {selected.can_edit && (
                        <Dropdown.Item
                          className="menu-item"
                          onSelect={() => setTab("bulk")}
                        >
                          Массовые изменения
                        </Dropdown.Item>
                      )}
                    </Dropdown.Content>
                  </Dropdown.Portal>
                </Dropdown.Root>
              )}
            </div>
            {tab === "servers" && (
              <GroupServers
                key={`servers-${selected.id}`}
                group={selected}
                groups={groups}
                servers={servers}
                onCreate={() => {
                  if (pendingGroup) return;
                  const next = new URLSearchParams(params);
                  next.set("tab", "servers");
                  next.set("create", "1");
                  next.set("server_group", String(selected.id));
                  next.delete("group");
                  next.delete("group_view");
                  next.delete("bulk_operation");
                  setParams(next, { replace: true });
                }}
              />
            )}
            {tab === "context" && selected.role && (
              <GroupContext
                key={`context-${selected.id}`}
                groupId={selected.id!}
                canEdit={selected.can_edit}
              />
            )}
            {tab === "members" && selected.can_edit && (
              <GroupMembers
                key={`members-${selected.id}`}
                groupId={selected.id!}
              />
            )}
            {tab === "bulk" && selected.can_edit && (
              <GroupBulkOperations
                key={`bulk-${selected.id}`}
                groupId={selected.id!}
                groupName={selected.name}
              />
            )}
          </div>
        )}
      </Drawer>
      <Drawer
        open={editing !== undefined}
        onOpenChange={(open) => {
          if (!open) closeEditor();
        }}
        closeDisabled={save.isPending}
        title={editing ? "Настроить группу" : "Создать группу"}
      >
        <form onSubmit={submit}>
          <fieldset
            className="stack"
            disabled={save.isPending}
            style={{ border: 0, margin: 0, padding: 0 }}
          >
            <Field
              label="Название"
              htmlFor="group-name"
              error={
                duplicateName
                  ? "У вас уже есть группа с таким названием."
                  : undefined
              }
            >
              <input
                id="group-name"
                required
                maxLength={100}
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </Field>
            <Field label="Описание" htmlFor="group-description">
              <textarea
                id="group-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </Field>
            <Feedback error={save.error} />
            <div className="form-actions">
              <Button onClick={closeEditor}>Отмена</Button>
              <Button
                type="submit"
                variant="primary"
                disabled={!name.trim() || duplicateName}
                loading={save.isPending}
              >
                {editing ? "Сохранить изменения" : "Создать группу"}
              </Button>
            </div>
          </fieldset>
        </form>
      </Drawer>
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(open) => {
          if (!open && !remove.isPending) setRemoving(null);
        }}
        title="Удалить группу?"
        description={
          <div className="stack">
            <p>
              Группа «{removing?.name}» будет удалена. Серверы сохранятся без
              этой группы.
            </p>
            <Feedback error={remove.error} />
          </div>
        }
        pending={remove.isPending}
        onConfirm={() => remove.mutate()}
        confirmLabel="Удалить группу"
      />
      <ConfirmDialog
        open={discard}
        onOpenChange={setDiscard}
        title="Закрыть без сохранения?"
        description="Введённые параметры группы будут потеряны."
        confirmLabel="Не сохранять"
        onConfirm={() => {
          setDiscard(false);
          setEditing(undefined);
        }}
      />
    </>
  );
}
