import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, Download, RefreshCw } from "lucide-react";
import { governanceApi, type AuditEvent } from "@/api/governance";
import {
  Button,
  DataTable,
  Drawer,
  ErrorState,
  JsonDetails,
  LoadingState,
  Metric,
  PageHeader,
  Panel,
  StatusBadge,
} from "@/components/ui";
import { FormField, GovernanceGuard, dateTime } from "./shared";

function AuditContent() {
  const [params, setParams] = useSearchParams();
  const [selected, setSelected] = useState<AuditEvent | null>(null);
  const [search, setSearch] = useState(params.get("search") ?? "");
  const queryParams = new URLSearchParams(params);
  queryParams.set("limit", "50");
  const query = useQuery({
    queryKey: ["governance", "audit", queryParams.toString()],
    queryFn: ({ signal }) => governanceApi.audit(queryParams, signal),
  });
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "offset") next.delete("offset");
    setParams(next);
  };
  const exportUrl = (format: string) => {
    const next = new URLSearchParams(queryParams);
    next.set("format", format);
    return `/api/settings/activity/?${next}`;
  };
  const offset = Number(params.get("offset") ?? 0);
  return (
    <>
      <PageHeader
        eyebrow="Управление"
        title="Журнал аудита"
        description="Действия пользователей и изменения платформы с контекстом и результатом."
        actions={
          <>
            <a
              className="btn btn-secondary btn-md"
              href={exportUrl("csv")}
              download
            >
              <Download size={15} />
              CSV
            </a>
            <a
              className="btn btn-secondary btn-md"
              href={exportUrl("syslog")}
              download
            >
              Syslog
            </a>
            <Button
              aria-label="Обновить журнал"
              onClick={() => void query.refetch()}
              loading={query.isFetching}
            >
              <RefreshCw size={15} />
            </Button>
          </>
        }
      />
      {query.data && (
        <div className="gov-metrics">
          <Metric label="События" value={query.data.summary.total_events} />
          <Metric label="Пользователи" value={query.data.summary.total_users} />
          <Metric label="Входы" value={query.data.summary.login_count} />
          <Metric
            label="Изменения серверов"
            value={query.data.summary.server_changes}
          />
        </div>
      )}
      <Panel>
        <form
          className="gov-audit-filters"
          onSubmit={(e) => {
            e.preventDefault();
            set("search", search);
          }}
        >
          <FormField label="Поиск по событиям">
            {(id) => (
              <input
                id={id}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Действие, пользователь или объект"
              />
            )}
          </FormField>
          <FormField label="Период">
            {(id) => (
              <select
                id={id}
                value={params.get("days") ?? "14"}
                onChange={(e) => set("days", e.target.value)}
              >
                {[1, 7, 14, 30, 90, 365].map((days) => (
                  <option key={days} value={days}>
                    {days} дн.
                  </option>
                ))}
              </select>
            )}
          </FormField>
          <FormField label="Пользователь">
            {(id) => (
              <select
                id={id}
                value={params.get("user_id") ?? ""}
                onChange={(e) => set("user_id", e.target.value)}
              >
                <option value="">Все пользователи</option>
                {query.data?.users.map((user) => (
                  <option value={user.id} key={user.id}>
                    {user.username}
                  </option>
                ))}
              </select>
            )}
          </FormField>
          <FormField label="Категория">
            {(id) => (
              <select
                id={id}
                value={params.get("category") ?? ""}
                onChange={(e) => set("category", e.target.value)}
              >
                <option value="">Все категории</option>
                {[
                  "auth",
                  "security",
                  "servers",
                  "terminal",
                  "settings",
                  "plugins",
                  "ai",
                  "agents",
                  "pipeline",
                  "files",
                  "mcp",
                ].map((category) => (
                  <option value={category} key={category}>
                    {category}
                  </option>
                ))}
              </select>
            )}
          </FormField>
          <FormField label="Результат">
            {(id) => (
              <select
                id={id}
                value={params.get("status") ?? ""}
                onChange={(e) => set("status", e.target.value)}
              >
                <option value="">Все результаты</option>
                <option value="success">Успешно</option>
                <option value="error">Ошибка</option>
                <option value="warning">Предупреждение</option>
                <option value="info">Информация</option>
              </select>
            )}
          </FormField>
          <Button type="submit">Найти</Button>
          {params.size > 0 && (
            <Button
              variant="ghost"
              onClick={() => {
                setSearch("");
                setParams({});
              }}
            >
              Сбросить
            </Button>
          )}
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
              emptyTitle="За выбранный период событий нет"
              emptyDescription="Попробуйте увеличить период или изменить фильтры."
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
                  render: (row) => <strong>{row.username}</strong>,
                },
                {
                  key: "action",
                  label: "Событие",
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
                  render: (row) => <StatusBadge status={row.status} />,
                },
                {
                  key: "detail",
                  label: "Подробности",
                  render: (row) => (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setSelected(row)}
                    >
                      Открыть
                    </Button>
                  ),
                },
              ]}
            />
            <div className="gov-audit-pagination">
              <span>
                Всего {query.data.paging.total} событий · экспорт до 5000
                событий
              </span>
              <div>
                <Button
                  size="sm"
                  disabled={offset === 0}
                  onClick={() =>
                    set("offset", String(Math.max(0, offset - 50)))
                  }
                >
                  <ChevronLeft size={15} />
                  Назад
                </Button>
                <Button
                  size="sm"
                  disabled={!query.data.paging.has_more}
                  onClick={() => set("offset", String(offset + 50))}
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
        wide
      >
        {selected && (
          <>
            <StatusBadge status={selected.status} />
            <p>{selected.description}</p>
            <dl className="gov-details">
              {[
                ["Пользователь", selected.username],
                ["Категория", selected.category],
                ["Объект", selected.entity_name],
                ["Тип объекта", selected.entity_type],
                ["Идентификатор", selected.entity_id],
                ["IP-адрес", selected.ip_address],
                ["Клиент", selected.user_agent],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value || "—"}</dd>
                </div>
              ))}
            </dl>
            <JsonDetails data={selected.metadata} label="Контекст события" />
          </>
        )}
      </Drawer>
    </>
  );
}
export function AuditPage() {
  return (
    <GovernanceGuard staff>
      <AuditContent />
    </GovernanceGuard>
  );
}
