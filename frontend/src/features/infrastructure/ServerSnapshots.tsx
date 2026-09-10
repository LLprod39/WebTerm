import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileClock, RefreshCw } from "lucide-react";
import type { ServerDetail } from "@/api/infrastructure";
import {
  serverOperationsApi,
  type RollbackSnapshot,
} from "@/api/server-operations";
import { serverWorkspaceApi } from "@/api/server-workspace";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
  EmptyState,
  ErrorState,
  Feedback,
  LoadingState,
  Panel,
  StatusBadge,
} from "@/components/ui";
import { useUnsavedEditsBlocker } from "@/features/automation/unsaved";
import "./server-operations.css";

function SnapshotReview({
  server,
  snapshot,
  onClose,
}: {
  server: ServerDetail;
  snapshot: RollbackSnapshot;
  onClose: () => void;
}) {
  const client = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const query = useQuery({
    queryKey: ["server-snapshot", server.id, snapshot.id],
    queryFn: ({ signal }) =>
      serverOperationsApi.snapshotDetail(server.id, snapshot.id, signal),
    retry: false,
  });
  const prepare = useMutation({
    mutationKey: ["server-workspace", server.id],
    mutationFn: () =>
      serverOperationsApi.prepareRestore(server.id, snapshot.id),
    onSuccess: () => setConfirm(true),
  });
  const execution = useMutation({
    mutationKey: ["server-workspace", server.id],
    mutationFn: async () => {
      if (!prepare.data?.restore_command)
        throw new Error(
          "Не удалось подготовить восстановление. Попробуйте ещё раз.",
        );
      const response = await serverWorkspaceApi.execute(
        server.id,
        prepare.data.restore_command,
      );
      if (response.output.exit_code !== 0)
        throw new Error(
          "Восстановление не подтверждено. Код завершения: " +
            (response.output.exit_code ?? "не получен") +
            ". " +
            (response.output.stderr || response.output.stdout || ""),
        );
      return response;
    },
    onSuccess: () => {
      setConfirm(false);
      void client.invalidateQueries({ queryKey: ["files", server.id] });
    },
  });
  const busy = prepare.isPending || execution.isPending;
  const blocker = useUnsavedEditsBlocker(busy);
  const data = query.data?.snapshot;
  const absent = data?.file_existed === false;
  const ambiguous = data?.file_existed == null && !data?.content;
  return (
    <>
      <Drawer
        open
        onOpenChange={(open) => {
          if (!open && !busy) onClose();
        }}
        closeDisabled={busy}
        title="Снимок файла"
        description={snapshot.file_path}
        wide
      >
        {query.isPending ? (
          <LoadingState />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : (
          data && (
            <div className="stack">
              <dl className="ops-facts">
                <div>
                  <dt>Создан</dt>
                  <dd>{new Date(data.created_at).toLocaleString("ru-RU")}</dd>
                </div>
                <div>
                  <dt>Размер</dt>
                  <dd>{data.byte_size.toLocaleString("ru-RU")} байт</dd>
                </div>
              </dl>
              <details className="technical-details">
                <summary>Команда перед изменением и контрольная сумма</summary>
                <pre className="code-block">{data.command}</pre>
                <p className="mono text-sm">SHA-256: {data.content_hash}</p>
              </details>
              <div>
                <h3>Сохранённое содержимое</h3>
                <pre className="code-block ops-log">
                  {data.content ||
                    (absent
                      ? "Файла ещё не было."
                      : ambiguous
                        ? "Содержимое не сохранено."
                        : "Пустой файл · 0 байт")}
                </pre>
              </div>
              {data.content_truncated ? (
                <div className="notice notice-warning">
                  Снимок усечён. Восстановление из него недоступно: часть
                  содержимого не сохранена.
                </div>
              ) : ambiguous ? (
                <div className="notice notice-warning">
                  Старый снимок не различает пустой файл и ошибку чтения.
                  Автоматическое восстановление недоступно.
                </div>
              ) : (
                <p className="muted text-sm">
                  {absent
                    ? "Восстановление удалит файл, созданный после этого снимка."
                    : "Восстановление заменит текущее содержимое файла. Сохраните текущую версию, если она нужна."}
                </p>
              )}
              <div className="row">
                <Button
                  variant="primary"
                  loading={busy}
                  disabled={
                    data.content_truncated ||
                    ambiguous ||
                    !server.capabilities.execute_command ||
                    execution.isSuccess
                  }
                  onClick={() => {
                    if (!busy) {
                      execution.reset();
                      prepare.mutate();
                    }
                  }}
                >
                  <FileClock size={14} />
                  Восстановить
                </Button>
              </div>
              {!server.capabilities.execute_command && (
                <p className="muted text-sm">
                  Для восстановления нужно разрешение на выполнение команд
                  сервера.
                </p>
              )}
              <Feedback
                error={prepare.error}
                success={
                  execution.isSuccess
                    ? absent
                      ? "Файл удалён. Состояние до изменения восстановлено."
                      : "Содержимое файла восстановлено."
                    : undefined
                }
              />
              <ConfirmDialog
                open={confirm}
                onOpenChange={(open) => {
                  if (!execution.isPending) setConfirm(open);
                }}
                title={
                  absent
                    ? "Удалить созданный файл?"
                    : "Заменить содержимое файла?"
                }
                description={
                  <>
                    <p>
                      <strong>{server.name}</strong> ·{" "}
                      <span className="mono">
                        {server.username}@{server.host}:{server.port}
                      </span>
                    </p>
                    <p>
                      {absent
                        ? "Будет удалён файл:"
                        : "Будет восстановлен файл:"}{" "}
                      <span className="mono">{data.file_path}</span>
                    </p>
                    <p>Введите полный путь для подтверждения.</p>
                    <details className="technical-details">
                      <summary>Команда восстановления</summary>
                      <pre className="code-block ops-log">
                        {prepare.data?.restore_command}
                      </pre>
                    </details>
                    <Feedback error={execution.error} />
                  </>
                }
                typedText={data.file_path}
                confirmLabel={absent ? "Удалить файл" : "Восстановить файл"}
                pending={execution.isPending}
                onConfirm={() => {
                  if (!execution.isPending) execution.mutate();
                }}
              />
            </div>
          )
        )}
      </Drawer>
      <ConfirmDialog
        open={blocker.state === "blocked"}
        title="Восстановление выполняется"
        description="Дождитесь результата перед переходом на другую страницу."
        onOpenChange={() => {
          if (blocker.state === "blocked") blocker.reset();
        }}
        confirmLabel="Остаться"
        onConfirm={() => {
          if (blocker.state === "blocked") blocker.reset();
        }}
      />
    </>
  );
}

export function ServerSnapshots({ server }: { server: ServerDetail }) {
  const [selected, setSelected] = useState<RollbackSnapshot | null>(null);
  const query = useQuery({
    queryKey: ["server-snapshots", server.id],
    queryFn: ({ signal }) => serverOperationsApi.snapshots(server.id, signal),
    retry: false,
  });
  return (
    <Panel
      title="Снимки файлов"
      description="Ваши сохранённые версии перед изменениями файлов через AI в терминале."
      actions={
        <Button
          size="sm"
          onClick={() => void query.refetch()}
          loading={query.isFetching}
        >
          <RefreshCw size={14} />
          Обновить
        </Button>
      }
    >
      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : !query.data.snapshots.length ? (
        <EmptyState
          icon={<FileClock size={24} />}
          title="Снимков пока нет"
          description="Они появляются перед поддерживаемыми командами AI, изменяющими текстовые файлы. Изменения в редакторе файлов сюда не попадают."
        />
      ) : (
        <DataTable
          rows={query.data.snapshots}
          rowKey={(row) => row.id}
          searchValue={(row) => row.file_path}
          searchPlaceholder="Найти файл…"
          hideSinglePagePagination
          columns={[
            {
              key: "file",
              label: "Файл",
              render: (row) => (
                <button
                  className="text-link mono"
                  onClick={() => setSelected(row)}
                >
                  {row.file_path}
                </button>
              ),
              sortValue: (row) => row.file_path,
            },
            {
              key: "size",
              label: "Размер",
              render: (row) => row.byte_size.toLocaleString("ru-RU") + " Б",
              sortValue: (row) => row.byte_size,
            },
            {
              key: "created",
              label: "Создан",
              render: (row) => new Date(row.created_at).toLocaleString("ru-RU"),
              sortValue: (row) => row.created_at,
            },
            {
              key: "state",
              label: "Состояние",
              render: (row) => (
                <StatusBadge
                  status={
                    row.content_truncated ||
                    (row.file_existed == null && row.byte_size === 0)
                      ? "warning"
                      : "ready"
                  }
                >
                  {row.content_truncated
                    ? "Усечён"
                    : row.file_existed === false
                      ? "Файла не было"
                      : row.file_existed == null && row.byte_size === 0
                        ? "Только просмотр"
                        : "Полный"}
                </StatusBadge>
              ),
            },
          ]}
        />
      )}
      {!!query.data && query.data.snapshots.length === 100 && (
        <p className="muted section-body text-sm">
          Показаны последние 100 снимков.
        </p>
      )}
      {selected && (
        <SnapshotReview
          key={selected.id}
          server={server}
          snapshot={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </Panel>
  );
}
