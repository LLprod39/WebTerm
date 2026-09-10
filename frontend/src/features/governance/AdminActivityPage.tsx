import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
  Activity,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Users,
} from "lucide-react";
import {
  adminActivityApi,
  type ActivityEvent,
  type AdminUsage,
  type ProviderUsage,
} from "@/api/admin-activity";
import { usePermission } from "@/app/session";
import {
  Button,
  DataTable,
  Drawer,
  EmptyState,
  ErrorState,
  LoadingState,
  Metric,
  PageHeader,
  Panel,
  StatusBadge,
  Tabs,
} from "@/components/ui";
import { CheckField, FormField, GovernanceGuard, dateTime } from "./shared";

const number = (value: number) => new Intl.NumberFormat("ru-RU").format(value);
const usd = (value: number | null) =>
  value == null
    ? "Нет данных"
    : new Intl.NumberFormat("ru-RU", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 4,
      }).format(value);
const bounded = (
  value: string | null,
  fallback: number,
  min: number,
  max: number,
) => {
  const parsed = Number(value);
  return value && Number.isSafeInteger(parsed)
    ? Math.min(max, Math.max(min, parsed))
    : fallback;
};

function ActiveUsersPanel({ onUser }: { onUser: (id: number) => void }) {
  const [live, setLive] = useState(true);
  const query = useQuery({
    queryKey: ["governance", "active-users"],
    queryFn: ({ signal }) => adminActivityApi.sessions(signal),
    refetchInterval: live ? 30_000 : false,
    refetchIntervalInBackground: false,
  });
  if (query.isPending) return <LoadingState />;
  if (query.error)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  const data = query.data;
  return (
    <>
      <div className="gov-metrics">
        <Metric
          label="Активность за 5 минут"
          value={data.online_count}
          icon={<Users size={16} />}
        />
        <Metric label="Активны сегодня" value={data.active_today} />
        <Metric label="Всего учётных записей" value={data.total_registered} />
        <Metric
          label="Терминалы участников"
          value={data.sessions.reduce(
            (sum, user) => sum + user.active_terminals,
            0,
          )}
          detail="У пользователей из этой выборки"
        />
      </div>
      <Panel
        title="Пользователи за последние 5 минут"
        description="В выборку попадают пользователи с зарегистрированными событиями. Открытая сессия без событий здесь не отображается."
        actions={
          <Button
            size="sm"
            aria-label="Обновить активность пользователей"
            loading={query.isFetching}
            onClick={() => void query.refetch()}
          >
            <RefreshCw size={14} />
            Обновить
          </Button>
        }
      >
        <DataTable
          rows={data.sessions}
          rowKey={(row) => row.user_id}
          searchValue={(row) =>
            `${row.username} ${row.email} ${row.last_action}`
          }
          searchPlaceholder="Найти активного пользователя"
          emptyTitle="За последние 5 минут событий нет"
          emptyDescription="Здесь появятся пользователи после следующего зарегистрированного действия."
          columns={[
            {
              key: "user",
              label: "Пользователь",
              sortValue: (row) => row.username,
              render: (row) => (
                <button
                  className="gov-cell-button"
                  onClick={() => onUser(row.user_id)}
                >
                  <strong>{row.username}</strong>
                  <small>{row.email || `ID ${row.user_id}`}</small>
                </button>
              ),
            },
            {
              key: "role",
              label: "Роль",
              render: (row) =>
                row.is_staff ? "Администратор" : "Пользователь",
            },
            {
              key: "action",
              label: "Последнее событие",
              render: (row) => (
                <div>
                  {row.last_action}
                  <small className="gov-subline">{row.last_category}</small>
                </div>
              ),
            },
            {
              key: "time",
              label: "Время события",
              sortValue: (row) => row.last_activity,
              render: (row) => (
                <span className="gov-nowrap">
                  {dateTime(row.last_activity)}
                </span>
              ),
            },
            {
              key: "terminals",
              label: "Терминалы",
              sortValue: (row) => row.active_terminals,
              render: (row) => row.active_terminals,
            },
            {
              key: "today",
              label: "Событий сегодня",
              sortValue: (row) => row.today_actions,
              render: (row) => number(row.today_actions),
            },
            {
              key: "open",
              label: "История",
              render: (row) => (
                <Button size="sm" onClick={() => onUser(row.user_id)}>
                  События
                </Button>
              ),
            },
          ]}
        />
        <div className="gov-row-actions">
          <CheckField
            label="Обновлять каждые 30 секунд"
            checked={live}
            onChange={setLive}
          />
          <span className="muted text-sm">
            Проверено: {dateTime(new Date(query.dataUpdatedAt).toISOString())}
          </span>
        </div>
      </Panel>
    </>
  );
}

function EventsPanel() {
  const [params, setParams] = useSearchParams();
  const [selected, setSelected] = useState<ActivityEvent | null>(null);
  const days = bounded(params.get("days"), 7, 1, 90);
  const offset = bounded(
    params.get("offset"),
    0,
    0,
    Number.MAX_SAFE_INTEGER - 50,
  );
  const userId = bounded(params.get("user_id"), 0, 0, Number.MAX_SAFE_INTEGER);
  const category = params.get("category") ?? "";
  const search = params.get("search") ?? "";
  const queryParams = new URLSearchParams({
    days: String(days),
    offset: String(offset),
    limit: "50",
  });
  if (userId) queryParams.set("user_id", String(userId));
  if (category) queryParams.set("category", category);
  if (search) queryParams.set("search", search);
  const query = useQuery({
    queryKey: ["governance", "user-activity", queryParams.toString()],
    queryFn: ({ signal }) => adminActivityApi.events(queryParams, signal),
  });
  const canAudit = usePermission("settings");
  const paginate = (next: number) => {
    const values = new URLSearchParams(params);
    values.set("offset", String(next));
    setParams(values);
  };
  return (
    <>
      <Panel
        title="События пользователей"
        description="История зарегистрированных действий по всей платформе, до 90 дней."
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
        <form
          key={`${userId}:${days}:${category}:${search}`}
          className="gov-activity-filters"
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            const next = new URLSearchParams({ view: "events" });
            for (const key of ["search", "days", "category", "user_id"]) {
              const value = String(form.get(key) ?? "").trim();
              if (value) next.set(key, value);
            }
            setParams(next);
          }}
        >
          <FormField label="Поиск событий">
            {(id) => (
              <input
                id={id}
                name="search"
                defaultValue={search}
                placeholder="Пользователь, действие, описание"
              />
            )}
          </FormField>
          <FormField label="Период">
            {(id) => (
              <select id={id} name="days" defaultValue={days}>
                {[1, 7, 14, 30, 90].map((value) => (
                  <option key={value} value={value}>
                    {value} дн.
                  </option>
                ))}
              </select>
            )}
          </FormField>
          <FormField label="ID пользователя">
            {(id) => (
              <input
                id={id}
                name="user_id"
                type="number"
                min={1}
                step={1}
                defaultValue={userId || ""}
                placeholder="Все пользователи"
              />
            )}
          </FormField>
          <FormField label="Категория">
            {(id) => (
              <input
                id={id}
                name="category"
                defaultValue={category}
                placeholder="Все категории"
              />
            )}
          </FormField>
          <Button type="submit">Применить</Button>
          <Button variant="ghost" onClick={() => setParams({ view: "events" })}>
            Сбросить
          </Button>
        </form>
        {query.isPending ? (
          <LoadingState />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : (
          <>
            <DataTable
              rows={query.data.events}
              rowKey={(row) => row.id}
              pageSize={50}
              emptyTitle="Событий по этим фильтрам нет"
              emptyDescription="Увеличьте период или уточните условия поиска."
              columns={[
                {
                  key: "time",
                  label: "Время",
                  render: (row) => (
                    <span className="gov-nowrap">
                      {dateTime(row.created_at)}
                    </span>
                  ),
                },
                {
                  key: "user",
                  label: "Пользователь",
                  render: (row) => (
                    <div>
                      <strong>{row.username}</strong>
                      {row.user_id && (
                        <small className="gov-subline">ID {row.user_id}</small>
                      )}
                    </div>
                  ),
                },
                {
                  key: "action",
                  label: "Действие",
                  render: (row) => (
                    <button
                      className="gov-cell-button"
                      onClick={() => setSelected(row)}
                    >
                      <strong>{row.action}</strong>
                      <small>{row.description || row.category}</small>
                    </button>
                  ),
                },
                {
                  key: "entity",
                  label: "Объект",
                  render: (row) => row.entity_name || row.entity_type || "—",
                },
                {
                  key: "status",
                  label: "Результат",
                  render: (row) => (
                    <StatusBadge status={row.status}>
                      {row.status === "info" ? "Информация" : undefined}
                    </StatusBadge>
                  ),
                },
                {
                  key: "details",
                  label: "Подробности",
                  render: (row) => (
                    <Button size="sm" onClick={() => setSelected(row)}>
                      Открыть
                    </Button>
                  ),
                },
              ]}
            />
            <div className="gov-audit-pagination">
              <span>
                Всего {number(query.data.total)} событий · страница{" "}
                {Math.floor(offset / 50) + 1}
              </span>
              <div>
                <Button
                  size="sm"
                  disabled={!offset}
                  onClick={() => paginate(Math.max(0, offset - 50))}
                >
                  <ChevronLeft size={15} />
                  Назад
                </Button>
                <Button
                  size="sm"
                  disabled={offset + 50 >= query.data.total}
                  onClick={() => paginate(offset + 50)}
                >
                  Далее
                  <ChevronRight size={15} />
                </Button>
              </div>
            </div>
          </>
        )}
      </Panel>
      <Drawer
        open={!!selected}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
        title={selected?.action ?? "Событие"}
        description={selected ? dateTime(selected.created_at) : undefined}
      >
        {selected && (
          <>
            <StatusBadge status={selected.status} />
            <p className="gov-event-description">
              {selected.description || "Описание не указано."}
            </p>
            {selected.description.length >= 300 && (
              <p className="muted text-sm">
                Показаны первые 300 символов описания.
              </p>
            )}
            <dl className="gov-details">
              {[
                ["Пользователь", selected.username],
                ["ID пользователя", selected.user_id],
                ["Категория", selected.category],
                ["Объект", selected.entity_name],
                ["Тип объекта", selected.entity_type],
                ["IP-адрес", selected.ip_address],
              ].map(([label, value]) => (
                <div key={String(label)}>
                  <dt>{label}</dt>
                  <dd>{value || "—"}</dd>
                </div>
              ))}
            </dl>
            {canAudit && (
              <Link
                to={`/governance/audit?search=${encodeURIComponent(selected.action)}${selected.user_id ? `&user_id=${selected.user_id}` : ""}`}
                className="btn btn-secondary"
              >
                Открыть журнал аудита
              </Link>
            )}
          </>
        )}
      </Drawer>
    </>
  );
}

function ActivityTrends({ data }: { data: AdminUsage }) {
  return (
    <div className="gov-policy-grid gov-activity-trends">
      <Panel
        title="Пользователи за 7 дней"
        description="До 10 пользователей по количеству зарегистрированных событий."
      >
        <DataTable
          rows={data.top_users}
          rowKey={(row) => row.username}
          pageSize={10}
          emptyTitle="За неделю событий нет"
          columns={[
            {
              key: "name",
              label: "Пользователь",
              render: (row) => row.username,
            },
            {
              key: "total",
              label: "События",
              sortValue: (row) => row.total,
              render: (row) => number(row.total),
            },
            {
              key: "ai",
              label: "AI-действия",
              render: (row) => number(row.ai_requests),
            },
            {
              key: "terminal",
              label: "События терминала",
              render: (row) => number(row.terminal_sessions),
            },
          ]}
        />
      </Panel>
      <Panel
        title="Активность за 24 часа"
        description="Количество событий по часам. Время отображается в вашем часовом поясе."
      >
        <DataTable
          rows={data.hourly_activity}
          rowKey={(row) => row.hour}
          pageSize={24}
          emptyTitle="За сутки событий нет"
          columns={[
            { key: "hour", label: "Час", render: (row) => dateTime(row.hour) },
            {
              key: "count",
              label: "Событий",
              render: (row) => (
                <div className="gov-hour-count">
                  <span>{number(row.count)}</span>
                  <meter
                    min={0}
                    max={Math.max(
                      1,
                      ...data.hourly_activity.map((item) => item.count),
                    )}
                    value={row.count}
                    aria-label={`${dateTime(row.hour)}: ${row.count} событий`}
                  />
                </div>
              ),
            },
          ]}
        />
      </Panel>
    </div>
  );
}

function UsagePanel() {
  const [selected, setSelected] = useState<
    (ProviderUsage & { provider: string }) | null
  >(null);
  const query = useQuery({
    queryKey: ["governance", "admin-usage"],
    queryFn: ({ signal }) => adminActivityApi.usage(signal),
    staleTime: 60_000,
  });
  if (query.isPending)
    return <LoadingState label="Получаем статистику использования…" />;
  if (query.error)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  const data = query.data;
  const rows = Object.entries(data.api_usage).map(([provider, usage]) => ({
    provider,
    ...usage,
  }));
  const actual = rows.filter((row) => row.actual_spend_usd != null);
  return (
    <>
      <div className="gov-metrics">
        <Metric
          label="API-вызовы сегодня"
          value={number(data.api_calls_today)}
        />
        <Metric
          label="Ошибки и таймауты"
          value={number(rows.reduce((sum, row) => sum + row.errors, 0))}
        />
        <Metric
          label="Оценка по токенам"
          value={usd(
            rows.reduce((sum, row) => sum + row.estimated_cost_usd, 0),
          )}
          detail="Локальные счётчики за сегодня"
        />
        <Metric
          label="Расход по данным провайдеров"
          value={
            actual.length
              ? usd(
                  actual.reduce(
                    (sum, row) => sum + (row.actual_spend_usd ?? 0),
                    0,
                  ),
                )
              : "Нет данных"
          }
          detail={`Данные доступны: ${actual.length} из ${rows.length} провайдеров`}
        />
      </div>
      <Panel
        title="Использование AI"
        description="Локальная статистика за день сервера. Фактические расходы поступают из подключённого биллинга провайдеров за день UTC и могут включать другие приложения аккаунта."
        actions={
          <Button
            size="sm"
            loading={query.isFetching}
            onClick={() => void query.refetch()}
          >
            <RefreshCw size={14} />
            Обновить
          </Button>
        }
      >
        <DataTable
          rows={rows}
          rowKey={(row) => row.provider}
          pageSize={10}
          emptyTitle="Статистика провайдеров отсутствует"
          columns={[
            {
              key: "provider",
              label: "Провайдер",
              render: (row) => (
                <button
                  className="gov-cell-button"
                  onClick={() => setSelected(row)}
                >
                  <strong>{row.provider}</strong>
                  <small>
                    {data.providers[row.provider]?.enabled
                      ? data.providers[row.provider]?.model || "Включён"
                      : "Отключён в настройках"}
                  </small>
                </button>
              ),
            },
            {
              key: "calls",
              label: "Вызовы",
              sortValue: (row) => row.calls,
              render: (row) => number(row.calls),
            },
            {
              key: "tokens",
              label: "Токены: вход / выход",
              render: (row) =>
                `${number(row.input_tokens)} / ${number(row.output_tokens)}`,
            },
            {
              key: "errors",
              label: "Ошибки",
              render: (row) => number(row.errors),
            },
            {
              key: "estimated",
              label: "Оценка, USD",
              render: (row) => usd(row.estimated_cost_usd),
            },
            {
              key: "actual",
              label: "Факт, USD",
              render: (row) => usd(row.actual_spend_usd),
            },
            {
              key: "balance",
              label: "Баланс, USD",
              render: (row) => usd(row.balance_usd),
            },
            {
              key: "details",
              label: "Источник",
              render: (row) => (
                <Button size="sm" onClick={() => setSelected(row)}>
                  Подробности
                </Button>
              ),
            },
          ]}
        />
        <p className="muted text-sm">
          Оценка использует общие коэффициенты платформы и не учитывает точный
          тариф модели. Биллинг обновляется с кэшем сервера; отсутствие данных
          не означает нулевой расход.
        </p>
      </Panel>
      <ActivityTrends data={data} />
      <Panel
        title="Зарегистрированные терминальные подключения"
        description="Подключения со статусом connected в реестре платформы. Это снимок реестра на момент запроса."
      >
        <DataTable
          rows={data.terminals.connections.map((row, index) => ({
            ...row,
            index,
          }))}
          rowKey={(row) => row.index}
          pageSize={10}
          emptyTitle="Активных подключений в реестре нет"
          columns={[
            { key: "server", label: "Сервер", render: (row) => row.server },
            { key: "user", label: "Пользователь", render: (row) => row.user },
            {
              key: "time",
              label: "Подключён",
              render: (row) => dateTime(row.connected_at),
            },
          ]}
        />
      </Panel>
      <Drawer
        open={!!selected}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
        title={selected ? `Биллинг: ${selected.provider}` : "Биллинг"}
      >
        {selected && (
          <>
            <dl className="gov-details">
              {[
                ["Оценка", usd(selected.estimated_cost_usd)],
                ["Фактический расход", usd(selected.actual_spend_usd)],
                ["Баланс", usd(selected.balance_usd)],
                ["Источник данных", selected.billing_source],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <p className="gov-event-description">
              {selected.billing_note ||
                "Провайдер не передал дополнительных сведений."}
            </p>
          </>
        )}
      </Drawer>
    </>
  );
}

function ActivityContent() {
  const [params, setParams] = useSearchParams();
  const view = ["users", "events", "usage"].includes(params.get("view") ?? "")
    ? params.get("view")!
    : "users";
  return (
    <>
      <PageHeader
        eyebrow="Управление платформой"
        title="Активность пользователей"
        description="События, терминальные подключения и использование AI по всей платформе."
      />
      <Tabs
        value={view}
        onChange={(value) => {
          const next = new URLSearchParams(params);
          next.set("view", value);
          setParams(next);
        }}
        items={[
          { value: "users", label: "Пользователи" },
          { value: "events", label: "События" },
          { value: "usage", label: "Использование AI" },
        ]}
      />
      {view === "users" ? (
        <ActiveUsersPanel
          onUser={(id) => setParams({ view: "events", user_id: String(id) })}
        />
      ) : view === "events" ? (
        <EventsPanel />
      ) : view === "usage" ? (
        <UsagePanel />
      ) : (
        <EmptyState
          title="Выберите представление"
          icon={<Activity size={24} />}
        />
      )}
    </>
  );
}
export function AdminActivityPage() {
  return (
    <GovernanceGuard staff feature="dashboard">
      <ActivityContent />
    </GovernanceGuard>
  );
}
