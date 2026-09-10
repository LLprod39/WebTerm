import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Play, RefreshCw } from "lucide-react";
import { governanceApi } from "@/api/governance";
import {
  serverGroupsApi,
  type BulkAction,
  type BulkOperation,
  type BulkRequest,
} from "@/api/server-groups";
import { usePermission, useSession } from "@/app/session";
import {
  Button,
  ConfirmDialog,
  DataTable,
  ErrorState,
  Feedback,
  Field,
  LoadingState,
  Metric,
  Panel,
  StatusBadge,
} from "@/components/ui";
import { formatDate } from "@/lib/utils";

const actionNames: Record<BulkAction, string> = {
  set_active: "Активность записи сервера",
  set_ai_read_only: "Режим AI только для чтения",
  set_tags: "Заменить теги",
};
export function GroupBulkOperations({
  groupId,
  groupName,
}: {
  groupId: number;
  groupName: string;
}) {
  const { user } = useSession();
  const automation = usePermission("automation");
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [action, setAction] = useState<BulkAction>("set_ai_read_only");
  const [value, setValue] = useState(true);
  const [tags, setTags] = useState("");
  const [confirm, setConfirm] = useState(false);
  const project = useQuery({
    queryKey: ["projects"],
    queryFn: ({ signal }) => governanceApi.projects(signal),
  });
  const current = project.data?.projects.find(
    (item) => item.id === project.data?.active_project_id,
  );
  const canWrite =
    !!current && ["owner", "admin", "operator"].includes(current.role);
  const forbidden = action === "set_ai_read_only" && !value && !automation;
  const operationId = Number(params.get("bulk_operation"));
  const operation = useQuery({
    queryKey: ["group-bulk-operation", operationId, user?.active_project?.id],
    queryFn: ({ signal }) => serverGroupsApi.bulkOperation(operationId, signal),
    enabled: Number.isSafeInteger(operationId) && operationId > 0,
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.operation.status ?? "")
        ? 2000
        : false,
  });
  const body: BulkRequest =
    action === "set_tags"
      ? { action, parameters: { value: tags } }
      : { action, parameters: { value } };
  const create = useMutation({
    mutationKey: ["server-group", groupId],
    mutationFn: () => serverGroupsApi.bulkCreate(groupId, body),
    onSuccess: (data) => {
      client.setQueryData(
        ["group-bulk-operation", data.operation.id, user?.active_project?.id],
        data,
      );
      const next = new URLSearchParams(params);
      next.set("tab", "groups");
      next.set("group", String(groupId));
      next.set("group_view", "bulk");
      next.set("bulk_operation", String(data.operation.id));
      setParams(next, { replace: true });
      setConfirm(false);
    },
  });
  const result = operation.data?.operation;
  const completedId =
    result && ["completed", "failed"].includes(result.status)
      ? result.id
      : null;
  useEffect(() => {
    if (completedId) void client.invalidateQueries({ queryKey: ["servers"] });
  }, [completedId, client]);
  const inProgress =
    result?.group_id === groupId &&
    ["queued", "running"].includes(result.status);
  const description =
    action === "set_tags"
      ? `Теги будут заменены на «${tags || "пустой список"}».`
      : action === "set_active"
        ? value
          ? "Записи серверов станут активными."
          : "Записи серверов станут неактивными."
        : value
          ? "AI будет переведён в режим только для чтения."
          : "Ограничение AI только для чтения будет снято.";
  function submit(event: FormEvent) {
    event.preventDefault();
    if (canWrite && !forbidden && !inProgress && !create.isPending) {
      create.reset();
      setConfirm(true);
    }
  }
  return (
    <div className="stack">
      <p className="muted">
        Изменение охватит все серверы группы «{groupName}» в активном проекте. В
        том числе неактивные записи. Состав группы фиксируется при запуске.
      </p>
      {project.error ? (
        <ErrorState
          error={project.error}
          retry={() => void project.refetch()}
        />
      ) : project.isPending ? (
        <LoadingState />
      ) : !canWrite ? (
        <div className="notice">
          Для запуска нужна роль оператора, администратора или владельца
          активного проекта.
        </div>
      ) : (
        <form onSubmit={submit}>
          <fieldset
            className="stack"
            disabled={create.isPending || inProgress}
            style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
          >
            <Field label="Массовое изменение" htmlFor="group-bulk-action">
              <select
                id="group-bulk-action"
                value={action}
                onChange={(event) =>
                  setAction(event.target.value as BulkAction)
                }
              >
                {Object.entries(actionNames).map(([id, name]) => (
                  <option key={id} value={id}>
                    {name}
                  </option>
                ))}
              </select>
            </Field>
            {action === "set_tags" ? (
              <Field
                label="Новые теги"
                htmlFor="group-bulk-tags"
                description="Заменяет существующие теги, максимум 500 символов."
              >
                <input
                  id="group-bulk-tags"
                  value={tags}
                  maxLength={500}
                  onChange={(event) => setTags(event.target.value)}
                />
              </Field>
            ) : (
              <Field label="Новое значение" htmlFor="group-bulk-value">
                <select
                  id="group-bulk-value"
                  value={String(value)}
                  onChange={(event) => setValue(event.target.value === "true")}
                >
                  <option value="true">
                    {action === "set_active" ? "Активны" : "Только чтение"}
                  </option>
                  <option value="false">
                    {action === "set_active"
                      ? "Неактивны"
                      : "Разрешить изменения"}
                  </option>
                </select>
              </Field>
            )}
            {action === "set_active" && (
              <p className="muted text-sm">
                Меняется активность записи в WebTerm. Питание серверов и
                процессы не затрагиваются.
              </p>
            )}
            {forbidden && (
              <div className="notice">
                Для снятия ограничения требуется разрешение на автоматизацию.
              </div>
            )}
            <Button
              type="submit"
              variant="primary"
              disabled={forbidden || inProgress}
              loading={create.isPending}
            >
              <Play size={14} />
              Проверить и запустить
            </Button>
          </fieldset>
        </form>
      )}
      {operationId > 0 && (
        <Panel
          title={`Операция #${operationId}`}
          actions={
            <Button
              size="sm"
              loading={operation.isFetching}
              onClick={() => void operation.refetch()}
            >
              <RefreshCw size={14} />
              Обновить
            </Button>
          }
        >
          {operation.error ? (
            <ErrorState
              error={operation.error}
              retry={() => void operation.refetch()}
            />
          ) : operation.isPending ? (
            <LoadingState />
          ) : result?.group_id !== groupId ? (
            <div className="notice">Операция относится к другой группе.</div>
          ) : result ? (
            <OperationReport operation={result} />
          ) : null}
        </Panel>
      )}
      <ConfirmDialog
        open={confirm}
        onOpenChange={(open) => {
          if (!create.isPending) setConfirm(open);
        }}
        title="Применить ко всей группе?"
        typedText={groupName}
        description={
          <div className="stack">
            <p>{description}</p>
            <p>
              Группа: {groupName}. Проект: {current?.name}. Изменение
              выполняется в фоне; отмена после постановки в очередь не
              предусмотрена.
            </p>
            <Feedback error={create.error} />
          </div>
        }
        confirmLabel="Запустить изменение"
        pending={create.isPending}
        onConfirm={() => {
          if (canWrite && !forbidden && !inProgress && !create.isPending)
            create.mutate();
        }}
      />
    </div>
  );
}
function OperationReport({ operation }: { operation: BulkOperation }) {
  const [copyMessage, setCopyMessage] = useState("");
  return (
    <div className="stack section-body">
      <div className="row spread">
        <StatusBadge status={operation.status} />
        <Button
          size="sm"
          onClick={() => {
            void navigator.clipboard.writeText(window.location.href).then(
              () => setCopyMessage("Ссылка скопирована"),
              () =>
                setCopyMessage(
                  "Не удалось скопировать. Скопируйте адрес страницы.",
                ),
            );
          }}
        >
          <Copy size={14} />
          Скопировать ссылку
        </Button>
      </div>
      {copyMessage && (
        <p role="status" className="muted text-sm">
          {copyMessage}
        </p>
      )}
      <p>
        {actionNames[operation.action]} ·{" "}
        {typeof operation.parameters.value === "boolean"
          ? operation.parameters.value
            ? "Включено"
            : "Выключено"
          : operation.parameters.value || "Пустой список"}
      </p>
      <progress
        className="full-width"
        aria-label="Прогресс массовой операции"
        max={100}
        value={operation.progress_percent}
      />
      <div className="metrics-strip">
        <Metric
          label="Обработано"
          value={`${operation.processed_count} / ${operation.total_count}`}
        />
        <Metric label="Успешно" value={operation.succeeded_count} />
        <Metric label="Ошибок" value={operation.failed_count} />
      </div>
      <dl className="detail-list">
        <dt>Создана</dt>
        <dd>{formatDate(operation.created_at)}</dd>
        <dt>Начало</dt>
        <dd>{formatDate(operation.started_at)}</dd>
        <dt>Завершение</dt>
        <dd>{formatDate(operation.completed_at)}</dd>
      </dl>
      {operation.status === "queued" && (
        <p className="muted text-sm">
          Ожидает обработчика массовых операций. Статус обновляется
          автоматически.
        </p>
      )}
      {!!operation.failures.length && (
        <DataTable
          rows={operation.failures.map((failure, index) => ({
            ...failure,
            index,
          }))}
          rowKey={(row) => row.index}
          columns={[
            {
              key: "server",
              label: "Сервер",
              render: (row) => row.server_id ?? "Вся операция",
            },
            { key: "error", label: "Причина", render: (row) => row.error },
          ]}
        />
      )}
    </div>
  );
}
