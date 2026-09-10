import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ServerGroup, ServerRow } from "@/api/infrastructure";
import { serverGroupsApi } from "@/api/server-groups";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Feedback,
  Field,
} from "@/components/ui";

export function GroupServers({
  group,
  groups,
  servers,
  onCreate,
}: {
  group: ServerGroup;
  groups: ServerGroup[];
  servers: ServerRow[];
  onCreate: () => void;
}) {
  const client = useQueryClient();
  const [selected, setSelected] = useState<number[]>([]);
  const [action, setAction] = useState("group");
  const [target, setTarget] = useState("");
  const [tags, setTags] = useState("");
  const [active, setActive] = useState(true);
  const [confirm, setConfirm] = useState(false);
  const rows = servers.filter((server) => server.group_id === group.id);
  const selectedRows = rows.filter(
    (server) => server.can_edit && selected.includes(server.id),
  );
  const targetGroup = groups.find((item) => String(item.id) === target);
  const update = useMutation({
    mutationKey: ["server-group", group.id],
    mutationFn: () =>
      serverGroupsApi.updateServers({
        server_ids: selectedRows.map((server) => server.id),
        ...(action === "group"
          ? { group_id: target ? Number(target) : null }
          : action === "tags"
            ? { tags }
            : { is_active: active }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["servers"] });
      setSelected([]);
      setConfirm(false);
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    if (selectedRows.length && !update.isPending) {
      update.reset();
      setConfirm(true);
    }
  }
  return (
    <div className="stack">
      <DataTable
        rows={rows}
        rowKey={(server) => server.id}
        searchValue={(server) => `${server.name} ${server.host}`}
        searchPlaceholder="Найти сервер в группе…"
        hideSinglePagePagination
        emptyTitle="В группе нет доступных серверов"
        emptyDescription={
          group.role
            ? "Добавьте SSH-подключение. Группа уже будет выбрана."
            : "Здесь появятся серверы, к которым вам предоставят доступ."
        }
        toolbar={
          <>
            {!!group.role && (
              <Button
                variant="primary"
                onClick={onCreate}
                disabled={update.isPending}
              >
                Добавить сервер
              </Button>
            )}
            {rows.some((row) => row.can_edit) && (
              <Button
                size="sm"
                disabled={update.isPending}
                onClick={() =>
                  setSelected(
                    selectedRows.length
                      ? []
                      : rows.filter((row) => row.can_edit).map((row) => row.id),
                  )
                }
              >
                {selectedRows.length ? "Снять выбор" : "Выбрать свои серверы"}
              </Button>
            )}
          </>
        }
        columns={[
          {
            key: "select",
            label: "",
            render: (server) => (
              <input
                type="checkbox"
                aria-label={`Выбрать ${server.name}`}
                disabled={!server.can_edit || update.isPending}
                checked={selectedRows.some((row) => row.id === server.id)}
                onChange={(event) =>
                  setSelected(
                    event.target.checked
                      ? [...selected, server.id]
                      : selected.filter((id) => id !== server.id),
                  )
                }
              />
            ),
          },
          {
            key: "server",
            label: "Сервер",
            sortValue: (server) => server.name,
            render: (server) => (
              <Link to={`/infrastructure/servers/${server.id}`}>
                <strong>{server.name}</strong>
              </Link>
            ),
          },
          {
            key: "host",
            label: "Адрес SSH",
            sortValue: (server) => server.host,
            render: (server) => (
              <span className="mono">
                {server.username}@{server.host}:{server.port}
              </span>
            ),
          },
        ]}
      />
      <Feedback
        success={
          update.isSuccess
            ? "Изменение сохранено. Список серверов обновлён."
            : undefined
        }
      />
      {!!selectedRows.length && (
        <form onSubmit={submit}>
          <fieldset
            className="stack"
            disabled={update.isPending}
            style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
          >
            <h3>Изменить выбранные серверы · {selectedRows.length}</h3>
            <p className="muted text-sm">
              Выбирать можно только серверы, которыми вы владеете.
            </p>
            <Field label="Действие" htmlFor="group-selection-action">
              <select
                id="group-selection-action"
                value={action}
                onChange={(event) => setAction(event.target.value)}
              >
                <option value="group">Переместить в группу</option>
                <option value="tags">Заменить теги</option>
                <option value="active">Изменить активность записей</option>
              </select>
            </Field>
            {action === "group" ? (
              <Field label="Целевая группа" htmlFor="group-selection-target">
                <select
                  id="group-selection-target"
                  value={target}
                  onChange={(event) => setTarget(event.target.value)}
                >
                  <option value="">Без группы</option>
                  {groups
                    .filter((item) => item.id != null && item.role)
                    .map((item) => (
                      <option value={item.id!} key={item.id}>
                        {item.name}
                      </option>
                    ))}
                </select>
              </Field>
            ) : action === "tags" ? (
              <Field label="Новые теги" htmlFor="group-selection-tags">
                <input
                  id="group-selection-tags"
                  maxLength={500}
                  value={tags}
                  onChange={(event) => setTags(event.target.value)}
                />
              </Field>
            ) : (
              <Field label="Активность" htmlFor="group-selection-active">
                <select
                  id="group-selection-active"
                  value={String(active)}
                  onChange={(event) => setActive(event.target.value === "true")}
                >
                  <option value="true">Активны</option>
                  <option value="false">Неактивны</option>
                </select>
                {!active && (
                  <p className="muted text-sm">
                    Серверы исчезнут из активного списка. Вернуть их можно через
                    «Ещё → Массовые изменения» в этой группе.
                  </p>
                )}
              </Field>
            )}
            <Button type="submit" variant="primary" loading={update.isPending}>
              Проверить изменение
            </Button>
          </fieldset>
        </form>
      )}
      <ConfirmDialog
        open={confirm}
        onOpenChange={(open) => {
          if (!update.isPending) setConfirm(open);
        }}
        title={`Изменить ${selectedRows.length} серверов?`}
        description={
          <div className="stack">
            <p>{selectedRows.map((server) => server.name).join(", ")}</p>
            <p>
              {action === "group"
                ? `Целевая группа: ${targetGroup?.name ?? "Без группы"}.`
                : action === "tags"
                  ? `Теги будут заменены на «${tags || "пустой список"}».`
                  : `Записи станут ${active ? "активными" : "неактивными"}.`}
            </p>
            <Feedback error={update.error} />
          </div>
        }
        pending={update.isPending}
        onConfirm={() => update.mutate()}
        confirmLabel="Применить изменение"
      />
    </div>
  );
}
