import { useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, FileText, RefreshCw, ShieldCheck } from "lucide-react";
import { ApiError } from "@/api/client";
import type { ServerDetail } from "@/api/infrastructure";
import {
  serverOperationsApi,
  type LinuxAction,
  type LinuxActionResult,
  type LinuxSnapshots,
} from "@/api/server-operations";
import { useSession } from "@/app/session";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
  EmptyState,
  ErrorState,
  Feedback,
  Field,
  LoadingState,
  Metric,
  Panel,
  StatusBadge,
  Tabs,
} from "@/components/ui";
import "./server-operations.css";
import { useUnsavedEditsBlocker } from "@/features/automation/unsaved";

type ServerProps = { server: ServerDetail };
type OperationAction = LinuxAction & { description?: string };
type RequestAction = (action: OperationAction) => void;
const actionLabels = {
  start: "Запустить",
  stop: "Остановить",
  restart: "Перезапустить",
  reload: "Перечитать конфигурацию",
  terminate: "Завершить",
  kill_force: "Завершить принудительно",
};
const num = (value: number | null | undefined, suffix = "") =>
  value == null
    ? "—"
    : `${value.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}${suffix}`;
const observed = (value: string) => new Date(value).toLocaleString("ru-RU");

function useSnapshot<T extends keyof LinuxSnapshots>(
  server: ServerDetail,
  resource: T,
  params: Record<string, string> = {},
) {
  return useQuery({
    queryKey: ["server-operations", server.id, resource, params],
    queryFn: ({ signal }) =>
      serverOperationsApi.snapshot(server.id, resource, params, signal),
    staleTime: 15_000,
    retry: false,
  });
}
function SnapshotState({
  loading,
  error,
  refresh,
  fetching,
  timestamp,
  showRefresh = true,
  children,
}: {
  loading: boolean;
  error: Error | null;
  refresh: () => unknown;
  fetching: boolean;
  timestamp?: string;
  showRefresh?: boolean;
  children: ReactNode;
}) {
  if (loading) return <LoadingState label="Получаем состояние сервера…" />;
  const accessDenied =
    error instanceof ApiError && [401, 403].includes(error.status);
  if (error && (!timestamp || accessDenied))
    return (
      <ErrorState
        error={error}
        retry={showRefresh ? () => void refresh() : undefined}
      />
    );
  return (
    <div className="stack">
      <div className="spread ops-observed">
        <span className="muted text-sm">
          {timestamp
            ? `Состояние на ${observed(timestamp)}`
            : "Снимок состояния"}
        </span>
        {showRefresh && (
          <Button size="sm" onClick={() => void refresh()} loading={fetching}>
            <RefreshCw size={14} />
            Обновить
          </Button>
        )}
      </div>
      {error && (
        <div role="alert" className="notice notice-warning">
          Не удалось обновить состояние. Показан последний полученный снимок.{" "}
          {error.message}
        </div>
      )}
      {children}
    </div>
  );
}
function Overview({ server }: ServerProps) {
  const query = useSnapshot(server, "overview");
  const data = query.data?.overview;
  return (
    <SnapshotState
      loading={query.isPending}
      error={query.error}
      refresh={query.refetch}
      fetching={query.isFetching}
      timestamp={query.data?.observed_at}
    >
      {data && (
        <>
          <div className="ops-metrics">
            <Metric
              label="Память"
              value={num(data.memory.percent, "%")}
              detail={`${num(data.memory.used_mb)} / ${num(data.memory.total_mb)} МБ`}
            />
            <Metric
              label="Диск /"
              value={num(data.disk.percent, "%")}
              detail={`${num(data.disk.used_gb)} / ${num(data.disk.total_gb)} ГБ`}
            />
            <Metric
              label="Нагрузка · 1 / 5 / 15 мин"
              value={num(data.load.one)}
              detail={`${num(data.load.five)} / ${num(data.load.fifteen)}`}
            />
            <Metric
              label="Процессы"
              value={num(data.process_count)}
              detail={
                data.uptime_seconds == null
                  ? "Время работы неизвестно"
                  : `Работает ${Math.floor(data.uptime_seconds / 86400)} д ${Math.floor((data.uptime_seconds % 86400) / 3600)} ч`
              }
            />
          </div>
          <dl className="ops-facts">
            {[
              ["Имя узла", data.hostname],
              ["Операционная система", data.os_name],
              ["Ядро", data.kernel],
              ["Пользователь", data.current_user],
              ["Домашний каталог", data.home_path],
              ...(data.cwd !== data.home_path
                ? [["Рабочий каталог", data.cwd]]
                : []),
            ].map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value || "—"}</dd>
              </div>
            ))}
          </dl>
        </>
      )}
    </SnapshotState>
  );
}
function WorkloadLogs({
  server,
  target,
  kind,
}: ServerProps & { target: string; kind: "services" | "docker" }) {
  const params = {
    [kind === "services" ? "service" : "container"]: target,
    lines: "120",
  };
  const query = useSnapshot(
    server,
    kind === "services" ? "services/logs" : "docker/logs",
    params,
  );
  const data =
    query.data &&
    ("service_logs" in query.data
      ? query.data.service_logs
      : query.data.docker_logs);
  return (
    <SnapshotState
      loading={query.isPending}
      error={query.error}
      refresh={query.refetch}
      fetching={query.isFetching}
      timestamp={query.data?.observed_at}
    >
      {data && (
        <>
          <p className="muted text-sm">
            {data.source || "Docker logs"} · последние {data.lines} строк
          </p>
          {data.available === false ? (
            <div role="status" className="notice notice-warning">
              {data.unavailable_reason ||
                "У пользователя SSH нет доступа к этому журналу."}
            </div>
          ) : (
            <pre className="code-block ops-log">
              {data.content || "Нет строк для отображения."}
            </pre>
          )}
        </>
      )}
    </SnapshotState>
  );
}
function Services({
  server,
  onAction,
}: ServerProps & { onAction: RequestAction }) {
  const query = useSnapshot(server, "services", { limit: "120" });
  const [state, setState] = useState("all");
  const [logs, setLogs] = useState<string | null>(null);
  return (
    <>
      <SnapshotState
        loading={query.isPending}
        error={query.error}
        refresh={query.refetch}
        fetching={query.isFetching}
        timestamp={query.data?.observed_at}
      >
        {query.data && (
          <>
            <DataTable
              rows={query.data.services.filter((row) =>
                state === "failed"
                  ? row.is_failed
                  : state === "active"
                    ? row.is_active
                    : state === "inactive"
                      ? row.health === "inactive"
                      : true,
              )}
              searchValue={(row) => `${row.unit} ${row.description}`}
              searchPlaceholder="Имя или описание службы…"
              hideSinglePagePagination
              defaultSort={{ key: "state", desc: false }}
              toolbar={
                <select
                  aria-label="Состояние служб"
                  value={state}
                  onChange={(e) => setState(e.target.value)}
                >
                  <option value="all">Все состояния</option>
                  <option value="failed">
                    С ошибкой ({query.data.summary.failed})
                  </option>
                  <option value="active">
                    Работают ({query.data.summary.active})
                  </option>
                  <option value="inactive">
                    Остановлены ({query.data.summary.inactive})
                  </option>
                </select>
              }
              rowKey={(row) => row.unit}
              emptyTitle="Службы не найдены"
              emptyDescription={
                state === "all"
                  ? "Сервер не вернул службы systemd."
                  : "В этом состоянии служб нет. Выберите другой фильтр."
              }
              columns={[
                {
                  key: "unit",
                  label: "Служба",
                  render: (row) => (
                    <div>
                      <strong className="mono">{row.unit}</strong>
                      <div className="muted text-sm">{row.description}</div>
                    </div>
                  ),
                  sortValue: (row) => row.unit,
                },
                {
                  key: "state",
                  label: "Состояние",
                  render: (row) => (
                    <div>
                      <StatusBadge status={row.health}>
                        {row.is_failed
                          ? "Ошибка"
                          : row.is_active
                            ? "Работает"
                            : row.health === "inactive"
                              ? "Остановлена"
                              : row.active}
                      </StatusBadge>
                      <div className="muted text-sm">
                        {row.load} · {row.sub}
                      </div>
                    </div>
                  ),
                  sortValue: (row) =>
                    row.is_failed ? 0 : row.is_active ? 2 : 1,
                },
                {
                  key: "actions",
                  label: "Действия",
                  render: (row) => (
                    <div className="ops-row-actions">
                      <Button size="sm" onClick={() => setLogs(row.unit)}>
                        <FileText size={13} />
                        Журнал
                      </Button>
                      <Dropdown.Root>
                        <Dropdown.Trigger asChild>
                          <Button
                            size="sm"
                            variant="ghost"
                            aria-label={`Управление службой ${row.unit}`}
                            disabled={!server.capabilities.execute_command}
                            title={
                              !server.capabilities.execute_command
                                ? "Нет разрешения на выполнение команд"
                                : undefined
                            }
                          >
                            Управление <ChevronDown size={14} />
                          </Button>
                        </Dropdown.Trigger>
                        <Dropdown.Portal>
                          <Dropdown.Content
                            className="menu-content"
                            align="end"
                          >
                            {(row.is_active
                              ? (["restart", "reload", "stop"] as const)
                              : (["start"] as const)
                            ).map((action) => (
                              <Dropdown.Item
                                key={action}
                                className={`menu-item${action === "stop" ? " danger" : ""}`}
                                onSelect={() =>
                                  onAction({
                                    kind: "services",
                                    target: row.unit,
                                    action,
                                  })
                                }
                              >
                                {actionLabels[action]}
                              </Dropdown.Item>
                            ))}
                          </Dropdown.Content>
                        </Dropdown.Portal>
                      </Dropdown.Root>
                    </div>
                  ),
                },
              ]}
            />
            <p className="muted text-sm">
              Поиск и фильтры по снимку из {query.data.services.length} служб.
              Сервер возвращает до {query.data.limit} записей.
            </p>
          </>
        )}
      </SnapshotState>
      <Drawer
        open={logs !== null}
        onOpenChange={(open) => !open && setLogs(null)}
        title={`Журнал · ${logs || ""}`}
        description={`${server.name} · ${server.host}`}
        wide
      >
        {logs && <WorkloadLogs server={server} kind="services" target={logs} />}
      </Drawer>
    </>
  );
}
function Processes({
  server,
  onAction,
}: ServerProps & { onAction: RequestAction }) {
  const query = useSnapshot(server, "processes", { limit: "80" });
  const data = query.data?.processes;
  const rows = data
    ? [
        ...new Map(
          [...data.top_cpu, ...data.top_memory].map((row) => [row.pid, row]),
        ).values(),
      ]
    : [];
  return (
    <SnapshotState
      loading={query.isPending}
      error={query.error}
      refresh={query.refetch}
      fetching={query.isFetching}
      timestamp={query.data?.observed_at}
    >
      {data && (
        <>
          <DataTable
            rows={rows}
            searchValue={(row) =>
              `${row.pid} ${row.user} ${row.command} ${row.args}`
            }
            searchPlaceholder="PID, пользователь или команда…"
            defaultSort={{ key: "cpu", desc: true }}
            hideSinglePagePagination
            rowKey={(row) => row.pid}
            emptyTitle="Процессы не найдены"
            columns={[
              {
                key: "pid",
                label: "PID",
                render: (row) => <span className="mono">{row.pid}</span>,
                sortValue: (row) => row.pid,
              },
              {
                key: "command",
                label: "Команда",
                render: (row) => (
                  <details className="ops-command">
                    <summary>
                      <strong>{row.command}</strong>
                    </summary>
                    <pre className="code-block text-sm">{row.args}</pre>
                  </details>
                ),
              },
              { key: "user", label: "Пользователь", render: (row) => row.user },
              {
                key: "cpu",
                label: "CPU",
                render: (row) => num(row.cpu_percent, "%"),
                sortValue: (row) => row.cpu_percent ?? -1,
              },
              {
                key: "memory",
                label: "Память",
                render: (row) => num(row.memory_percent, "%"),
                sortValue: (row) => row.memory_percent ?? -1,
              },
              { key: "elapsed", label: "Время", render: (row) => row.elapsed },
              {
                key: "actions",
                label: "Действия",
                render: (row) => (
                  <Dropdown.Root>
                    <Dropdown.Trigger asChild>
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`Действия процесса ${row.pid}`}
                        title={
                          row.pid <= 1
                            ? "Основной системный процесс нельзя завершить"
                            : !server.capabilities.execute_command
                              ? "Нет разрешения на выполнение команд"
                              : undefined
                        }
                        disabled={
                          !server.capabilities.execute_command || row.pid <= 1
                        }
                      >
                        Управление
                        <ChevronDown size={14} />
                      </Button>
                    </Dropdown.Trigger>
                    <Dropdown.Portal>
                      <Dropdown.Content className="menu-content" align="end">
                        {(["terminate", "kill_force"] as const).map(
                          (action) => (
                            <Dropdown.Item
                              key={action}
                              className="menu-item danger"
                              onSelect={() =>
                                onAction({
                                  kind: "processes",
                                  target: row.pid,
                                  action,
                                  description: row.args || row.command,
                                })
                              }
                            >
                              {actionLabels[action]}
                            </Dropdown.Item>
                          ),
                        )}
                      </Dropdown.Content>
                    </Dropdown.Portal>
                  </Dropdown.Root>
                ),
              },
            ]}
          />
          <p className="muted text-sm">
            Поиск по снимку из {rows.length} процессов: до {data.limit} лидеров
            по CPU и памяти. Завершение применяется к PID на момент запроса.
          </p>
        </>
      )}
    </SnapshotState>
  );
}
function Docker({
  server,
  onAction,
}: ServerProps & { onAction: RequestAction }) {
  const query = useSnapshot(server, "docker");
  const [logs, setLogs] = useState<string | null>(null);
  const [state, setState] = useState("all");
  const data = query.data?.docker;
  return (
    <>
      <SnapshotState
        loading={query.isPending}
        error={query.error}
        refresh={query.refetch}
        fetching={query.isFetching}
        timestamp={query.data?.observed_at}
      >
        {data &&
          (data.ready ? (
            <>
              <DataTable
                rows={data.containers.filter(
                  (row) =>
                    state === "all" ||
                    (state === "other"
                      ? !["running", "exited"].includes(row.state)
                      : row.state === state),
                )}
                searchValue={(row) =>
                  `${row.name} ${row.id} ${row.image} ${row.ports}`
                }
                searchPlaceholder="Имя, ID, образ или порт…"
                hideSinglePagePagination
                toolbar={
                  <select
                    aria-label="Состояние контейнеров"
                    value={state}
                    onChange={(e) => setState(e.target.value)}
                  >
                    <option value="all">Все состояния</option>
                    <option value="running">Запущены</option>
                    <option value="exited">Остановлены</option>
                    <option value="other">Другие состояния</option>
                  </select>
                }
                rowKey={(row) => row.id}
                emptyTitle={
                  state === "all"
                    ? "Контейнеров пока нет"
                    : "Нет контейнеров в этом состоянии"
                }
                emptyDescription={
                  state === "all"
                    ? undefined
                    : "Выберите другой фильтр состояния."
                }
                columns={[
                  {
                    key: "name",
                    label: "Контейнер",
                    render: (row) => (
                      <div>
                        <strong>{row.name}</strong>
                        <div className="mono muted text-sm">{row.id}</div>
                      </div>
                    ),
                    sortValue: (row) => row.name,
                  },
                  {
                    key: "image",
                    label: "Образ",
                    render: (row) => <span className="mono">{row.image}</span>,
                  },
                  {
                    key: "state",
                    label: "Состояние",
                    render: (row) => (
                      <div>
                        <StatusBadge status={row.state}>
                          {(
                            {
                              running: "Работает",
                              exited: "Остановлен",
                              restarting: "Перезапускается",
                              paused: "Приостановлен",
                              created: "Создан",
                              dead: "Сбой",
                              removing: "Удаляется",
                            } as Record<string, string>
                          )[row.state] || row.state}
                        </StatusBadge>
                        <div className="muted text-sm">{row.status}</div>
                      </div>
                    ),
                    sortValue: (row) => row.state,
                  },
                  {
                    key: "resources",
                    label: "Ресурсы",
                    render: (row) => (
                      <div className="text-sm">
                        <span>CPU {row.cpu_percent || "—"}</span>
                        <div>Память {row.memory_usage || "—"}</div>
                      </div>
                    ),
                  },
                  {
                    key: "ports",
                    label: "Порты",
                    render: (row) => (
                      <span className="mono text-sm">{row.ports || "—"}</span>
                    ),
                  },
                  {
                    key: "actions",
                    label: "Действия",
                    render: (row) => (
                      <div className="ops-row-actions">
                        <Button size="sm" onClick={() => setLogs(row.id)}>
                          Журнал
                        </Button>
                        <Dropdown.Root>
                          <Dropdown.Trigger asChild>
                            <Button
                              size="sm"
                              variant="ghost"
                              aria-label={`Управление контейнером ${row.name}`}
                              disabled={!server.capabilities.execute_command}
                              title={
                                !server.capabilities.execute_command
                                  ? "Нет разрешения на выполнение команд"
                                  : undefined
                              }
                            >
                              Управление <ChevronDown size={14} />
                            </Button>
                          </Dropdown.Trigger>
                          <Dropdown.Portal>
                            <Dropdown.Content
                              className="menu-content"
                              align="end"
                            >
                              {(["running", "restarting", "paused"].includes(
                                row.state,
                              )
                                ? (["restart", "stop"] as const)
                                : (["start"] as const)
                              ).map((action) => (
                                <Dropdown.Item
                                  key={action}
                                  className={`menu-item${action === "stop" ? " danger" : ""}`}
                                  onSelect={() =>
                                    onAction({
                                      kind: "docker",
                                      target: row.id,
                                      action,
                                      description: row.name,
                                    })
                                  }
                                >
                                  {actionLabels[action]}
                                </Dropdown.Item>
                              ))}
                            </Dropdown.Content>
                          </Dropdown.Portal>
                        </Dropdown.Root>
                      </div>
                    ),
                  },
                ]}
              />
            </>
          ) : (
            <EmptyState
              title="Docker недоступен"
              description={
                data.error ||
                "Не удалось получить доступ к Docker daemon от имени пользователя SSH."
              }
            />
          ))}
      </SnapshotState>
      <Drawer
        open={logs !== null}
        onOpenChange={(open) => !open && setLogs(null)}
        title={`Журнал контейнера · ${logs || ""}`}
        description={`${server.name} · ${server.host}`}
        wide
      >
        {logs && <WorkloadLogs server={server} kind="docker" target={logs} />}
      </Drawer>
    </>
  );
}
const logLabels: Record<string, string> = {
  journal: "Системный журнал",
  service: "Журнал службы",
  syslog: "syslog",
  messages: "messages",
  auth: "Входы и авторизация",
  nginx_error: "nginx · ошибки",
  nginx_access: "nginx · запросы",
  apache_error: "Apache · ошибки",
  apache_access: "Apache · запросы",
  docker: "Docker",
};
function Logs({ server }: ServerProps) {
  const client = useQueryClient();
  const [source, setSource] = useState("journal");
  const [service, setService] = useState("");
  const [lines, setLines] = useState("120");
  const [params, setParams] = useState({
    source: "journal",
    service: "",
    lines: "120",
  });
  const query = useSnapshot(server, "logs", params);
  const data = query.data?.logs;
  const cachedPresets = client
    .getQueriesData<LinuxSnapshots["logs"]>({
      queryKey: ["server-operations", server.id, "logs"],
    })
    .map(([, snapshot]) => snapshot?.logs.presets)
    .find((items) => items?.length);
  const presets =
    data?.presets ||
    cachedPresets ||
    Object.entries(logLabels)
      .filter(([key]) => key !== "docker")
      .map(([key, label]) => ({ key, label, available: undefined }));
  const requested = {
    source,
    service: source === "service" ? service.trim() : "",
    lines,
  };
  const changed =
    requested.source !== params.source ||
    requested.service !== params.service ||
    requested.lines !== params.lines;
  return (
    <div className="stack">
      <form
        aria-busy={query.isFetching}
        onSubmit={(e) => {
          e.preventDefault();
          if (query.isFetching) return;
          if (changed) setParams(requested);
          else void query.refetch();
        }}
      >
        <fieldset
          className="ops-toolbar ops-log-filters"
          disabled={query.isFetching}
        >
          <Field label="Источник" htmlFor="ops-log-source">
            <select
              id="ops-log-source"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            >
              {presets.map((preset) => (
                <option key={preset.key} value={preset.key}>
                  {logLabels[preset.key] || preset.label}
                  {preset.available === false ? " · недоступен" : ""}
                </option>
              ))}
            </select>
          </Field>
          {source === "service" && (
            <Field label="Имя службы" htmlFor="ops-log-service">
              <input
                id="ops-log-service"
                value={service}
                onChange={(e) => setService(e.target.value)}
                required
                pattern="[A-Za-z0-9_.:@\-]+"
                placeholder="nginx.service"
              />
            </Field>
          )}
          <Field label="Строк" htmlFor="ops-log-lines">
            <select
              id="ops-log-lines"
              value={lines}
              onChange={(e) => setLines(e.target.value)}
            >
              {[40, 80, 120, 240].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </Field>
          <Button type="submit" loading={query.isFetching}>
            {changed ? "Показать" : query.error ? "Повторить" : "Обновить"}
          </Button>
        </fieldset>
      </form>
      {changed && (
        <p className="muted text-sm" role="status">
          Параметры изменены. Нажмите «Показать», чтобы загрузить выбранный
          журнал.
        </p>
      )}
      <SnapshotState
        loading={query.isPending}
        error={query.error}
        refresh={query.refetch}
        fetching={query.isFetching}
        timestamp={query.data?.observed_at}
        showRefresh={false}
      >
        {data && (
          <>
            <p className="muted text-sm">
              {logLabels[params.source] || params.source}
              {params.service ? ` · ${params.service}` : ""} · последние{" "}
              {params.lines} строк
            </p>
            {data.available === false ? (
              <div role="status" className="notice notice-warning">
                {data.unavailable_reason ||
                  "Источник журнала недоступен. Проверьте наличие журнала и права пользователя SSH или выберите другой источник."}
              </div>
            ) : (
              <pre className="code-block ops-log">
                {data.content || "Нет строк для отображения."}
              </pre>
            )}
            {data.available === false && data.content && (
              <details className="technical-details">
                <summary>Причина недоступности</summary>
                <pre className="code-block ops-log">{data.content}</pre>
              </details>
            )}
          </>
        )}
      </SnapshotState>
    </div>
  );
}
function Disk({ server }: ServerProps) {
  const query = useSnapshot(server, "disk");
  const data = query.data?.disk;
  return (
    <SnapshotState
      loading={query.isPending}
      error={query.error}
      refresh={query.refetch}
      fetching={query.isFetching}
      timestamp={query.data?.observed_at}
    >
      {data && (
        <>
          <DataTable
            rows={data.mounts}
            rowKey={(row) => `${row.filesystem}:${row.mount}`}
            hideSinglePagePagination
            defaultSort={{ key: "percent", desc: true }}
            columns={[
              {
                key: "mount",
                label: "Точка монтирования",
                render: (row) => <span className="mono">{row.mount}</span>,
              },
              {
                key: "filesystem",
                label: "Устройство",
                render: (row) => <span className="mono">{row.filesystem}</span>,
              },
              {
                key: "size",
                label: "Объём",
                render: (row) => num(row.size_gb, " ГБ"),
              },
              {
                key: "available",
                label: "Свободно",
                render: (row) => num(row.available_gb, " ГБ"),
              },
              {
                key: "percent",
                label: "Заполнено",
                render: (row) => (
                  <div className="ops-usage">
                    <progress
                      max={100}
                      value={row.percent ?? 0}
                      aria-label={`Заполнение ${row.mount}`}
                    />
                    <span>{num(row.percent, "%")}</span>
                  </div>
                ),
                sortValue: (row) => row.percent ?? -1,
              },
            ]}
          />
          <div className="ops-columns">
            {[
              { title: "Крупные каталоги", rows: data.top_directories },
              { title: "Крупные журналы", rows: data.large_logs },
            ].map((group) => (
              <Panel key={group.title} title={group.title}>
                <DataTable
                  rows={group.rows}
                  rowKey={(row) => row.path}
                  hideSinglePagePagination
                  defaultSort={{ key: "size", desc: true }}
                  emptyTitle="Нет доступных данных"
                  columns={[
                    {
                      key: "path",
                      label: "Путь",
                      render: (row) => (
                        <span className="mono text-sm">{row.path}</span>
                      ),
                    },
                    {
                      key: "size",
                      label: "Размер",
                      render: (row) => num(row.size_mb, " МБ"),
                      sortValue: (row) => row.size_mb ?? -1,
                    },
                  ]}
                />
              </Panel>
            ))}
          </div>
          {data.cleanup_candidates.length > 0 && (
            <details className="technical-details">
              <summary>
                Старые элементы /tmp · {data.cleanup_candidates.length}
              </summary>
              <p className="muted text-sm">
                Элементы старше 7 дней. Перед очисткой проверьте их назначение в
                файловом менеджере.
              </p>
              <pre className="code-block">
                {data.cleanup_candidates.join("\n")}
              </pre>
            </details>
          )}
        </>
      )}
    </SnapshotState>
  );
}
function Network({ server }: ServerProps) {
  const query = useSnapshot(server, "network");
  const data = query.data?.network;
  return (
    <SnapshotState
      loading={query.isPending}
      error={query.error}
      refresh={query.refetch}
      fetching={query.isFetching}
      timestamp={query.data?.observed_at}
    >
      {data && (
        <>
          <DataTable
            rows={data.interfaces}
            rowKey={(row) => row.name}
            hideSinglePagePagination
            emptyTitle="Интерфейсы не получены"
            emptyDescription={
              data.tools.ip ? undefined : "Утилита ip недоступна."
            }
            columns={[
              {
                key: "name",
                label: "Интерфейс",
                render: (row) => <strong className="mono">{row.name}</strong>,
              },
              {
                key: "state",
                label: "Состояние",
                render: (row) => (
                  <StatusBadge
                    status={
                      row.state === "UP"
                        ? "healthy"
                        : row.state === "DOWN"
                          ? "offline"
                          : "unknown"
                    }
                  >
                    {row.state}
                  </StatusBadge>
                ),
              },
              {
                key: "addresses",
                label: "Адреса",
                render: (row) => (
                  <div className="mono text-sm">
                    {row.addresses.map((address) => (
                      <div key={`${address.family}:${address.address}`}>
                        {address.address}{" "}
                        <span className="muted">{address.scope}</span>
                      </div>
                    ))}
                  </div>
                ),
              },
              {
                key: "mac",
                label: "MAC / MTU",
                render: (row) => (
                  <div className="mono text-sm">
                    {row.mac || "—"}
                    <div className="muted">MTU {row.mtu ?? "—"}</div>
                  </div>
                ),
              },
            ]}
          />
          <Panel title="Слушающие порты">
            <DataTable
              rows={data.listening}
              hideSinglePagePagination
              rowKey={(row) =>
                `${row.protocol}:${row.local_address}:${row.process}`
              }
              emptyTitle="Сокеты не получены"
              emptyDescription={
                data.tools.ss ? undefined : "Утилита ss недоступна."
              }
              columns={[
                {
                  key: "protocol",
                  label: "Протокол",
                  render: (row) => row.protocol,
                },
                {
                  key: "local",
                  label: "Локальный адрес",
                  render: (row) => (
                    <span className="mono">{row.local_address}</span>
                  ),
                },
                {
                  key: "peer",
                  label: "Удалённый адрес",
                  render: (row) => (
                    <span className="mono">{row.peer_address}</span>
                  ),
                },
                {
                  key: "process",
                  label: "Процесс",
                  render: (row) => (
                    <span className="mono text-sm">{row.process || "—"}</span>
                  ),
                },
              ]}
            />
          </Panel>
          <details className="technical-details">
            <summary>Таблица маршрутизации</summary>
            <pre className="code-block">
              {data.routes.join("\n") || "Маршруты не получены."}
            </pre>
          </details>
        </>
      )}
    </SnapshotState>
  );
}
function Packages({ server }: ServerProps) {
  const query = useSnapshot(server, "packages");
  const data = query.data?.packages;
  return (
    <SnapshotState
      loading={query.isPending}
      error={query.error}
      refresh={query.refetch}
      fetching={query.isFetching}
      timestamp={query.data?.observed_at}
    >
      {data && (
        <>
          <p className="muted text-sm">
            Пакетный менеджер: {data.package_manager || "не определён"}.
            Показаны версии распространённых серверных пакетов, а не полный
            список установленного ПО.
          </p>
          <DataTable
            rows={data.installed}
            searchValue={(row) => `${row.name} ${row.version}`}
            searchPlaceholder="Название или версия пакета…"
            hideSinglePagePagination
            rowKey={(row) => row.name}
            emptyTitle="Основные пакеты не найдены"
            columns={[
              {
                key: "name",
                label: "Пакет",
                render: (row) => <span className="mono">{row.name}</span>,
                sortValue: (row) => row.name,
              },
              {
                key: "version",
                label: "Версия",
                render: (row) => <span className="mono">{row.version}</span>,
              },
            ]}
          />
          <details className="technical-details">
            <summary>
              Доступные обновления · {data.updates.length} в выборке
            </summary>
            <p className="muted text-sm">
              Первые 15 записей по данным пакетного менеджера на момент снимка.
            </p>
            <pre className="code-block ops-log">
              {data.updates.join("\n") ||
                "Доступные обновления не обнаружены в текущей выборке."}
            </pre>
          </details>
        </>
      )}
    </SnapshotState>
  );
}
function Configuration({ server }: ServerProps) {
  const query = useSnapshot(server, "settings");
  const data = query.data?.settings;
  return (
    <SnapshotState
      loading={query.isPending}
      error={query.error}
      refresh={query.refetch}
      fetching={query.isFetching}
      timestamp={query.data?.observed_at}
    >
      {data && (
        <>
          <dl className="ops-facts">
            {[
              ["Имя узла", data.general.hostname],
              ["Часовой пояс", data.general.timezone],
              ["Архитектура", data.general.architecture],
              ["Процессор", data.general.cpu],
              ["Память", data.general.total_memory],
              ["Время работы", data.general.uptime],
            ].map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value || "—"}</dd>
              </div>
            ))}
          </dl>
          <Panel title="Учётные записи Linux">
            <DataTable
              rows={data.users.accounts}
              rowKey={(row) => row.uid}
              hideSinglePagePagination
              columns={[
                {
                  key: "name",
                  label: "Пользователь",
                  render: (row) => row.name,
                },
                { key: "uid", label: "UID", render: (row) => row.uid },
                {
                  key: "home",
                  label: "Домашний каталог",
                  render: (row) => <span className="mono">{row.home}</span>,
                },
                {
                  key: "shell",
                  label: "Оболочка",
                  render: (row) => <span className="mono">{row.shell}</span>,
                },
              ]}
            />
          </Panel>
          <p className="muted text-sm">
            Дополнительные сведения показаны, если сервер вернул их пользователю
            SSH.
          </p>
          {[
            ["Активные сеансы", data.users.logged_in],
            ["Последние входы", data.users.last_logins],
            ["Группа sudo", data.users.sudo_group],
            ["SSH", data.security.ssh_config],
            ["Межсетевой экран", data.security.firewall],
            ["Неудачные входы", data.security.failed_logins],
            ["Crontab пользователя", data.crontab.user_crontab],
            ["Системный crontab", data.crontab.system_crontab],
            ["Каталог cron.d", data.crontab.cron_dirs],
            ["Таймеры systemd", data.crontab.timers],
            [
              "Пути поиска команд",
              data.environment.path_directories.join("\n"),
            ],
          ]
            .filter(([, content]) => content?.trim())
            .map(([label, content]) => (
              <details className="technical-details" key={label}>
                <summary>{label}</summary>
                <pre className="code-block ops-log">
                  {content === "No crontab for current user"
                    ? "У пользователя нет заданий cron."
                    : content === "No /etc/crontab"
                      ? "Системный crontab отсутствует."
                      : content}
                </pre>
              </details>
            ))}
        </>
      )}
    </SnapshotState>
  );
}

export function ServerOperations({ server }: ServerProps) {
  const { user } = useSession();
  const client = useQueryClient();
  const allowed =
    !!user?.is_staff &&
    !!user.features.servers &&
    !!server.capabilities.connect_terminal &&
    server.server_type === "ssh";
  const capabilities = useQuery({
    queryKey: ["server-operations", server.id, "capabilities"],
    queryFn: ({ signal }) =>
      serverOperationsApi.snapshot(server.id, "capabilities", {}, signal),
    enabled: allowed,
    staleTime: 60_000,
    retry: false,
  });
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("system") || "overview";
  function setTab(value: string) {
    if (action.isPending) return;
    action.reset();
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      if (value === "overview") next.delete("system");
      else next.set("system", value);
      return next;
    });
  }
  const [pending, setPending] = useState<OperationAction | null>(null);
  const action = useMutation({
    mutationKey: ["server-workspace", server.id],
    mutationFn: (input: LinuxAction) =>
      serverOperationsApi.action(server.id, input),
    onSuccess: () => setPending(null),
    onSettled: () => {
      void client.invalidateQueries({
        queryKey: ["server-operations", server.id],
      });
    },
  });
  const blocker = useUnsavedEditsBlocker(action.isPending);
  const resultEnvelope =
    action.data ||
    (action.error instanceof ApiError
      ? (action.error.details as {
          service_action?: LinuxActionResult;
          process_action?: LinuxActionResult;
          docker_action?: LinuxActionResult;
        })
      : null);
  const result =
    resultEnvelope?.service_action ||
    resultEnvelope?.process_action ||
    resultEnvelope?.docker_action;
  const operationError =
    action.error &&
    /permission denied|operation not permitted/i.test(result?.output || "")
      ? new Error("У пользователя SSH недостаточно прав на эту операцию.")
      : action.error;
  const requestAction: RequestAction = (input) => {
    if (action.isPending) return;
    action.reset();
    setPending(input);
  };
  if (!allowed)
    return (
      <EmptyState
        icon={<ShieldCheck size={24} />}
        title="Linux-операции недоступны"
        description={
          !user?.is_staff
            ? "Раздел доступен администраторам платформы."
            : server.server_type !== "ssh"
              ? "Раздел доступен для серверов SSH."
              : "Требуется разрешение на подключение к терминалу этого сервера."
        }
      />
    );
  if (capabilities.isPending)
    return <LoadingState label="Определяем возможности сервера…" />;
  if (
    capabilities.error &&
    (!capabilities.data ||
      (capabilities.error instanceof ApiError &&
        [401, 403].includes(capabilities.error.status)))
  )
    return (
      <ErrorState
        error={capabilities.error}
        retry={() => void capabilities.refetch()}
      />
    );
  const apps = capabilities.data?.capabilities.available_apps || {};
  const currentAvailable = tab === "logs" || !!apps[tab];
  const primaryTabs = [
    { value: "overview", label: "Состояние" },
    { value: "processes", label: "Процессы" },
    { value: "services", label: "Службы" },
    { value: "docker", label: "Docker" },
    { value: "logs", label: "Журналы" },
  ].filter((item) => item.value === "logs" || apps[item.value]);
  const moreTabs = [
    { value: "disk", label: "Диски" },
    { value: "network", label: "Сеть" },
    { value: "packages", label: "Пакеты" },
    { value: "settings", label: "Сведения о системе" },
  ].filter((item) => apps[item.value]);
  return (
    <Panel
      title="Система"
      description={`${capabilities.data?.capabilities.os_name || "Linux"} · ${capabilities.data?.capabilities.hostname || server.host}`}
    >
      {capabilities.error && (
        <div role="alert" className="notice notice-warning section-body">
          Не удалось обновить доступные разделы. Показаны последние полученные
          возможности сервера. {capabilities.error.message}
        </div>
      )}
      <div className="row spread section-body">
        <Tabs
          value={tab}
          onChange={setTab}
          disabled={action.isPending}
          items={primaryTabs}
        />
        <Dropdown.Root>
          <Dropdown.Trigger asChild>
            <Button
              variant="ghost"
              aria-label="Ещё о системе"
              disabled={action.isPending || capabilities.isFetching}
            >
              {moreTabs.find((item) => item.value === tab)?.label || "Ещё"}
              <ChevronDown size={14} />
            </Button>
          </Dropdown.Trigger>
          <Dropdown.Portal>
            <Dropdown.Content className="menu-content" align="end">
              {moreTabs.map((item) => (
                <Dropdown.Item
                  key={item.value}
                  className="menu-item"
                  onSelect={() => setTab(item.value)}
                >
                  {item.label}
                </Dropdown.Item>
              ))}
              <Dropdown.Separator className="menu-separator" />
              <Dropdown.Item
                className="menu-item"
                onSelect={() => void capabilities.refetch()}
              >
                Обновить доступные разделы
              </Dropdown.Item>
            </Dropdown.Content>
          </Dropdown.Portal>
        </Dropdown.Root>
      </div>
      <div className="section-body stack">
        {!server.capabilities.execute_command && (
          <p className="notice">
            Просмотр состояния. Для управления требуется разрешение на
            выполнение команд.
          </p>
        )}
        {!currentAvailable ? (
          <EmptyState
            title="Возможность недоступна на сервере"
            description="Необходимая системная утилита не обнаружена. Обновите возможности после установки или изменения прав пользователя SSH."
            action={
              <Button onClick={() => setTab("overview")}>
                К состоянию сервера
              </Button>
            }
          />
        ) : (
          <>
            {tab === "overview" && <Overview server={server} />}
            {tab === "services" && (
              <Services server={server} onAction={requestAction} />
            )}
            {tab === "processes" && (
              <Processes server={server} onAction={requestAction} />
            )}
            {tab === "docker" && (
              <Docker server={server} onAction={requestAction} />
            )}
            {tab === "logs" && <Logs server={server} />}
            {tab === "disk" && <Disk server={server} />}
            {tab === "network" && <Network server={server} />}
            {tab === "packages" && <Packages server={server} />}
            {tab === "settings" && <Configuration server={server} />}
          </>
        )}
        <Feedback
          error={operationError}
          success={
            action.isSuccess
              ? result?.still_running
                ? "Сигнал отправлен. Обновите список, чтобы проверить завершение."
                : "Операция выполнена."
              : undefined
          }
        />
        {result && (
          <details className="technical-details">
            <summary>Подробности операции</summary>
            <div className="row">
              <StatusBadge status={result.success ? "success" : "error"} />
              {result.still_running === true && (
                <span className="muted text-sm">
                  На момент проверки процесс ещё не завершился.
                </span>
              )}
            </div>
            <pre className="code-block ops-log">
              {result.output ||
                result.status_excerpt ||
                result.process_excerpt ||
                result.inspect_excerpt ||
                "Операция завершена без вывода."}
            </pre>
          </details>
        )}
      </div>
      <ConfirmDialog
        key={
          pending
            ? `${pending.kind}:${pending.target}:${pending.action}`
            : "idle"
        }
        open={pending !== null}
        onOpenChange={(open) => !open && !action.isPending && setPending(null)}
        title={
          pending
            ? `${actionLabels[pending.action]} · ${pending.target}`
            : "Подтверждение операции"
        }
        description={
          <>
            <p>
              Сервер: <strong>{server.name}</strong> ·{" "}
              <span className="mono">
                {server.username}@{server.host}:{server.port}
              </span>
            </p>
            <p>
              {pending?.description && (
                <span className="mono">{pending.description}</span>
              )}
            </p>
            <p>
              {pending?.kind === "processes"
                ? pending.action === "kill_force"
                  ? "Будет отправлен SIGKILL. Процесс не сможет завершить работу с сохранением данных."
                  : "Будет отправлен SIGTERM выбранному PID."
                : pending?.action === "stop" || pending?.action === "restart"
                  ? "Операция прервёт работу выбранной службы или контейнера и может повлиять на связанные приложения."
                  : "Будет выполнено выбранное действие с сохранением события в аудите."}
            </p>
            <Feedback error={operationError} />
            {action.error && result?.output && (
              <details className="technical-details">
                <summary>Ответ сервера</summary>
                <pre className="code-block ops-log">{result.output}</pre>
              </details>
            )}
          </>
        }
        onConfirm={() => pending && !action.isPending && action.mutate(pending)}
        pending={action.isPending}
        confirmLabel={pending ? actionLabels[pending.action] : "Выполнить"}
        typedText={
          pending &&
          (pending.action === "kill_force" || pending.action === "stop")
            ? String(pending.target)
            : undefined
        }
      />
      <ConfirmDialog
        open={blocker.state === "blocked"}
        title="Операция выполняется"
        description="Дождитесь результата перед переходом на другую страницу."
        onOpenChange={() => {
          if (blocker.state === "blocked") blocker.reset();
        }}
        confirmLabel="Остаться"
        onConfirm={() => {
          if (blocker.state === "blocked") blocker.reset();
        }}
      />
    </Panel>
  );
}
