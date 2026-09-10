import { lazy, Suspense, useEffect, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, RefreshCw, Square, Play } from "lucide-react";
import { api, ApiError } from "@/api/client";
import {
  automationApi,
  playbookBase,
  studioBase,
  type HostResult,
  type PipelineRun,
  type RunSummary,
  type Values,
} from "@/api/automation";
import { usePermission } from "@/app/session";
import { RealtimeConnection, type ConnectionState } from "@/realtime/socket";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
  EmptyState,
  ErrorState,
  Feedback,
  Field,
  Metric,
  PageHeader,
  Panel,
  Skeleton,
  StatusBadge,
  Tabs,
} from "@/components/ui";
import { formatDate } from "@/lib/utils";
import { activeRun, duration, KeyValues } from "./shared";
const RunCanvas = lazy(() => import("./RunCanvas"));

interface History {
  items: RunSummary[];
  page: { next_cursor: number | null; has_more: boolean; limit: number };
}
export function RunHistory() {
  const canPlaybooks = usePermission("automation");
  const canPipelines = usePermission("studio_runs");
  const [params] = useSearchParams();
  const [tab, setTab] = useState(
    params.has("pipeline")
      ? "pipeline"
      : canPlaybooks
        ? "playbook"
        : "pipeline",
  );
  const [status, setStatus] = useState("");
  const [cursor, setCursor] = useState(0);
  const [prior, setPrior] = useState<number[]>([]);
  const pbId = params.get("playbook") || "";
  const pipelineId = params.get("pipeline");
  const history = useQuery({
    queryKey: ["automation", "history", status, cursor, pbId],
    queryFn: ({ signal }) =>
      api.get<History>(
        `${playbookBase}runs/history/?limit=25&cursor=${cursor}&status=${encodeURIComponent(status)}&playbook_id=${pbId}`,
        signal,
      ),
    enabled: tab === "playbook" && canPlaybooks,
    refetchInterval: (q) =>
      q.state.data?.items.some((r) => activeRun(r.status)) ? 10000 : false,
  });
  const pipelines = useQuery({
    queryKey: ["automation", "pipeline-runs"],
    queryFn: ({ signal }) => automationApi.pipelineRuns(signal),
    enabled: tab === "pipeline" && canPipelines,
    refetchInterval: (q) =>
      q.state.data?.some((r) => activeRun(r.status)) ? 10000 : false,
  });
  return (
    <>
      <PageHeader
        eyebrow="Автоматизация"
        title="История выполнения"
        description="Результаты операций, ошибки и контроль активных запусков."
      />
      <Tabs
        value={tab}
        onChange={(v) => {
          setTab(v);
          setStatus("");
        }}
        items={[
          ...(canPlaybooks ? [{ value: "playbook", label: "Плейбуки" }] : []),
          ...(canPipelines
            ? [
                { value: "pipeline", label: "Рабочие процессы" },
                { value: "dead", label: "Требуют разбора" },
              ]
            : []),
        ]}
      />
      {tab === "dead" ? (
        <DeadLetters />
      ) : tab === "playbook" ? (
        <Panel>
          {history.isPending ? (
            <Skeleton />
          ) : history.error ? (
            <ErrorState
              error={history.error}
              retry={() => void history.refetch()}
            />
          ) : (
            <>
              <DataTable
                rows={history.data?.items ?? []}
                rowKey={(r) => r.id}
                searchValue={(r) => `${r.playbook_name} ${r.id}`}
                pageSize={25}
                emptyTitle="Запусков пока нет"
                emptyDescription="После выполнения плейбука здесь появится отчёт по каждому серверу."
                toolbar={
                  <select
                    aria-label="Статус запуска"
                    value={status}
                    onChange={(e) => {
                      setStatus(e.target.value);
                      setCursor(0);
                      setPrior([]);
                    }}
                  >
                    <option value="">Все статусы</option>
                    {[
                      "pending",
                      "running",
                      "completed",
                      "failed",
                      "partial",
                      "cancelled",
                    ].map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                }
                columns={[
                  {
                    key: "id",
                    label: "Запуск",
                    render: (r) => (
                      <div className="auto-row-title">
                        <Link to={`/automation/runs/playbook/${r.id}`}>
                          {r.playbook_name}
                        </Link>
                        <small>#{r.id}</small>
                      </div>
                    ),
                  },
                  {
                    key: "status",
                    label: "Статус",
                    render: (r) => <StatusBadge status={r.status} />,
                  },
                  {
                    key: "progress",
                    label: "Ход выполнения",
                    render: (r) =>
                      r.progress_percent != null
                        ? `${Math.round(r.progress_percent)}%`
                        : r.phase || "—",
                  },
                  {
                    key: "created",
                    label: "Начало",
                    render: (r) => formatDate(r.started_at || r.created_at),
                  },
                  {
                    key: "finished",
                    label: "Окончание",
                    render: (r) => formatDate(r.finished_at),
                  },
                ]}
              />
              <div className="auto-action-strip">
                <Button
                  size="sm"
                  disabled={!prior.length}
                  onClick={() => {
                    setCursor(prior.at(-1) ?? 0);
                    setPrior(prior.slice(0, -1));
                  }}
                >
                  Более новые
                </Button>
                <Button
                  size="sm"
                  disabled={!history.data?.page.has_more}
                  onClick={() => {
                    setPrior([...prior, cursor]);
                    setCursor(history.data?.page.next_cursor ?? 0);
                  }}
                >
                  Более ранние
                </Button>
              </div>
            </>
          )}
        </Panel>
      ) : (
        <Panel>
          {pipelines.isPending ? (
            <Skeleton />
          ) : pipelines.error ? (
            <ErrorState
              error={pipelines.error}
              retry={() => void pipelines.refetch()}
            />
          ) : (
            <DataTable
              rows={(pipelines.data ?? []).filter(
                (r) => !pipelineId || r.pipeline_id === Number(pipelineId),
              )}
              rowKey={(r) => r.id}
              searchValue={(r) => `${r.pipeline_name} ${r.id}`}
              emptyTitle="Процессы ещё не запускались"
              columns={[
                {
                  key: "name",
                  label: "Процесс",
                  render: (r) => (
                    <div className="auto-row-title">
                      <Link to={`/automation/runs/pipeline/${r.id}`}>
                        {r.pipeline_name}
                      </Link>
                      <small>
                        #{r.id} · {r.trigger_type}
                      </small>
                    </div>
                  ),
                },
                {
                  key: "status",
                  label: "Статус",
                  render: (r) => <StatusBadge status={r.status} />,
                },
                {
                  key: "duration",
                  label: "Длительность",
                  render: (r) => duration(r.duration_seconds),
                },
                {
                  key: "start",
                  label: "Начало",
                  render: (r) => formatDate(r.started_at || r.created_at),
                },
                {
                  key: "end",
                  label: "Окончание",
                  render: (r) => formatDate(r.finished_at),
                },
              ]}
            />
          )}
        </Panel>
      )}
    </>
  );
}
export function PlaybookRunDetail() {
  const { id } = useParams();
  const runId = Number(id);
  const report = useQuery({
    queryKey: ["automation", "run-report", runId],
    queryFn: ({ signal }) => automationApi.report(runId, signal),
    refetchInterval: (q) =>
      activeRun(q.state.data?.report.run.status) ? 3000 : false,
    refetchIntervalInBackground: false,
  });
  const [cancel, setCancel] = useState(false);
  const [retry, setRetry] = useState(false);
  const [selectedHost, setSelectedHost] = useState<number | null>(null);
  const mutation = useMutation({
    mutationFn: () => api.post(`${playbookBase}runs/${runId}/cancel/`),
    onSuccess: () => {
      setCancel(false);
      void report.refetch();
    },
  });
  if (report.isPending) return <Skeleton />;
  if (report.error)
    return (
      <ErrorState error={report.error} retry={() => void report.refetch()} />
    );
  const data = report.data!.report;
  const run = data.run;
  return (
    <>
      <PageHeader
        eyebrow={`Автоматизация / Запуск #${run.id}`}
        title={run.playbook_name}
        description={
          <>
            <StatusBadge status={run.status} /> · {formatDate(run.created_at)}
          </>
        }
        actions={
          <>
            <Link className="btn btn-ghost" to="/automation/runs">
              История
            </Link>
            {data.actions.can_export && (
              <a
                className="btn btn-secondary"
                href={data.actions.export_url}
                download
              >
                <Download size={14} />
                Скачать отчёт
              </a>
            )}
            {data.actions.can_retry_failed && (
              <Button onClick={() => setRetry(true)}>
                <RefreshCw size={14} />
                Повторить ошибки
              </Button>
            )}
            {data.actions.can_cancel && (
              <Button variant="danger" onClick={() => setCancel(true)}>
                <Square size={13} />
                Остановить
              </Button>
            )}
          </>
        }
      />
      <Feedback error={mutation.error} />
      <div className="metrics-strip">
        <Metric label="Целевых серверов" value={run.target_count} />
        <Metric
          label="Длительность"
          value={duration(
            run.duration_ms == null ? null : run.duration_ms / 1000,
          )}
        />
        <Metric
          label="Выполнение"
          value={
            data.progress.percent == null
              ? "—"
              : `${Math.round(data.progress.percent)}%`
          }
          detail={
            data.progress.total_kind === "estimated"
              ? "Общее число задач оценивается"
              : data.progress.phase
          }
        />
        <Metric
          label="Версия"
          value={run.revision_id ? `#${run.revision_id}` : "—"}
          detail={run.binding_profile_name}
        />
      </div>
      {data.failure && (
        <div className="notice notice-danger">
          <div>
            <strong>{data.failure.message}</strong>
            {data.failure.suggested_action && (
              <p>{data.failure.suggested_action}</p>
            )}
          </div>
        </div>
      )}
      <div className="auto-stack">
        <Panel title="Результаты по серверам">
          <DataTable
            rows={data.hosts}
            rowKey={(r) => r.server_id}
            emptyTitle={
              activeRun(run.status)
                ? "Ожидаем результаты хостов"
                : "Результатов хостов нет"
            }
            columns={[
              {
                key: "server",
                label: "Сервер",
                render: (r) => (
                  <Button
                    variant="ghost"
                    onClick={() => setSelectedHost(r.server_id)}
                  >
                    {r.server_name}
                  </Button>
                ),
              },
              {
                key: "status",
                label: "Результат",
                render: (r) => <StatusBadge status={r.status} />,
              },
              {
                key: "tasks",
                label: "Задачи",
                render: (r) =>
                  r.task_counts
                    ? `${r.task_counts.ok ?? 0} успешных · ${r.task_counts.failed ?? 0} ошибок · ${r.task_counts.changed ?? 0} изменений`
                    : "—",
              },
              {
                key: "detail",
                label: "Подробности",
                render: (r) => (
                  <Button
                    size="sm"
                    onClick={() => setSelectedHost(r.server_id)}
                  >
                    Открыть задачи
                  </Button>
                ),
              },
            ]}
          />
        </Panel>
        <RunLog key={runId} runId={runId} active={activeRun(run.status)} />
      </div>
      <Drawer
        open={selectedHost !== null}
        onOpenChange={(v) => !v && setSelectedHost(null)}
        title="Задачи сервера"
        wide
      >
        {selectedHost !== null && (
          <HostTasks runId={runId} hostId={selectedHost} />
        )}
      </Drawer>
      <Drawer
        open={retry}
        onOpenChange={setRetry}
        title="Повторить неуспешные хосты"
      >
        {retry && <RetryPlaybook runId={runId} />}
      </Drawer>
      <ConfirmDialog
        open={cancel}
        onOpenChange={setCancel}
        title="Остановить запуск?"
        description="Будет отправлен запрос на остановку. Уже выполненные изменения не отменяются."
        confirmLabel="Остановить"
        onConfirm={() => mutation.mutate()}
        pending={mutation.isPending}
      />
    </>
  );
}
function RunLog({ runId, active }: { runId: number; active: boolean }) {
  const [text, setText] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [truncated, setTruncated] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cursor = 0;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    const poll = async () => {
      if (disposed) return;
      if (document.hidden) {
        if (active) timer = setTimeout(() => void poll(), 4000);
        return;
      }
      try {
        const data = await automationApi.log(runId, cursor, controller.signal);
        if (disposed) return;
        setText((old) =>
          (data.reset_required || cursor === 0
            ? data.text
            : old + data.text
          ).slice(-120000),
        );
        setTruncated(data.truncated);
        setError(null);
        cursor = data.next_cursor;
        if (data.has_more || active)
          timer = setTimeout(() => void poll(), data.has_more ? 100 : 3000);
      } catch (err) {
        if (disposed) return;
        setError(err);
      }
    };
    void poll();
    return () => {
      disposed = true;
      controller.abort();
      clearTimeout(timer);
    };
  }, [runId, active, attempt]);
  return (
    <Panel
      title="Журнал выполнения"
      actions={
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setAttempt((v) => v + 1)}
        >
          <RefreshCw size={13} />
          Обновить
        </Button>
      }
    >
      {error ? (
        <ErrorState error={error} />
      ) : (
        <pre className="auto-log" aria-label="Журнал выполнения">
          {text || "Журнал пока пуст."}
        </pre>
      )}
      {truncated && (
        <p className="auto-empty-note">
          Показана доступная часть журнала. Старые строки удалены политикой
          хранения.
        </p>
      )}
    </Panel>
  );
}
function HostTasks({ runId, hostId }: { runId: number; hostId: number }) {
  const query = useQuery({
    queryKey: ["automation", "run-host", runId, hostId],
    queryFn: ({ signal }) =>
      api.get<{ host: HostResult }>(
        `${playbookBase}runs/${runId}/hosts/${hostId}/`,
        signal,
      ),
  });
  return query.isPending ? (
    <Skeleton />
  ) : query.error ? (
    <ErrorState error={query.error} />
  ) : (
    <div>
      <h3>{query.data?.host.server_name}</h3>
      {query.data?.host.tasks?.map((task, index) => (
        <div className="auto-task" key={`${task.task_id}-${index}`}>
          <div className="auto-task-head">
            <strong>{task.name}</strong>
            <StatusBadge status={task.status} />
          </div>
          <small className="muted">
            Код завершения: {task.exit_code ?? "—"}
          </small>
          <pre className="auto-source">{task.output || "Нет вывода"}</pre>
        </div>
      ))}
    </div>
  );
}
function RetryPlaybook({ runId }: { runId: number }) {
  const context = useQuery({
    queryKey: ["automation", "retry-context", runId],
    queryFn: ({ signal }) =>
      api.get<{
        retry_context: {
          can_retry: boolean;
          failed_server_ids: number[];
          required_variable_names: string[];
        };
      }>(`${playbookBase}runs/${runId}/retry-context/`, signal),
  });
  const [vars, setVars] = useState<Values>({});
  const [password, setPassword] = useState("");
  const navigate = useNavigate();
  const mutation = useMutation({
    mutationFn: () =>
      api.post<{ run: RunSummary }>(
        `${playbookBase}runs/${runId}/rerun-failed/`,
        { extra_vars: vars, master_password: password || undefined },
      ),
    onSuccess: (data) => {
      setPassword("");
      navigate(`/automation/runs/playbook/${data.run.id}`);
    },
  });
  return (
    <div className="auto-form">
      {context.isPending ? (
        <Skeleton />
      ) : context.error ? (
        <ErrorState error={context.error} />
      ) : (
        <>
          <p>
            Неуспешных серверов:{" "}
            {context.data?.retry_context.failed_server_ids.length}. Будет
            использована исходная версия плейбука.
          </p>
          {!!context.data?.retry_context.required_variable_names.length && (
            <p className="notice notice-info">
              Укажите заново:{" "}
              {context.data.retry_context.required_variable_names.join(", ")}
            </p>
          )}
          <KeyValues value={vars} onChange={setVars} />
          <Field
            label="Мастер-пароль (если требуется)"
            htmlFor="retry-password"
          >
            <input
              id="retry-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <Feedback error={mutation.error} />
          <Button
            variant="primary"
            disabled={!context.data?.retry_context.can_retry}
            loading={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            Проверить и повторить неуспешные хосты
          </Button>
        </>
      )}
    </div>
  );
}
export function PipelineRunDetail() {
  const { id } = useParams();
  const runId = Number(id);
  const query = useQuery({
    queryKey: ["automation", "pipeline-run", runId],
    queryFn: ({ signal }) => automationApi.pipelineRun(runId, signal),
    refetchInterval: (q) => (activeRun(q.state.data?.status) ? 7000 : false),
    refetchIntervalInBackground: false,
  });
  const client = useQueryClient();
  const [connection, setConnection] = useState<ConnectionState>("disconnected");
  const [selected, setSelected] = useState<string | null>(null);
  const [stop, setStop] = useState(false);
  const [resume, setResume] = useState(false);
  const [resumeNodes, setResumeNodes] = useState<
    { node_id?: string; id?: string; node_type?: string }[]
  >([]);
  const status = query.data?.status;
  useEffect(() => {
    if (!activeRun(status)) return;
    const realtime = new RealtimeConnection<{
      type: string;
      node_id?: string;
      state?: PipelineRun["node_states"][string];
      status?: string;
    }>({
      path: `/ws/studio/pipeline-runs/${runId}/live/`,
      onState: setConnection,
      onOpen: () => {
        void client.invalidateQueries({
          queryKey: ["automation", "pipeline-run", runId],
        });
      },
      onMessage: (event) => {
        if (
          (event.type === "pipeline.node.state" ||
            event.type === "node_state") &&
          event.node_id &&
          event.state
        )
          client.setQueryData<PipelineRun>(
            ["automation", "pipeline-run", runId],
            (old) =>
              old
                ? {
                    ...old,
                    node_states: {
                      ...old.node_states,
                      [event.node_id!]: event.state!,
                    },
                  }
                : old,
          );
        else if (
          event.type === "pipeline.status" ||
          event.type === "run_status"
        ) {
          void client.invalidateQueries({
            queryKey: ["automation", "pipeline-run", runId],
          });
        }
      },
    });
    realtime.connect();
    return () => realtime.close();
  }, [runId, status, client]);
  const stopRun = useMutation({
    mutationFn: () => api.post(`${studioBase}runs/${runId}/stop/`),
    onSuccess: () => {
      setStop(false);
      void query.refetch();
    },
  });
  const resumeRun = useMutation({
    mutationFn: (confirmed: boolean) =>
      api.post(`${studioBase}runs/${runId}/resume/`, {
        confirm_non_idempotent: confirmed,
      }),
    onSuccess: () => {
      setResume(false);
      void query.refetch();
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        const data = error.details as {
          code?: string;
          nodes?: typeof resumeNodes;
        };
        if (data.code === "resume_confirmation_required") {
          setResumeNodes(data.nodes ?? []);
          setResume(true);
        }
      }
    },
  });
  if (query.isPending) return <Skeleton />;
  if (query.error)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  const run = query.data!;
  const nodeId = selected ?? (run.entry_node_id || run.nodes_snapshot[0]?.id);
  const state = nodeId ? run.node_states[nodeId] : undefined;
  const node = run.nodes_snapshot.find((item) => item.id === nodeId);
  return (
    <>
      <PageHeader
        eyebrow={`Автоматизация / Запуск #${run.id}`}
        title={run.pipeline_name}
        description={
          <>
            <StatusBadge status={run.status} /> · {formatDate(run.created_at)}
            {activeRun(run.status) && (
              <>
                {" "}
                ·{" "}
                <StatusBadge status={connection}>
                  {connection === "connected"
                    ? "Обновляется в реальном времени"
                    : "Обновляется по HTTP"}
                </StatusBadge>
              </>
            )}
          </>
        }
        actions={
          <>
            <Link
              className="btn btn-ghost"
              to={`/automation/pipelines/${run.pipeline_id}`}
            >
              Открыть процесс
            </Link>
            {run.can_resume && (
              <Button
                loading={resumeRun.isPending}
                onClick={() => resumeRun.mutate(false)}
              >
                <Play size={14} />
                Возобновить
              </Button>
            )}
            {activeRun(run.status) && (
              <Button variant="danger" onClick={() => setStop(true)}>
                <Square size={14} />
                Остановить
              </Button>
            )}
          </>
        }
      />
      <Feedback error={stopRun.error || (!resume ? resumeRun.error : null)} />
      {run.error && <div className="notice notice-danger">{run.error}</div>}
      <div className="metrics-strip">
        <Metric label="Шагов" value={run.nodes_snapshot.length} />
        <Metric
          label="Завершено"
          value={
            Object.values(run.node_states).filter((n) =>
              ["completed", "success"].includes(n.status),
            ).length
          }
        />
        <Metric label="Длительность" value={duration(run.duration_seconds)} />
        <Metric
          label="Триггер"
          value={run.trigger_type}
          detail={run.entry_node_id}
        />
      </div>
      <div className="auto-run-graph-layout">
        <Panel
          title="Схема запуска"
          description="Выберите шаг, чтобы увидеть его результат. Схема сохранена на момент запуска."
        >
          <Suspense fallback={<Skeleton />}>
            <RunCanvas run={run} selected={nodeId} onSelect={setSelected} />
          </Suspense>
        </Panel>
        <Panel title={nodeId ? `Результат: ${nodeId}` : "Результат шага"}>
          {node && (
            <div className="auto-pad">
              <strong>{String(node.data.label || node.type)}</strong>
              <div className="auto-run-node-type">{node.type}</div>
            </div>
          )}
          {state ? (
            <>
              <div className="auto-pad">
                <StatusBadge status={state.status} />
                {(state.started_at || state.finished_at) && (
                  <dl className="detail-list auto-run-node-times">
                    {state.started_at && (
                      <>
                        <dt>Начало</dt>
                        <dd>{formatDate(state.started_at)}</dd>
                      </>
                    )}
                    {state.finished_at && (
                      <>
                        <dt>Завершение</dt>
                        <dd>{formatDate(state.finished_at)}</dd>
                      </>
                    )}
                  </dl>
                )}
                {state.status === "awaiting_approval" && (
                  <p className="notice notice-warning">
                    Ожидается решение назначенного согласующего. Для решения
                    используйте полученную ссылку согласования.
                  </p>
                )}
                {state.error && (
                  <p className="notice notice-danger">{state.error}</p>
                )}
              </div>
              <pre className="auto-log">
                {state.output || "Шаг ещё не вернул результат."}
              </pre>
            </>
          ) : (
            <EmptyState
              title={node ? "Результат пока не записан" : "Выберите шаг"}
              description={
                node
                  ? "Для этого шага ещё нет сохранённого статуса или вывода."
                  : "Здесь появятся вывод и диагностические сообщения."
              }
            />
          )}
        </Panel>
      </div>
      <Panel title="Шаги процесса">
        <DataTable
          rows={run.nodes_snapshot.map((item) => ({
            id: item.id,
            label: String(item.data.label || item.type),
            status: run.node_states[item.id]?.status,
          }))}
          rowKey={(row) => row.id}
          pageSize={30}
          columns={[
            {
              key: "node",
              label: "Шаг",
              render: (row) => (
                <Button
                  variant="ghost"
                  aria-pressed={row.id === nodeId}
                  onClick={() => setSelected(row.id)}
                >
                  {row.label}
                </Button>
              ),
            },
            {
              key: "status",
              label: "Статус",
              render: (row) =>
                row.status ? (
                  <StatusBadge status={row.status} />
                ) : (
                  <span>Нет результата</span>
                ),
            },
          ]}
        />
      </Panel>
      {run.summary && (
        <Panel title="Итог запуска">
          <p className="auto-draft-message">{run.summary}</p>
        </Panel>
      )}
      <ConfirmDialog
        open={stop}
        onOpenChange={setStop}
        title="Остановить процесс?"
        description="Последующие шаги не будут запущены. Уже выполненные действия не откатываются."
        onConfirm={() => stopRun.mutate()}
        pending={stopRun.isPending}
        confirmLabel="Остановить"
      />
      <ConfirmDialog
        open={resume}
        onOpenChange={setResume}
        title="Подтвердите повтор действий"
        description={
          <div>
            <p>Эти шаги могут повторить изменения во внешних системах:</p>
            <ul>
              {resumeNodes.map((n, index) => (
                <li key={index}>
                  {n.node_id || n.id} · {n.node_type}
                </li>
              ))}
            </ul>
            <Feedback error={resumeRun.error} />
          </div>
        }
        onConfirm={() => resumeRun.mutate(true)}
        pending={resumeRun.isPending}
        confirmLabel="Возобновить с повтором"
      />
    </>
  );
}
interface DeadLetter {
  id: number;
  run_id: number;
  pipeline_name: string;
  node_id: string;
  status: string;
  attempt_count: number;
  max_attempts: number;
  last_error: string;
  created_at: string;
  resolution_note: string;
}
function DeadLetters() {
  const [status, setStatus] = useState("open");
  const query = useQuery({
    queryKey: ["automation", "dead-letters", status],
    queryFn: ({ signal }) =>
      api.get<DeadLetter[]>(
        `${studioBase}dead-letters/?status=${status}`,
        signal,
      ),
  });
  const [item, setItem] = useState<DeadLetter | null>(null);
  const [note, setNote] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      api.post(`${studioBase}dead-letters/${item!.id}/resolve/`, { note }),
    onSuccess: () => {
      setItem(null);
      setNote("");
      void query.refetch();
    },
  });
  return (
    <>
      <Panel
        title="Исчерпанные попытки"
        description="Разберите причины ошибок и зафиксируйте решение. Закрытие записи не повторяет запуск."
      >
        {query.isPending ? (
          <Skeleton />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : (
          <DataTable
            rows={query.data ?? []}
            rowKey={(r) => r.id}
            emptyTitle="Ошибок для разбора нет"
            toolbar={
              <select
                aria-label="Состояние разбора"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                <option value="open">Открытые</option>
                <option value="resolved">Разобранные</option>
                <option value="all">Все</option>
              </select>
            }
            columns={[
              {
                key: "process",
                label: "Процесс",
                render: (r) => (
                  <>
                    <Link to={`/automation/runs/pipeline/${r.run_id}`}>
                      {r.pipeline_name}
                    </Link>
                    <small>{r.node_id}</small>
                  </>
                ),
              },
              {
                key: "error",
                label: "Причина",
                render: (r) => (
                  <div className="auto-row-title">
                    <small>{r.last_error}</small>
                  </div>
                ),
              },
              {
                key: "attempts",
                label: "Попытки",
                render: (r) => `${r.attempt_count} / ${r.max_attempts}`,
              },
              {
                key: "action",
                label: "Действие",
                render: (r) =>
                  r.status === "open" ? (
                    <Button size="sm" onClick={() => setItem(r)}>
                      Зафиксировать решение
                    </Button>
                  ) : (
                    <StatusBadge status="completed">Разобрано</StatusBadge>
                  ),
              },
            ]}
          />
        )}
      </Panel>
      <Drawer
        open={!!item}
        onOpenChange={(v) => !v && setItem(null)}
        title="Результат разбора"
      >
        <div className="auto-form">
          <p>{item?.last_error}</p>
          <Field label="Решение" htmlFor="resolution-note">
            <textarea
              id="resolution-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Причина ошибки и принятые меры"
            />
          </Field>
          <Feedback error={mutation.error} />
          <Button
            variant="primary"
            loading={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            Закрыть запись
          </Button>
        </div>
      </Drawer>
    </>
  );
}
