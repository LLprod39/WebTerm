import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Plus, RefreshCw, Server, Terminal } from "lucide-react";
import { infrastructureApi, type ServerRow } from "@/api/infrastructure";
import {
  Button,
  DataTable,
  ErrorState,
  PageHeader,
  Panel,
  Skeleton,
  Tabs,
} from "@/components/ui";
import { formatDate } from "@/lib/utils";
import { ServerForm } from "./ServerForm";
import { ServerGroups } from "./ServerGroups";
export default function ServersPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "groups" ? "groups" : "servers";
  const setTab = (value: string) => {
    const next = new URLSearchParams(params);
    next.set("tab", value);
    setParams(next, { replace: true });
  };
  const [group, setGroup] = useState("all");
  const query = useQuery({
    queryKey: ["servers"],
    queryFn: ({ signal }) => infrastructureApi.bootstrap(signal),
  });
  const data = query.data;
  const rows = (data?.servers ?? []).filter(
    (s) => group === "all" || String(s.group_id ?? "none") === group,
  );
  const create = params.get("create") === "1";
  const setCreate = (open: boolean) => {
    const next = new URLSearchParams(params);
    if (open) next.set("create", "1");
    else {
      next.delete("create");
      next.delete("server_group");
    }
    setParams(next, { replace: true });
  };
  return (
    <>
      <PageHeader
        title="Серверы"
        actions={
          <>
            <Button
              onClick={() => void query.refetch()}
              loading={query.isFetching}
              variant="ghost"
              size="icon"
              aria-label="Обновить список серверов"
              title="Обновить список серверов"
            >
              <RefreshCw size={14} />
            </Button>
            {tab === "servers" && (
              <Button variant="primary" onClick={() => setCreate(true)}>
                <Plus size={15} />
                Добавить сервер
              </Button>
            )}
          </>
        }
      />
      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { value: "servers", label: "Все серверы", count: data?.stats.total },
          { value: "groups", label: "Группы" },
        ]}
      />
      {query.error && (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      )}
      {query.isPending ? (
        <Panel>
          <Skeleton />
        </Panel>
      ) : !data ? null : tab === "groups" ? (
        <ServerGroups
          groups={data?.groups ?? []}
          servers={data?.servers ?? []}
        />
      ) : (
        <Panel>
          <DataTable<ServerRow>
            rows={rows}
            rowKey={(r) => r.id}
            hideSinglePagePagination
            searchValue={(r) =>
              `${r.name} ${r.host} ${r.username} ${r.group_name}`
            }
            searchPlaceholder="Поиск по имени или адресу…"
            emptyTitle={
              group === "all"
                ? "Добавьте первый сервер"
                : "В этой группе нет доступных серверов"
            }
            emptyDescription={
              group === "all"
                ? "Добавьте SSH-подключение, чтобы открыть терминал и работать с файлами."
                : "Выберите другую группу или сбросьте фильтр."
            }
            toolbar={
              data.groups.length > 1 || group !== "all" ? (
                <>
                  <select
                    aria-label="Фильтр по группе"
                    value={group}
                    onChange={(e) => setGroup(e.target.value)}
                  >
                    <option value="all">Все группы</option>
                    {data?.groups.map((g) => (
                      <option key={g.id ?? "none"} value={g.id ?? "none"}>
                        {g.name === "Ungrouped" ? "Без группы" : g.name}
                      </option>
                    ))}
                  </select>
                  {group !== "all" && (
                    <Button variant="ghost" onClick={() => setGroup("all")}>
                      Сбросить фильтр
                    </Button>
                  )}
                </>
              ) : undefined
            }
            columns={[
              {
                key: "name",
                label: "Сервер",
                sortValue: (s) => s.name,
                render: (s) => (
                  <div className="table-name">
                    <span className="table-icon">
                      <Server size={16} />
                    </span>
                    <div>
                      <Link to={`/infrastructure/servers/${s.id}`}>
                        {s.name}
                      </Link>
                      {s.is_shared && <small>Общий доступ</small>}
                      {(s.detected_os_pretty ||
                        (s.detected_os !== "unknown" && s.detected_os)) && (
                        <small>{s.detected_os_pretty || s.detected_os}</small>
                      )}
                    </div>
                  </div>
                ),
              },
              {
                key: "host",
                label: "Адрес SSH",
                sortValue: (s) => s.host,
                render: (s) => (
                  <div className="mono text-sm">
                    {s.username}@{s.host}:{s.port}
                  </div>
                ),
              },
              {
                key: "group",
                label: "Группа",
                sortValue: (s) => s.group_name,
                render: (s) => (
                  <span className="badge">
                    {s.group_name === "Ungrouped" ? "Без группы" : s.group_name}
                  </span>
                ),
              },
              {
                key: "connected",
                label: "Последнее подключение",
                sortValue: (s) => Date.parse(s.last_connected ?? "") || 0,
                render: (s) => (
                  <span className="text-sm muted">
                    {s.last_connected
                      ? formatDate(s.last_connected)
                      : "Не подключались"}
                  </span>
                ),
              },
              {
                key: "actions",
                label: "Терминал",
                className: "table-actions-col",
                render: (s) =>
                  (s.can_connect_terminal ?? s.can_edit) ? (
                    <Link
                      className="btn btn-secondary btn-sm"
                      to={`/infrastructure/terminal/${s.id}`}
                      aria-label={`Подключиться к ${s.name}`}
                    >
                      <Terminal size={14} /> Подключиться
                    </Link>
                  ) : (
                    <span className="muted text-sm">
                      Нет доступа к терминалу
                    </span>
                  ),
              },
            ]}
          />
        </Panel>
      )}
      <ServerForm
        open={create}
        onOpenChange={setCreate}
        groups={data?.groups ?? []}
        defaultGroupId={params.get("server_group") ?? ""}
      />
    </>
  );
}
