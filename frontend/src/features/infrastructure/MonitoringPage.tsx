import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Check, RefreshCw, Radio } from "lucide-react";
import {
  infrastructureApi,
  type HealthRow,
  type Monitoring,
} from "@/api/infrastructure";
import { RealtimeConnection, type ConnectionState } from "@/realtime/socket";
import {
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  Feedback,
  Metric,
  PageHeader,
  Panel,
  Skeleton,
  StatusBadge,
} from "@/components/ui";
import { HealthTable } from "./OverviewPage";
import { MonitoringExtras } from "./MonitoringExtras";
import { formatDate } from "@/lib/utils";
interface MetricEvent extends Partial<HealthRow> {
  type: string;
  server_id: number;
  ts?: number;
}
export default function MonitoringPage() {
  const client = useQueryClient();
  const [live, setLive] = useState(false);
  const [state, setState] = useState<ConnectionState>("disconnected");
  const socket = useRef<RealtimeConnection<MetricEvent> | null>(null);
  const query = useQuery({
    queryKey: ["monitoring"],
    queryFn: ({ signal }) => infrastructureApi.monitoring(signal),
    staleTime: 30_000,
  });
  const refresh = useMutation({
    mutationFn: infrastructureApi.refresh,
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ["monitoring"] }),
  });
  const resolve = useMutation({
    mutationFn: infrastructureApi.resolveAlert,
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ["monitoring"] }),
  });
  const ids = (query.data?.servers ?? [])
    .map((s) => s.server_id ?? s.id)
    .slice(0, 100)
    .sort()
    .join(",");
  useEffect(() => {
    if (!live || !ids) return;
    const connection = new RealtimeConnection<MetricEvent>({
      path: "/ws/monitoring/live/",
      onState: setState,
      onOpen: () =>
        connection.send({
          type: "subscribe",
          server_ids: ids.split(",").map(Number),
        }),
      onMessage: (event) => {
        if (event.type === "live.metrics")
          client.setQueryData<Monitoring>(["monitoring"], (old) =>
            old
              ? {
                  ...old,
                  servers: old.servers.map((s) =>
                    (s.server_id ?? s.id) === event.server_id
                      ? {
                          ...s,
                          ...event,
                          is_stale: false,
                          checked_at: event.ts
                            ? new Date(event.ts * 1000).toISOString()
                            : s.checked_at,
                        }
                      : s,
                  ),
                }
              : old,
          );
      },
    });
    socket.current = connection;
    connection.connect();
    return () => {
      connection.close();
      socket.current = null;
    };
  }, [live, ids, client]);
  const data = query.data;
  return (
    <>
      <PageHeader
        eyebrow="Инфраструктура"
        title="Мониторинг"
        description="Сначала состояние и проблемный ресурс, затем метрики и действие."
        actions={
          <>
            <Button
              onClick={() => setLive((v) => !v)}
              variant={live ? "primary" : "secondary"}
            >
              <Radio size={14} />
              {live ? "Live включён" : "Включить Live"}
            </Button>
            <Button
              onClick={() => refresh.mutate()}
              loading={refresh.isPending}
            >
              <RefreshCw size={14} />
              Проверить сейчас
            </Button>
          </>
        }
      />
      {live && (
        <div className="row" style={{ marginBottom: 16 }}>
          <StatusBadge status={state} />
          {state === "failed" && (
            <Button size="sm" onClick={() => socket.current?.reconnect()}>
              Переподключить
            </Button>
          )}
          <span className="text-sm muted">
            Live-метрики используют SSH-соединения к доступным серверам.
          </span>
        </div>
      )}
      <Feedback error={refresh.error ?? resolve.error} />
      {query.error && (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      )}
      <div className="metrics-strip">
        <Metric
          label="В норме"
          value={
            data?.servers.filter(
              (server) => !server.is_stale && server.status === "healthy",
            ).length ?? "—"
          }
          icon={<Activity size={15} />}
        />
        <Metric label="Предупреждения" value={data?.summary.warning ?? "—"} />
        <Metric
          label="Критические / недоступны"
          value={data ? data.summary.critical + data.summary.unreachable : "—"}
        />
        <Metric
          label="Нет свежих данных"
          value={
            data?.servers.filter((s) => s.is_stale || s.status === "unknown")
              .length ?? "—"
          }
        />
      </div>
      <div className="stack">
        <Panel
          title="Активные оповещения"
          description="Проверьте источник проблемы перед закрытием события."
        >
          {query.isPending ? (
            <Skeleton rows={3} />
          ) : data?.alerts.length ? (
            <DataTable
              rows={data.alerts}
              rowKey={(a) => a.id}
              columns={[
                {
                  key: "severity",
                  label: "Важность",
                  render: (a) => <StatusBadge status={a.severity} />,
                },
                {
                  key: "title",
                  label: "Событие",
                  render: (a) => (
                    <div>
                      <strong>{a.title}</strong>
                      <small>{a.message}</small>
                    </div>
                  ),
                },
                {
                  key: "resource",
                  label: "Ресурс",
                  render: (a) => (
                    <Link to={`/infrastructure/servers/${a.server_id}`}>
                      {a.server_name}
                    </Link>
                  ),
                },
                {
                  key: "date",
                  label: "Обнаружено",
                  render: (a) => formatDate(a.created_at),
                },
                {
                  key: "action",
                  label: "",
                  render: (a) => (
                    <Button
                      size="sm"
                      loading={resolve.isPending}
                      onClick={() => resolve.mutate(a.id)}
                    >
                      <Check size={14} />
                      Решено
                    </Button>
                  ),
                },
              ]}
            />
          ) : (
            <EmptyState
              title="Активных оповещений нет"
              description="Новые события будут отображаться после проверки мониторинга."
            />
          )}
        </Panel>
        <Panel title="Состояние ресурсов">
          {query.isPending ? (
            <Skeleton />
          ) : (
            <HealthTable rows={data?.servers ?? []} />
          )}
        </Panel>
      </div>
      <MonitoringExtras />
    </>
  );
}
