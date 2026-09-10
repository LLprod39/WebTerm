import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Activity,
  Check,
  Play,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { infrastructureApi } from "@/api/infrastructure";
import {
  monitoringExtrasApi,
  type AiInsight,
  type Certificate,
  type HealthCheck,
  type InsightServer,
  type MonitoringConfig,
  type Prediction,
  type Thresholds,
  type WatcherDraft,
} from "@/api/monitoring-extras";
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
  JsonDetails,
  LoadingState,
  Metric,
  Panel,
  StatusBadge,
  Tabs,
} from "@/components/ui";
import "./server-operations.css";

const number = (value: number | null | undefined, unit = "") =>
  value == null
    ? "—"
    : `${value.toLocaleString("ru-RU", { maximumFractionDigits: 2 })}${unit}`;
const date = (value: string | null | undefined) =>
  value ? new Date(value).toLocaleString("ru-RU") : "—";
const predictionLabels: Record<string, string> = {
  disk_full: "Заполнение диска",
  inode_full: "Исчерпание inode",
  memory_pressure: "Дефицит памяти",
  cert_expiry: "Истечение сертификата",
};
function StaffOnly() {
  return (
    <EmptyState
      icon={<ShieldCheck size={24} />}
      title="Доступно администраторам"
      description="Расширенная аналитика охватывает все серверы платформы."
    />
  );
}
function useServerList() {
  return useQuery({
    queryKey: ["servers"],
    queryFn: ({ signal }) => infrastructureApi.bootstrap(signal),
    staleTime: 30_000,
  });
}
function Markdown({ children }: { children: string }) {
  return (
    <div className="prose ops-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}

function HealthChart({ checks }: { checks: HealthCheck[] }) {
  const rows = checks.filter((row) =>
    Number.isFinite(Date.parse(row.checked_at)),
  );
  if (rows.length < 2)
    return (
      <EmptyState
        title="Недостаточно данных для графика"
        description="Нужно минимум две проверки в выбранном периоде."
      />
    );
  const minTime = Date.parse(rows[0].checked_at),
    maxTime = Date.parse(rows[rows.length - 1].checked_at);
  const series = [
    { key: "cpu_percent" as const, label: "CPU", color: "var(--accent)" },
    { key: "memory_percent" as const, label: "Память", color: "#b88832" },
    { key: "disk_percent" as const, label: "Диск", color: "#7c6ac5" },
  ];
  return (
    <figure className="ops-chart">
      <svg
        viewBox="0 0 900 250"
        role="img"
        aria-label="История CPU, памяти и диска, в процентах от 0 до 100"
      >
        <title>Использование ресурсов по времени</title>
        {[0, 25, 50, 75, 100].map((value) => (
          <g key={value}>
            <line
              x1="45"
              x2="885"
              y1={215 - value * 1.9}
              y2={215 - value * 1.9}
              stroke="var(--border)"
            />
            <text
              x="5"
              y={219 - value * 1.9}
              fill="var(--text-muted)"
              fontSize="11"
            >
              {value}%
            </text>
          </g>
        ))}
        {series.map((seriesItem) => {
          let previousKnown = false;
          const path = rows
            .map((row) => {
              const value = row[seriesItem.key];
              if (value == null) {
                previousKnown = false;
                return "";
              }
              const x =
                45 +
                ((Date.parse(row.checked_at) - minTime) /
                  Math.max(1, maxTime - minTime)) *
                  840;
              const y = 215 - Math.min(100, Math.max(0, value)) * 1.9;
              const command = `${previousKnown ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
              previousKnown = true;
              return command;
            })
            .join(" ");
          return (
            <path
              key={seriesItem.key}
              d={path}
              stroke={seriesItem.color}
              strokeWidth="2"
              fill="none"
            />
          );
        })}
        <text x="45" y="242" fill="var(--text-muted)" fontSize="11">
          {date(rows[0].checked_at)}
        </text>
        <text
          x="885"
          y="242"
          textAnchor="end"
          fill="var(--text-muted)"
          fontSize="11"
        >
          {date(rows[rows.length - 1].checked_at)}
        </text>
      </svg>
      <figcaption className="row">
        {series.map((item) => (
          <span key={item.key} className="row text-sm">
            <i
              style={{
                backgroundColor: item.color,
                width: 9,
                height: 9,
                borderRadius: "50%",
              }}
            />
            {item.label}
          </span>
        ))}
        <span className="muted text-sm">
          Пробелы означают отсутствие данных. Значения доступны в таблице.
        </span>
      </figcaption>
    </figure>
  );
}
export function MonitoringHistory() {
  const servers = useServerList();
  const client = useQueryClient();
  const [serverId, setServerId] = useState("");
  const [hours, setHours] = useState("24");
  const [deep, setDeep] = useState(false);
  const query = useQuery({
    queryKey: ["monitoring-history", serverId, hours],
    queryFn: ({ signal }) =>
      monitoringExtrasApi.history(Number(serverId), Number(hours), signal),
    enabled: !!serverId,
    retry: false,
  });
  const check = useMutation({
    mutationFn: () => monitoringExtrasApi.healthCheck(Number(serverId), deep),
    onSuccess: () => {
      void client.invalidateQueries({
        queryKey: ["monitoring-history", serverId],
      });
      void client.invalidateQueries({ queryKey: ["monitoring"] });
    },
  });
  const analysis = useMutation({
    mutationFn: () => monitoringExtrasApi.analyze(Number(serverId)),
  });
  function selectServer(value: string) {
    setServerId(value);
    check.reset();
    analysis.reset();
  }
  const checks = query.data?.checks || [];
  return (
    <Panel
      title="История состояния"
      description="Проверки CPU, памяти, диска и доступности выбранного сервера."
    >
      <div className="section-body stack">
        <div className="ops-toolbar">
          <Field label="Сервер" htmlFor="monitor-history-server">
            <select
              id="monitor-history-server"
              value={serverId}
              onChange={(e) => selectServer(e.target.value)}
            >
              <option value="">Выберите сервер</option>
              {servers.data?.servers
                .filter((server) => server.server_type === "ssh")
                .map((server) => (
                  <option key={server.id} value={server.id}>
                    {server.name} · {server.host}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="Период" htmlFor="monitor-history-hours">
            <select
              id="monitor-history-hours"
              value={hours}
              onChange={(e) => setHours(e.target.value)}
            >
              {[
                { value: "6", label: "6 часов" },
                { value: "24", label: "24 часа" },
                { value: "72", label: "3 дня" },
                { value: "168", label: "7 дней" },
              ].map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </Field>
          <Button
            disabled={!serverId}
            onClick={() => void query.refetch()}
            loading={query.isFetching}
          >
            <RefreshCw size={14} />
            Обновить
          </Button>
        </div>
        {servers.error && (
          <ErrorState
            error={servers.error}
            retry={() => void servers.refetch()}
          />
        )}
        {!serverId ? (
          <EmptyState
            icon={<Activity size={24} />}
            title="Выберите сервер"
            description="История использует сохранённые проверки мониторинга."
          />
        ) : query.isPending ? (
          <LoadingState />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : (
          <>
            <div className="ops-toolbar">
              <label className="row">
                <input
                  type="checkbox"
                  checked={deep}
                  onChange={(e) => setDeep(e.target.checked)}
                />
                Расширенная проверка
              </label>
              <Button onClick={() => check.mutate()} loading={check.isPending}>
                Проверить сейчас
              </Button>
              <Button
                onClick={() => analysis.mutate()}
                loading={analysis.isPending}
                disabled={!checks.length}
              >
                <Sparkles size={14} />
                AI-анализ
              </Button>
              <span className="muted text-sm">
                Расширенная проверка также собирает службы и ошибки журналов.
              </span>
            </div>
            <Feedback
              error={check.error || analysis.error}
              success={
                check.isSuccess
                  ? check.data.queued
                    ? "Проверка уже выполняется. Обновите историю после завершения."
                    : check.data.cached
                      ? "Использован недавний результат проверки."
                      : "Проверка завершена."
                  : undefined
              }
            />
            <HealthChart checks={checks} />
            <DataTable
              rows={[...checks].reverse()}
              rowKey={(row) => row.id}
              emptyTitle="В этом периоде проверок нет"
              columns={[
                {
                  key: "time",
                  label: "Время",
                  render: (row) => date(row.checked_at),
                  sortValue: (row) => row.checked_at,
                },
                {
                  key: "status",
                  label: "Состояние",
                  render: (row) => <StatusBadge status={row.status} />,
                },
                {
                  key: "cpu",
                  label: "CPU",
                  render: (row) => number(row.cpu_percent, "%"),
                  sortValue: (row) => row.cpu_percent ?? -1,
                },
                {
                  key: "memory",
                  label: "Память",
                  render: (row) => number(row.memory_percent, "%"),
                  sortValue: (row) => row.memory_percent ?? -1,
                },
                {
                  key: "disk",
                  label: "Диск",
                  render: (row) => number(row.disk_percent, "%"),
                  sortValue: (row) => row.disk_percent ?? -1,
                },
                {
                  key: "load",
                  label: "Нагрузка · 1 мин",
                  render: (row) => number(row.load_1m),
                },
                {
                  key: "response",
                  label: "Отклик",
                  render: (row) => number(row.response_time_ms, " мс"),
                },
                {
                  key: "kind",
                  label: "Проверка",
                  render: (row) => (row.is_deep ? "Расширенная" : "Базовая"),
                },
              ]}
            />
            {analysis.data && (
              <Panel title={`AI-анализ · ${analysis.data.server_name}`}>
                <div className="section-body">
                  <Markdown>{analysis.data.analysis}</Markdown>
                </div>
              </Panel>
            )}
          </>
        )}
      </div>
    </Panel>
  );
}

function InsightContent({ insight }: { insight: AiInsight }) {
  return (
    <div className="stack">
      <div className="spread">
        <StatusBadge status={insight.verdict} />
        <span className="muted text-sm">
          {date(insight.created_at)} · {insight.model || "Модель не указана"}
        </span>
      </div>
      {insight.error && (
        <div className="notice notice-danger">{insight.error}</div>
      )}
      <Markdown>{insight.content || "Текст анализа отсутствует."}</Markdown>
    </div>
  );
}
function Spark({ values }: { values: number[] }) {
  if (values.length < 2)
    return <span className="muted text-sm">Нет тренда</span>;
  const points = values
    .map(
      (value, index) =>
        `${(index / (values.length - 1)) * 100},${30 - Math.min(100, Math.max(0, value)) * 0.3}`,
    )
    .join(" ");
  return (
    <svg
      width="100"
      height="32"
      viewBox="0 0 100 32"
      role="img"
      aria-label={`Тренд ${number(values[0], "%")} → ${number(values[values.length - 1], "%")}`}
    >
      <polyline
        points={points}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="1.5"
      />
    </svg>
  );
}
export function MonitoringInsights({
  initialView = "fleet",
}: {
  initialView?: "fleet" | "predictions" | "certificates";
}) {
  const { user } = useSession();
  const client = useQueryClient();
  const [view, setView] = useState<string>(initialView);
  const [server, setServer] = useState<InsightServer | null>(null);
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [certificate, setCertificate] = useState<Certificate | null>(null);
  const query = useQuery({
    queryKey: ["monitoring-insights"],
    queryFn: ({ signal }) => monitoringExtrasApi.insights(true, signal),
    enabled: !!user?.is_staff,
    staleTime: 60_000,
    retry: false,
    refetchInterval: (queryState) =>
      queryState.state.data?.ai.running ? 5000 : false,
  });
  const run = useMutation({
    mutationFn: (serverId?: number) =>
      monitoringExtrasApi.runInsights(serverId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["monitoring-insights"] });
    },
  });
  if (!user?.is_staff) return <StaffOnly />;
  if (query.isPending)
    return <LoadingState label="Собираем расширенную аналитику…" />;
  if (query.error)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  const data = query.data;
  return (
    <Panel
      title="Метрики и прогнозы"
      description="Все активные серверы платформы. Индекс состояния вычисляется по сигналам мониторинга."
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
      <Tabs
        value={view}
        onChange={setView}
        items={[
          {
            value: "fleet",
            label: "Инфраструктура",
            count: data.summary.servers_total,
          },
          {
            value: "predictions",
            label: "Прогнозы",
            count: data.predictions.length,
          },
          {
            value: "certificates",
            label: "Сертификаты",
            count: data.certificates.length,
          },
          { value: "ai", label: "AI-анализ" },
        ]}
      />
      <div className="section-body stack">
        <span className="muted text-sm">
          Сформировано {date(data.generated_at)}
        </span>
        <div className="ops-metrics">
          <Metric
            label="Индекс состояния / 100"
            value={data.servers.length ? data.summary.fleet_health_score : "—"}
            detail={
              data.servers.length
                ? `Худший сервер: ${data.summary.fleet_health_worst}`
                : "Нет активных серверов"
            }
          />
          <Metric label="Оповещения" value={data.summary.active_alerts} />
          <Metric
            label="Критические прогнозы"
            value={data.summary.predictions_critical}
          />
          <Metric
            label="TLS · истекают за 30 дней"
            value={data.summary.certificates_expiring_30d}
          />
        </div>
        {view === "fleet" && (
          <DataTable
            rows={data.servers}
            rowKey={(row) => row.id}
            searchValue={(row) => `${row.name} ${row.host} ${row.owner}`}
            searchPlaceholder="Сервер, адрес или владелец"
            emptyTitle="Активных серверов нет"
            columns={[
              {
                key: "name",
                label: "Сервер",
                render: (row) => (
                  <button className="text-link" onClick={() => setServer(row)}>
                    <strong>{row.name}</strong>
                    <span className="mono muted text-sm"> {row.host}</span>
                  </button>
                ),
                sortValue: (row) => row.name,
              },
              {
                key: "status",
                label: "Состояние",
                render: (row) => <StatusBadge status={row.status} />,
              },
              {
                key: "score",
                label: "Индекс",
                render: (row) => `${row.health_score}/100`,
                sortValue: (row) => row.health_score,
              },
              {
                key: "cpu",
                label: "CPU",
                render: (row) => (
                  <div>
                    {number(row.cpu_percent, "%")}
                    <Spark values={row.spark.cpu} />
                  </div>
                ),
                sortValue: (row) => row.cpu_percent ?? -1,
              },
              {
                key: "memory",
                label: "Память",
                render: (row) => (
                  <div>
                    {number(row.memory_percent, "%")}
                    <Spark values={row.spark.mem} />
                  </div>
                ),
                sortValue: (row) => row.memory_percent ?? -1,
              },
              {
                key: "disk",
                label: "Диск",
                render: (row) => (
                  <div>
                    {number(row.worst_disk?.percent, "%")}
                    <Spark values={row.spark.disk} />
                  </div>
                ),
              },
              {
                key: "sample",
                label: "Данные",
                render: (row) => (
                  <div className="text-sm">
                    {date(row.sample_at || row.checked_at)}
                    <div className="muted">
                      {row.has_extended_metrics
                        ? "Расширенные метрики"
                        : "Базовая проверка"}
                    </div>
                  </div>
                ),
              },
            ]}
          />
        )}
        {view === "predictions" && (
          <>
            <p className="muted text-sm">
              Прогнозы основаны на тенденциях сохранённых метрик. Срок — оценка
              при сохранении текущей динамики; пустой список не подтверждает
              отсутствие рисков при недостатке наблюдений.
            </p>
            <DataTable
              rows={data.predictions}
              rowKey={(row) => `${row.server_id}:${row.kind}:${row.target}`}
              emptyTitle="Прогнозов в текущих данных нет"
              columns={[
                {
                  key: "severity",
                  label: "Риск",
                  render: (row) => <StatusBadge status={row.severity} />,
                },
                {
                  key: "server",
                  label: "Сервер",
                  render: (row) => (
                    <Link
                      className="text-link"
                      to={`/infrastructure/servers/${row.server_id}`}
                    >
                      {row.server_name}
                    </Link>
                  ),
                },
                {
                  key: "kind",
                  label: "Прогноз",
                  render: (row) => (
                    <button
                      className="text-link"
                      onClick={() => setPrediction(row)}
                    >
                      {predictionLabels[row.kind] || row.kind}
                      <div className="mono muted text-sm">{row.target}</div>
                    </button>
                  ),
                },
                {
                  key: "eta",
                  label: "Ожидаемый срок",
                  render: (row) => (
                    <div>
                      {number(row.eta_days, " дн")}
                      <div className="muted text-sm">
                        {date(row.predicted_for)}
                      </div>
                    </div>
                  ),
                  sortValue: (row) => row.eta_days ?? Infinity,
                },
                {
                  key: "value",
                  label: "Текущее / порог",
                  render: (row) =>
                    `${number(row.current_value)} / ${number(row.threshold)} ${row.unit}`,
                },
                {
                  key: "confidence",
                  label: "Уверенность",
                  render: (row) => number(row.confidence * 100, "%"),
                },
              ]}
            />
          </>
        )}
        {view === "certificates" && (
          <DataTable
            rows={data.certificates}
            rowKey={(row) => row.id}
            searchValue={(row) =>
              `${row.server_name} ${row.endpoint} ${row.subject} ${row.issuer} ${row.sans.join(" ")}`
            }
            searchPlaceholder="Сервер, домен или издатель"
            emptyTitle="Сертификаты ещё не обнаружены"
            columns={[
              {
                key: "endpoint",
                label: "TLS endpoint",
                render: (row) => (
                  <button
                    className="text-link mono"
                    onClick={() => setCertificate(row)}
                  >
                    {row.endpoint}:{row.port}
                  </button>
                ),
              },
              {
                key: "server",
                label: "Сервер",
                render: (row) => row.server_name,
              },
              {
                key: "subject",
                label: "Субъект",
                render: (row) => row.subject || "—",
              },
              {
                key: "issuer",
                label: "Издатель",
                render: (row) => row.issuer || "—",
              },
              {
                key: "expiry",
                label: "Срок действия",
                render: (row) => (
                  <div>
                    <StatusBadge
                      status={
                        row.days_left == null
                          ? "unknown"
                          : row.days_left <= 7
                            ? "critical"
                            : row.days_left <= 30
                              ? "warning"
                              : "healthy"
                      }
                    >
                      {row.days_left == null
                        ? "Неизвестно"
                        : `${number(row.days_left)} дн`}
                    </StatusBadge>
                    <div className="muted text-sm">{date(row.not_after)}</div>
                  </div>
                ),
                sortValue: (row) => row.days_left ?? Infinity,
              },
              {
                key: "checked",
                label: "Проверен",
                render: (row) => date(row.last_checked_at),
              },
            ]}
          />
        )}
        {view === "ai" && (
          <>
            <div className="spread">
              <p className="muted text-sm">
                Анализирует собранные метрики и контекст инфраструктуры. Команды
                на серверах не выполняет.
              </p>
              <Button
                variant="primary"
                disabled={!data.ai.enabled || data.ai.running}
                loading={run.isPending}
                onClick={() => run.mutate(undefined)}
              >
                <Sparkles size={14} />
                {data.ai.running
                  ? "Анализ выполняется…"
                  : "Запустить AI-анализ"}
              </Button>
            </div>
            {!data.ai.enabled && (
              <div className="notice">
                AI-анализ мониторинга отключён в конфигурации платформы.
              </div>
            )}
            <Feedback
              error={run.error}
              success={
                run.isSuccess
                  ? run.data.queued
                    ? "Анализ поставлен в очередь. Результат появится после завершения."
                    : "Анализ уже выполняется."
                  : undefined
              }
            />
            {data.ai.fleet ? (
              <InsightContent insight={data.ai.fleet} />
            ) : (
              <EmptyState
                title="Анализ ещё не выполнен"
                description="Результат появится после первого успешного запуска."
              />
            )}
          </>
        )}
      </div>
      <Drawer
        open={server !== null}
        onOpenChange={(open) => !open && setServer(null)}
        title={server?.name || "Сервер"}
        description={server ? `${server.host} · владелец ${server.owner}` : ""}
        wide
      >
        {server && (
          <div className="stack">
            <Link
              className="btn btn-secondary"
              to={`/infrastructure/servers/${server.id}`}
            >
              Открыть сервер
            </Link>
            <dl className="ops-facts">
              {[
                ["CPU iowait", number(server.cpu_iowait_percent, "%")],
                ["CPU steal", number(server.cpu_steal_percent, "%")],
                ["Доступная память", number(server.memory_available_mb, " МБ")],
                ["Swap", number(server.swap_percent, "%")],
                ["Получено по сети", number(server.net_rx_bps, " Б/с")],
                ["Передано по сети", number(server.net_tx_bps, " Б/с")],
                ["TCP retransmit", number(server.tcp_retrans_per_sec, "/с")],
                ["Соединения TCP", number(server.tcp_established)],
                ["Файловые дескрипторы", number(server.fd_percent, "%")],
                ["Zombie процессы", number(server.zombie_count)],
                ["Ошибки журнала · 10 мин", number(server.journal_err_10m)],
                [
                  "Требуется перезагрузка",
                  server.reboot_required == null
                    ? "Нет данных"
                    : server.reboot_required
                      ? "Да"
                      : "Нет",
                ],
                [
                  "Синхронизация времени",
                  server.ntp_synchronized == null
                    ? "Нет данных"
                    : server.ntp_synchronized
                      ? "Да"
                      : "Нет",
                ],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <Button
              disabled={!data.ai.enabled || data.ai.running}
              loading={run.isPending}
              onClick={() => run.mutate(server.id)}
            >
              <Sparkles size={14} />
              AI-анализ сервера
            </Button>
            <Feedback error={run.error} />
            {data.ai.by_endpoint[server.endpoint_key] && (
              <InsightContent
                insight={data.ai.by_endpoint[server.endpoint_key]}
              />
            )}
          </div>
        )}
      </Drawer>
      <Drawer
        open={prediction !== null}
        onOpenChange={(open) => !open && setPrediction(null)}
        title={
          prediction
            ? predictionLabels[prediction.kind] || prediction.kind
            : "Прогноз"
        }
        description={
          prediction ? `${prediction.server_name} · ${prediction.target}` : ""
        }
      >
        {prediction && (
          <div className="stack">
            <StatusBadge status={prediction.severity} />
            <p>
              Ожидается {date(prediction.predicted_for)}. Изменение в день:{" "}
              {number(prediction.slope_per_day)} {prediction.unit}.
            </p>
            <JsonDetails
              data={prediction.evidence}
              label="Наблюдения для прогноза"
            />
          </div>
        )}
      </Drawer>
      <Drawer
        open={certificate !== null}
        onOpenChange={(open) => !open && setCertificate(null)}
        title="Сертификат TLS"
        description={
          certificate
            ? `${certificate.server_name} · ${certificate.endpoint}:${certificate.port}`
            : ""
        }
      >
        {certificate && (
          <dl className="ops-facts">
            {[
              ["Субъект", certificate.subject],
              ["Издатель", certificate.issuer],
              ["Действует до", date(certificate.not_after)],
              ["Изменение отпечатка", date(certificate.changed_at)],
              ["Последняя проверка", date(certificate.last_checked_at)],
              ["Альтернативные имена", certificate.sans.join(", ")],
            ].map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value || "—"}</dd>
              </div>
            ))}
          </dl>
        )}
      </Drawer>
    </Panel>
  );
}

export function MonitoringWatchers() {
  const { user } = useSession();
  const servers = useServerList();
  const client = useQueryClient();
  const [serverId, setServerId] = useState("");
  const [status, setStatus] = useState("open,acknowledged");
  const [persist, setPersist] = useState(true);
  const [selected, setSelected] = useState<WatcherDraft | null>(null);
  const [confirm, setConfirm] = useState<WatcherDraft | null>(null);
  const params = {
    ...(serverId ? { server_id: serverId } : {}),
    ...(status ? { status } : {}),
  };
  const query = useQuery({
    queryKey: ["monitoring-watchers", params],
    queryFn: ({ signal }) => monitoringExtrasApi.watchers(params, signal),
  });
  const invalidate = () =>
    void client.invalidateQueries({ queryKey: ["monitoring-watchers"] });
  const scan = useMutation({
    mutationFn: () =>
      monitoringExtrasApi.scan(serverId ? [Number(serverId)] : [], persist),
    onSuccess: invalidate,
  });
  const acknowledge = useMutation({
    mutationFn: monitoringExtrasApi.acknowledge,
    onSuccess: (result) => {
      setSelected(result.draft);
      invalidate();
    },
  });
  const launch = useMutation({
    mutationFn: monitoringExtrasApi.launch,
    onSuccess: (result) => {
      setSelected(result.draft);
      setConfirm(null);
      invalidate();
    },
  });
  return (
    <Panel
      title="Наблюдатели"
      description="Предложения по диагностике, сформированные из состояния, оповещений, прогнозов и памяти сервера."
    >
      <div className="section-body stack">
        <div className="ops-toolbar">
          <Field label="Сервер" htmlFor="watcher-server">
            <select
              id="watcher-server"
              value={serverId}
              onChange={(e) => {
                setServerId(e.target.value);
                scan.reset();
              }}
            >
              <option value="">Все доступные серверы</option>
              {servers.data?.servers.map((server) => (
                <option key={server.id} value={server.id}>
                  {server.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Состояние" htmlFor="watcher-status">
            <select
              id="watcher-status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="open,acknowledged">Открытые и принятые</option>
              <option value="open">Открытые</option>
              <option value="acknowledged">Принятые</option>
              <option value="resolved">Завершённые</option>
              <option value="suppressed">Подавленные</option>
              <option value="">Все</option>
            </select>
          </Field>
          <Button
            onClick={() => void query.refetch()}
            loading={query.isFetching}
          >
            <RefreshCw size={14} />
            Обновить
          </Button>
        </div>
        <div className="ops-toolbar">
          <label className="row">
            <input
              type="checkbox"
              checked={persist}
              onChange={(e) => {
                setPersist(e.target.checked);
                scan.reset();
              }}
            />
            Сохранить результаты сканирования
          </label>
          <Button onClick={() => scan.mutate()} loading={scan.isPending}>
            Проверить сигналы
          </Button>
          <span className="muted text-sm">
            До 100 серверов за один запрос. Сканирование не запускает агентов.
          </span>
        </div>
        <Feedback
          error={scan.error || acknowledge.error || launch.error}
          success={
            scan.data
              ? `Проверено серверов: ${scan.data.summary.scanned_servers}. Предложений: ${scan.data.summary.drafts}. ${scan.data.persisted_scan ? "Результаты сохранены." : "Предварительный просмотр без сохранения."}`
              : undefined
          }
        />
        {servers.error && (
          <ErrorState
            error={servers.error}
            retry={() => void servers.refetch()}
          />
        )}
        {scan.data && !scan.data.persisted_scan && (
          <Panel title="Предварительный просмотр">
            <DataTable
              rows={scan.data.drafts}
              rowKey={(row) => `${row.server_id}:${row.objective}`}
              emptyTitle="Новых предложений нет"
              columns={[
                {
                  key: "server",
                  label: "Сервер",
                  render: (row) => row.server_name,
                },
                {
                  key: "severity",
                  label: "Риск",
                  render: (row) => <StatusBadge status={row.severity} />,
                },
                {
                  key: "objective",
                  label: "Задача",
                  render: (row) => row.objective,
                },
              ]}
            />
          </Panel>
        )}
        {query.isPending ? (
          <LoadingState />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : (
          <>
            <div className="ops-metrics">
              <Metric label="Открытые" value={query.data.summary.open} />
              <Metric
                label="Принятые"
                value={query.data.summary.acknowledged}
              />
              <Metric label="Завершённые" value={query.data.summary.resolved} />
            </div>
            <DataTable
              rows={query.data.drafts}
              rowKey={(row) => row.id}
              searchValue={(row) =>
                `${row.objective} ${row.server_name} ${row.reasons.join(" ")}`
              }
              emptyTitle="Предложений по выбранным условиям нет"
              columns={[
                {
                  key: "severity",
                  label: "Риск",
                  render: (row) => <StatusBadge status={row.severity} />,
                },
                {
                  key: "server",
                  label: "Сервер",
                  render: (row) => row.server_name,
                },
                {
                  key: "objective",
                  label: "Предлагаемая задача",
                  render: (row) => (
                    <button
                      className="text-link"
                      onClick={() => setSelected(row)}
                    >
                      {row.objective}
                    </button>
                  ),
                },
                {
                  key: "status",
                  label: "Состояние",
                  render: (row) => <StatusBadge status={row.status} />,
                },
                {
                  key: "last",
                  label: "Последний сигнал",
                  render: (row) => date(row.last_seen_at),
                  sortValue: (row) => row.last_seen_at || "",
                },
                {
                  key: "actions",
                  label: "Действия",
                  render: (row) => (
                    <div className="row">
                      <Button
                        size="sm"
                        disabled={
                          row.status !== "open" || acknowledge.isPending
                        }
                        onClick={() => acknowledge.mutate(row.id)}
                      >
                        <Check size={13} />
                        Принять
                      </Button>
                      <Button
                        size="sm"
                        disabled={
                          !["open", "acknowledged"].includes(row.status) ||
                          launch.isPending
                        }
                        onClick={() => {
                          launch.reset();
                          setConfirm(row);
                        }}
                      >
                        <Play size={13} />
                        Запустить
                      </Button>
                    </div>
                  ),
                },
              ]}
            />
          </>
        )}
        {launch.data && (
          <div className="notice notice-success">
            Задание #{launch.data.run_id} создано:{" "}
            <StatusBadge status={launch.data.status} />
            {user?.features.agents && (
              <Link
                className="text-link"
                to={`/intelligence/runs/${launch.data.run_id}`}
              >
                Открыть выполнение
              </Link>
            )}
          </div>
        )}
      </div>
      <Drawer
        open={selected !== null}
        onOpenChange={(open) => !open && setSelected(null)}
        title="Предложение наблюдателя"
        description={selected?.server_name}
        wide
      >
        {selected && (
          <div className="stack">
            <div className="row">
              <StatusBadge status={selected.severity} />
              <StatusBadge status={selected.status} />
            </div>
            <h3>{selected.objective}</h3>
            <p className="muted text-sm">
              Роль агента: {selected.recommended_role}
            </p>
            <h4>Основания</h4>
            <ul>
              {selected.reasons.map((reason, index) => (
                <li key={index}>{reason}</li>
              ))}
            </ul>
            {selected.memory_excerpt.length > 0 && (
              <>
                <h4>Контекст из памяти</h4>
                <ul>
                  {selected.memory_excerpt.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              </>
            )}
            {selected.acknowledged_by && (
              <p className="muted text-sm">
                Принял {selected.acknowledged_by} ·{" "}
                {date(selected.acknowledged_at)}
              </p>
            )}
            {selected.metadata.last_launch_run_id && user?.features.agents && (
              <Link
                className="btn btn-secondary"
                to={`/intelligence/runs/${selected.metadata.last_launch_run_id}`}
              >
                Последнее выполнение #{selected.metadata.last_launch_run_id}
              </Link>
            )}
          </div>
        )}
      </Drawer>
      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Запустить агента по предложению?"
        description={
          <>
            <p>
              Сервер: <strong>{confirm?.server_name}</strong>
            </p>
            <p>{confirm?.objective}</p>
            <p>
              Будет создано задание агента с ролью {confirm?.recommended_role}.
              Допустимые действия определяются политикой доступа платформы.
            </p>
            <Feedback error={launch.error} />
          </>
        }
        typedText={confirm?.server_name}
        confirmLabel="Создать выполнение"
        onConfirm={() => confirm && launch.mutate(confirm.id)}
        pending={launch.isPending}
      />
    </Panel>
  );
}

export function MonitoringAlertHistory() {
  const servers = useServerList();
  const client = useQueryClient();
  const [serverId, setServerId] = useState("");
  const [severity, setSeverity] = useState("");
  const [resolved, setResolved] = useState("");
  const [detail, setDetail] = useState<
    | Awaited<ReturnType<typeof monitoringExtrasApi.alerts>>["alerts"][number]
    | null
  >(null);
  const params = {
    ...(serverId ? { server_id: serverId } : {}),
    ...(severity ? { severity } : {}),
    ...(resolved ? { resolved } : {}),
  };
  const query = useQuery({
    queryKey: ["monitoring-alerts", params],
    queryFn: ({ signal }) => monitoringExtrasApi.alerts(params, signal),
  });
  const resolve = useMutation({
    mutationFn: monitoringExtrasApi.resolve,
    onSuccess: () => {
      setDetail(null);
      void client.invalidateQueries({ queryKey: ["monitoring-alerts"] });
      void client.invalidateQueries({ queryKey: ["monitoring"] });
    },
  });
  return (
    <Panel
      title="История оповещений"
      description="До 200 последних событий, включая закрытые."
    >
      <div className="section-body stack">
        <div className="ops-toolbar">
          <Field label="Сервер" htmlFor="alert-history-server">
            <select
              id="alert-history-server"
              value={serverId}
              onChange={(e) => setServerId(e.target.value)}
            >
              <option value="">Все серверы</option>
              {servers.data?.servers.map((server) => (
                <option key={server.id} value={server.id}>
                  {server.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Важность" htmlFor="alert-history-severity">
            <select
              id="alert-history-severity"
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
            >
              <option value="">Все</option>
              <option value="critical">Критические</option>
              <option value="warning">Предупреждения</option>
              <option value="info">Информация</option>
            </select>
          </Field>
          <Field label="Состояние" htmlFor="alert-history-resolved">
            <select
              id="alert-history-resolved"
              value={resolved}
              onChange={(e) => setResolved(e.target.value)}
            >
              <option value="">Все</option>
              <option value="false">Активные</option>
              <option value="true">Закрытые</option>
            </select>
          </Field>
          <Button
            onClick={() => void query.refetch()}
            loading={query.isFetching}
          >
            <RefreshCw size={14} />
            Обновить
          </Button>
        </div>
        <Feedback error={resolve.error} />
        {query.isPending ? (
          <LoadingState />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : (
          <DataTable
            rows={query.data.alerts}
            rowKey={(row) => row.id}
            searchValue={(row) =>
              `${row.title} ${row.message} ${row.server_name}`
            }
            emptyTitle="Оповещений по выбранным условиям нет"
            columns={[
              {
                key: "severity",
                label: "Важность",
                render: (row) => <StatusBadge status={row.severity} />,
              },
              {
                key: "title",
                label: "Событие",
                render: (row) => (
                  <button className="text-link" onClick={() => setDetail(row)}>
                    {row.title}
                  </button>
                ),
              },
              {
                key: "server",
                label: "Сервер",
                render: (row) => row.server_name,
              },
              {
                key: "created",
                label: "Создано",
                render: (row) => date(row.created_at),
                sortValue: (row) => row.created_at,
              },
              {
                key: "state",
                label: "Состояние",
                render: (row) => (
                  <StatusBadge
                    status={row.is_resolved ? "resolved" : "warning"}
                  >
                    {row.is_resolved ? "Закрыто" : "Активно"}
                  </StatusBadge>
                ),
              },
              {
                key: "resolved",
                label: "Закрыто",
                render: (row) => date(row.resolved_at),
              },
            ]}
          />
        )}
      </div>
      <Drawer
        open={detail !== null}
        onOpenChange={(open) => !open && setDetail(null)}
        title={detail?.title || "Оповещение"}
        description={detail?.server_name}
      >
        {detail && (
          <div className="stack">
            <StatusBadge status={detail.severity} />
            <div className="ops-knowledge-content">{detail.message}</div>
            <JsonDetails data={detail.metadata} />
            <p className="muted text-sm">Создано {date(detail.created_at)}</p>
            {!detail.is_resolved && (
              <Button
                onClick={() => resolve.mutate(detail.id)}
                loading={resolve.isPending}
              >
                <Check size={14} />
                Отметить решённым
              </Button>
            )}
            <Feedback error={resolve.error} />
          </div>
        )}
      </Drawer>
    </Panel>
  );
}

function ThresholdEditor({ config }: { config: MonitoringConfig }) {
  const client = useQueryClient();
  const [values, setValues] = useState<Thresholds>(config.thresholds);
  const [error, setError] = useState("");
  const save = useMutation({
    mutationFn: () => monitoringExtrasApi.updateConfig(values),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["monitoring-config"] });
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (
      values.cpu_warn >= values.cpu_crit ||
      values.mem_warn >= values.mem_crit ||
      values.disk_warn >= values.disk_crit
    ) {
      setError(
        "Порог предупреждения должен быть ниже критического для каждого ресурса.",
      );
      return;
    }
    save.mutate();
  }
  const fields: { prefix: "cpu" | "mem" | "disk"; label: string }[] = [
    { prefix: "cpu", label: "CPU" },
    { prefix: "mem", label: "Память" },
    { prefix: "disk", label: "Диск" },
  ];
  return (
    <form onSubmit={submit} className="stack">
      <div className="notice notice-warning">
        Временные пороги текущего процесса сервера. Изменения сбрасываются после
        перезапуска и не синхронизируются между рабочими процессами. Постоянные
        значения задаются в конфигурации развёртывания.
      </div>
      <div className="ops-threshold-grid">
        <strong>Ресурс</strong>
        <strong>Предупреждение, %</strong>
        <strong>Критический, %</strong>
        {fields.map(({ prefix, label }) => (
          <div className="ops-threshold-row" key={prefix}>
            <span>{label}</span>
            {(["warn", "crit"] as const).map((level) => {
              const key = `${prefix}_${level}` as keyof Thresholds;
              return (
                <input
                  key={level}
                  aria-label={`${label} · ${level === "warn" ? "предупреждение" : "критический"}`}
                  type="number"
                  min="0"
                  max="100"
                  required
                  step="1"
                  value={values[key]}
                  onChange={(e) =>
                    setValues({ ...values, [key]: Number(e.target.value) })
                  }
                />
              );
            })}
          </div>
        ))}
      </div>
      <Feedback
        error={error ? new Error(error) : save.error}
        success={
          save.isSuccess ? "Пороги применены к текущему процессу." : undefined
        }
      />
      <Button variant="primary" type="submit" loading={save.isPending}>
        Применить временные пороги
      </Button>
    </form>
  );
}
export function MonitoringThresholds() {
  const { user } = useSession();
  const query = useQuery({
    queryKey: ["monitoring-config"],
    queryFn: ({ signal }) => monitoringExtrasApi.config(signal),
    enabled: !!user?.is_staff,
  });
  if (!user?.is_staff) return <StaffOnly />;
  return (
    <Panel
      title="Пороги мониторинга"
      description="Пороговые значения предупреждений и критических состояний."
    >
      <div className="section-body stack">
        {query.isPending ? (
          <LoadingState />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : (
          <>
            <div className="ops-metrics">
              <Metric
                label="Серверы SSH"
                value={query.data.stats.monitored_servers}
              />
              <Metric label="Проверки" value={query.data.stats.total_checks} />
              <Metric
                label="Активные оповещения"
                value={query.data.stats.active_alerts}
              />
              <Metric
                label="Последняя проверка"
                value={date(query.data.stats.last_check_at)}
              />
            </div>
            <ThresholdEditor config={query.data} />
          </>
        )}
      </div>
    </Panel>
  );
}
export function MonitoringExtras() {
  const { user } = useSession();
  const [tab, setTab] = useState("history");
  return (
    <div className="stack">
      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { value: "history", label: "История" },
          { value: "alerts", label: "Все оповещения" },
          { value: "watchers", label: "Наблюдатели" },
          ...(user?.is_staff
            ? [
                { value: "insights", label: "Метрики и прогнозы" },
                { value: "thresholds", label: "Пороги" },
              ]
            : []),
        ]}
      />
      {tab === "history" && <MonitoringHistory />}
      {tab === "alerts" && <MonitoringAlertHistory />}
      {tab === "watchers" && <MonitoringWatchers />}
      {tab === "insights" && <MonitoringInsights />}
      {tab === "thresholds" && <MonitoringThresholds />}
    </div>
  );
}
