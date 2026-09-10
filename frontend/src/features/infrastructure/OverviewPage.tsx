import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Activity,
  CheckCircle2,
  Plus,
  RefreshCw,
  Server,
  TriangleAlert,
} from "lucide-react";
import { infrastructureApi, type HealthRow } from "@/api/infrastructure";
import { usePermission, useSession } from "@/app/session";
import {
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  Metric,
  PageHeader,
  Panel,
  LoadingState,
  StatusBadge,
  type Column,
} from "@/components/ui";
import { formatDate } from "@/lib/utils";
import { DashboardSections } from "@/features/governance/DashboardPreferences";
export function Utilization({ value }: { value: number | null | undefined }) {
  return value == null ? (
    <span className="muted">—</span>
  ) : (
    <span className="mono text-sm">
      {value.toFixed(1)}%
      <span
        className={`progress-track${value > 90 ? " danger" : value > 75 ? " warning" : ""}`}
      >
        <span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </span>
    </span>
  );
}
export function HealthTable({
  rows,
  compact = false,
}: {
  rows: HealthRow[];
  compact?: boolean;
}) {
  const priority = (row: HealthRow) =>
    row.is_stale
      ? 2
      : ({ critical: 5, unreachable: 4, warning: 3, unknown: 2, healthy: 0 }[
          row.status
        ] ?? 1);
  return (
    <DataTable
      rows={[...rows].sort((a, b) => priority(b) - priority(a))}
      pageSize={compact ? 6 : 15}
      hideSinglePagePagination={compact}
      rowKey={(r) => r.server_id ?? r.id}
      searchValue={(r) => `${r.server_name ?? r.name} ${r.host}`}
      searchPlaceholder="Найти сервер…"
      emptyTitle="Нет данных мониторинга"
      emptyDescription="Добавьте сервер, чтобы начать отслеживать состояние инфраструктуры."
      columns={(
        [
          {
            key: "name",
            label: "Сервер",
            sortValue: (r) => r.server_name ?? r.name,
            render: (r) => (
              <div className="table-name">
                <span className="table-icon">
                  <Server size={16} />
                </span>
                <div>
                  <Link to={`/infrastructure/servers/${r.server_id ?? r.id}`}>
                    {r.server_name ?? r.name}
                  </Link>
                  <small className="mono">{r.host}</small>
                </div>
              </div>
            ),
          },
          {
            key: "status",
            label: "Состояние",
            render: (r) => (
              <div>
                <StatusBadge status={r.is_stale ? "unknown" : r.status}>
                  {r.is_stale ? "Нет свежих данных" : undefined}
                </StatusBadge>
                {r.is_stale && (
                  <small>
                    Последнее измерение:{" "}
                    {formatDate(r.metrics_checked_at ?? r.checked_at)}
                  </small>
                )}
              </div>
            ),
          },
          {
            key: "cpu",
            label: "CPU",
            sortValue: (r) => r.cpu_percent ?? -1,
            render: (r) => <Utilization value={r.cpu_percent} />,
          },
          {
            key: "memory",
            label: "Память",
            sortValue: (r) => r.memory_percent ?? -1,
            render: (r) => <Utilization value={r.memory_percent} />,
          },
          {
            key: "disk",
            label: "Диск",
            sortValue: (r) => r.disk_percent ?? -1,
            render: (r) => <Utilization value={r.disk_percent} />,
          },
          {
            key: "checked",
            label: "Обновлено",
            render: (r) => (
              <span className="text-sm muted">{formatDate(r.checked_at)}</span>
            ),
          },
        ] satisfies Column<HealthRow>[]
      ).filter(
        (column) => !compact || !["disk", "checked"].includes(column.key),
      )}
    />
  );
}
export default function OverviewPage() {
  const allowed = usePermission("servers");
  const { user } = useSession();
  const query = useQuery({
    queryKey: ["monitoring"],
    queryFn: ({ signal }) => infrastructureApi.monitoring(signal),
    enabled: allowed,
    staleTime: 30_000,
  });
  const data = query.data;
  const staleCount = data?.servers.filter(
    (server) => server.is_stale || server.status === "unknown",
  ).length;
  const healthyCount = data?.servers.filter(
    (server) => !server.is_stale && server.status === "healthy",
  ).length;
  const recentActivity =
    data?.recent_activity.filter(
      (item) => !["http_request", "login", "logout"].includes(item.action),
    ) ?? [];
  return (
    <>
      <PageHeader
        eyebrow="Рабочее пространство"
        title="Обзор инфраструктуры"
        description="Текущее состояние, важные события и следующие действия."
        actions={
          allowed && (
            <>
              <Button
                onClick={() => void query.refetch()}
                loading={query.isFetching}
              >
                <RefreshCw size={14} />
                Обновить
              </Button>
              <Link
                className="btn btn-primary"
                to="/infrastructure/servers?create=1"
              >
                <Plus size={15} />
                Добавить сервер
              </Link>
            </>
          )
        }
      />
      {query.error && (
        <>
          <ErrorState error={query.error} retry={() => void query.refetch()} />
          {data && (
            <p role="status" className="muted">
              Не удалось обновить обзор. Ниже показаны последние полученные
              данные.
            </p>
          )}
        </>
      )}
      {!allowed ? (
        <EmptyState
          title="Инфраструктура недоступна этой роли"
          description="Выберите доступный раздел в навигации. Для доступа к серверам обратитесь к администратору."
        />
      ) : !data ? (
        query.isPending ? (
          <LoadingState label="Загружаем состояние инфраструктуры…" />
        ) : null
      ) : (
        <>
          <div className="metrics-strip">
            <Metric
              label="Всего серверов"
              value={data?.summary.total_servers ?? "—"}
              icon={<Server size={15} />}
              detail="Доступно вашей учётной записи"
            />
            <Metric
              label="В норме"
              value={healthyCount ?? "—"}
              icon={<CheckCircle2 size={15} />}
              detail="Подтверждено мониторингом"
            />
            <Metric
              label="Требуют внимания"
              value={
                data
                  ? data.summary.warning +
                    data.summary.critical +
                    data.summary.unreachable
                  : "—"
              }
              icon={<TriangleAlert size={15} />}
              detail={
                data ? `${staleCount} без свежих данных` : "Ожидаем данные"
              }
            />
            <Metric
              label="Активные оповещения"
              value={data?.summary.active_alerts ?? "—"}
              icon={<Activity size={15} />}
              detail="Нерешённые события"
            />
          </div>
          <DashboardSections
            sections={{
              servers: (
                <Panel
                  title="Состояние серверов"
                  actions={
                    allowed && (
                      <Link className="text-sm" to="/infrastructure/servers">
                        Все серверы →
                      </Link>
                    )
                  }
                >
                  <HealthTable rows={data.servers} compact />
                </Panel>
              ),
              activity: (
                <Panel
                  title="Последние операции"
                  description="Ваши недавние действия в WebTerm."
                  actions={
                    user?.is_staff &&
                    user.features.settings && (
                      <Link className="text-sm" to="/governance/audit">
                        Журнал аудита →
                      </Link>
                    )
                  }
                >
                  {recentActivity.length ? (
                    <ul className="activity-list">
                      {recentActivity.slice(0, 6).map((item) => (
                        <li key={item.id}>
                          <span className="activity-marker" />
                          <div>
                            <p>{item.description || item.action}</p>
                            <small>
                              {item.entity_name && `${item.entity_name} · `}
                              {formatDate(item.created_at)}
                            </small>
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <EmptyState
                      title="Пока нет событий"
                      description="Здесь появятся ваши недавние операции."
                    />
                  )}
                </Panel>
              ),
              alerts: (
                <Panel
                  title="Требуют внимания"
                  actions={
                    <Link className="text-sm" to="/infrastructure/monitoring">
                      Мониторинг →
                    </Link>
                  }
                >
                  {data?.alerts.length ? (
                    <ul className="activity-list">
                      {data.alerts.slice(0, 5).map((alert) => (
                        <li key={alert.id}>
                          <TriangleAlert size={16} className="text-danger" />
                          <div>
                            <p>{alert.title}</p>
                            <small>
                              <Link
                                to={`/infrastructure/servers/${alert.server_id}`}
                              >
                                {alert.server_name}
                              </Link>{" "}
                              · {formatDate(alert.created_at)}
                            </small>
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <EmptyState
                      title="Активных оповещений нет"
                      description="Новые события мониторинга появятся здесь."
                      icon={<CheckCircle2 size={23} />}
                    />
                  )}
                </Panel>
              ),
            }}
          />
        </>
      )}
    </>
  );
}
