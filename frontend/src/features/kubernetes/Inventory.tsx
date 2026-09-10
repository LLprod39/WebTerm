import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, RefreshCw, Settings2 } from "lucide-react";
import {
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  Field,
  JsonDetails,
  LoadingState,
  Metric,
  PageHeader,
  Panel,
  Tabs,
} from "@/components/ui";
import { useSession } from "@/app/session";
import { formatDate } from "@/lib/utils";
import { kubernetesApi, type KubeData } from "@/api/kubernetes";
import {
  kubeBase,
  KubeNav,
  KubeEvents,
  KubeFacts,
  KubeStatus,
  obj,
  rows,
  str,
  useKubeCapabilities,
} from "./common";

function itemPath(item: KubeData, kind: string) {
  if (kind === "namespaces")
    return `${kubeBase}/clusters/${encodeURIComponent(str(item.cluster_id))}/namespaces/${encodeURIComponent(str(item.id, item.name ? str(item.name) : ""))}`;
  if (str(item.id).startsWith("app_")) return "";
  return `${kubeBase}/resources/${kind}/${encodeURIComponent(str(item.id))}`;
}
function ItemTable({ items, kind }: { items: KubeData[]; kind: string }) {
  return (
    <DataTable
      rows={items}
      rowKey={(r) => str(r.id, r.name ? str(r.name) : "")}
      searchValue={(r) => `${str(r.name)} ${str(r.namespace)} ${str(r.kind)}`}
      emptyTitle="Ресурсы не найдены"
      emptyDescription="Проверьте выбранное пространство имён и время последней синхронизации."
      columns={[
        {
          key: "name",
          label: "Ресурс",
          render: (r) => (
            <div>
              {itemPath(r, kind) ? (
                <Link className="kube-item-name" to={itemPath(r, kind)}>
                  {str(r.name)}
                </Link>
              ) : (
                <strong>{str(r.name)}</strong>
              )}
              <p className="muted">
                {str(
                  r.kind,
                  r.owner ? str(r.owner) : kind === "pods" ? "Pod" : "",
                )}
              </p>
            </div>
          ),
        },
        {
          key: "namespace",
          label: "Пространство имён",
          render: (r) => str(r.namespace),
        },
        {
          key: "health",
          label: "Состояние",
          render: (r) => <KubeStatus value={r.health || r.phase} />,
        },
        {
          key: "ready",
          label: "Готовность",
          render: (r) =>
            r.ready_containers !== undefined
              ? `${str(r.ready_containers)}/${str(r.total_containers)} контейнеров`
              : r.ready !== undefined
                ? `${str(r.ready)}/${str(r.desired)} реплик`
                : kind === "namespaces"
                  ? `${str(r.workloads, "0")} нагрузок`
                  : str(r.service_type),
        },
        {
          key: "sync",
          label: "Обновлено",
          render: (r) => formatDate(str(r.last_sync_at, "")),
        },
      ]}
    />
  );
}
export function ClustersPage() {
  const { user } = useSession();
  const q = useQuery({
    queryKey: ["kubernetes", "clusters"],
    queryFn: kubernetesApi.clusters,
  });
  const items = q.data?.clusters || [];
  return (
    <>
      <PageHeader
        eyebrow="Инфраструктура"
        title="Kubernetes"
        description="Состояние кластеров, рабочие нагрузки и контролируемый доступ к ресурсам."
        actions={
          <Button onClick={() => q.refetch()} loading={q.isFetching}>
            <RefreshCw size={16} /> Обновить
          </Button>
        }
      />
      <KubeNav />
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} retry={() => q.refetch()} />
      ) : (
        <div className="stack">
          <div className="kube-grid">
            <Metric label="Кластеры" value={items.length} />
            <Metric
              label="В норме"
              value={items.filter((c) => c.health === "healthy").length}
            />
            <Metric
              label="Готовые узлы"
              value={`${items.reduce((n, c) => n + c.nodes_ready, 0)}/${items.reduce((n, c) => n + c.nodes_total, 0)}`}
            />
            <Metric
              label="Рабочие нагрузки"
              value={items.reduce((n, c) => n + c.workloads, 0)}
            />
          </div>
          <Panel
            title="Кластеры"
            description="Данные последней синхронизации с Rancher и Devtron."
          >
            <DataTable
              rows={items}
              rowKey={(r) => r.id}
              searchValue={(r) => `${r.name} ${r.environment} ${r.provider}`}
              emptyTitle="Кластеры пока не подключены"
              emptyDescription="Настройте провайдер и синхронизируйте инвентарь."
              emptyAction={
                user?.is_staff ? (
                  <Link
                    className="btn btn-primary btn-md"
                    to={`${kubeBase}/providers`}
                  >
                    Подключить провайдер
                  </Link>
                ) : undefined
              }
              columns={[
                {
                  key: "name",
                  label: "Кластер",
                  render: (r) => (
                    <Link
                      className="kube-item-name"
                      to={`${kubeBase}/clusters/${r.id}`}
                    >
                      {r.name}
                    </Link>
                  ),
                },
                {
                  key: "env",
                  label: "Окружение",
                  render: (r) => r.environment || "—",
                },
                {
                  key: "health",
                  label: "Состояние",
                  render: (r) => <KubeStatus value={r.health} />,
                },
                {
                  key: "nodes",
                  label: "Узлы",
                  render: (r) => `${r.nodes_ready} / ${r.nodes_total}`,
                },
                {
                  key: "sync",
                  label: "Синхронизация",
                  render: (r) => (
                    <>
                      <KubeStatus value={r.sync_status} />
                      <p className="muted">{formatDate(r.last_sync_at)}</p>
                    </>
                  ),
                },
                {
                  key: "open",
                  label: "",
                  render: (r) => (
                    <Link
                      aria-label={`Открыть ${r.name}`}
                      to={`${kubeBase}/clusters/${r.id}`}
                    >
                      <ArrowRight size={16} />
                    </Link>
                  ),
                },
              ]}
            />
          </Panel>
        </div>
      )}
    </>
  );
}
export function ClusterPage() {
  const { id = "" } = useParams();
  const [tab, setTab] = useState("namespaces");
  const [namespace, setNamespace] = useState("");
  const q = useQuery({
    queryKey: ["kubernetes", "cluster", id],
    queryFn: () => kubernetesApi.cluster(id),
  });
  const namespaces = useQuery({
    queryKey: ["kubernetes", "inventory", id, "namespaces"],
    queryFn: () => kubernetesApi.inventory(id, "namespaces"),
  });
  const data = useQuery({
    queryKey: ["kubernetes", "inventory", id, tab],
    queryFn: () => kubernetesApi.inventory(id, tab),
  });
  const c = q.data?.cluster;
  const items = rows(
    data.data?.[tab === "network" ? "network_refs" : tab],
  ).filter(
    (r) =>
      !namespace ||
      r.namespace === namespace ||
      (tab === "namespaces" && r.name === namespace),
  );
  return (
    <>
      <PageHeader
        title={c?.name || "Кластер"}
        eyebrow="Kubernetes"
        description={
          c
            ? `${c.environment || "Без окружения"} · синхронизация ${formatDate(c.last_sync_at)}`
            : undefined
        }
        actions={
          <Link
            className="btn btn-secondary btn-md"
            to={`${kubeBase}/sessions?cluster=${id}`}
          >
            <Settings2 size={16} /> Сессии доступа
          </Link>
        }
      />
      <KubeNav />
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : (
        c && (
          <div className="stack">
            <div className="kube-grid">
              <Metric
                label="Узлы"
                value={`${c.nodes_ready} / ${c.nodes_total}`}
              />
              <Metric label="Пространства имён" value={c.namespaces} />
              <Metric label="Рабочие нагрузки" value={c.workloads} />
              <Metric
                label="Состояние"
                value={<KubeStatus value={c.health} />}
              />
            </div>
            <div className="kube-toolbar">
              <Field label="Пространство имён" htmlFor="kube-namespace">
                <select
                  id="kube-namespace"
                  value={namespace}
                  onChange={(e) => setNamespace(e.target.value)}
                >
                  <option value="">Все пространства</option>
                  {rows(namespaces.data?.namespaces).map((n) => (
                    <option
                      key={str(n.id, n.name ? str(n.name) : "")}
                      value={str(n.name, "")}
                    >
                      {str(n.name)}
                    </option>
                  ))}
                </select>
              </Field>
              <Button loading={data.isFetching} onClick={() => data.refetch()}>
                <RefreshCw size={16} /> Обновить
              </Button>
            </div>
            <Tabs
              value={tab}
              onChange={setTab}
              items={[
                { value: "namespaces", label: "Пространства имён" },
                { value: "workloads", label: "Нагрузки" },
                { value: "pods", label: "Pods" },
                { value: "network", label: "Сеть" },
                { value: "events", label: "События" },
              ]}
            />
            {data.isPending ? (
              <LoadingState />
            ) : data.error ? (
              <ErrorState error={data.error} retry={() => data.refetch()} />
            ) : (
              <Panel title={tab === "events" ? "События" : "Инвентарь"}>
                {tab === "events" ? (
                  <KubeEvents events={items} />
                ) : (
                  <ItemTable
                    items={items.map((r) => ({
                      ...r,
                      cluster_id: r.cluster_id || id,
                    }))}
                    kind={tab}
                  />
                )}
              </Panel>
            )}
          </div>
        )
      )}
    </>
  );
}
export function InventoryDetailPage() {
  const { id = "", kind = "", clusterId = "" } = useParams();
  const actualKind = clusterId ? "namespaces" : kind;
  const [tab, setTab] = useState("overview");
  const [tail, setTail] = useState(200);
  const q = useQuery({
    queryKey: ["kubernetes", "detail", actualKind, id, clusterId],
    queryFn: () =>
      clusterId
        ? kubernetesApi.namespace(clusterId, id)
        : kubernetesApi.detail(kind, id),
  });
  const logs = useQuery({
    queryKey: ["kubernetes", "pod-logs", id, tail],
    queryFn: () => kubernetesApi.podLogs(id, tail),
    enabled: actualKind === "pods" && tab === "logs",
  });
  const d = q.data || {};
  const item = obj(
    d[
      actualKind === "namespaces"
        ? "namespace"
        : actualKind === "workloads"
          ? "workload"
          : actualKind === "pods"
            ? "pod"
            : "network"
    ] || d.network_ref,
  );
  const c = obj(d.cluster);
  return (
    <>
      <PageHeader
        eyebrow={str(item.kind, actualKind)}
        title={str(item.name, "Ресурс")}
        description={`${str(c.name)} · ${str(item.namespace, item.name ? str(item.name) : "")}`}
        actions={
          c.id ? (
            <Link
              className="btn btn-secondary btn-md"
              to={`${kubeBase}/clusters/${str(c.id)}`}
            >
              Кластер
            </Link>
          ) : undefined
        }
      />
      <KubeNav />
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} retry={() => q.refetch()} />
      ) : (
        <div className="stack">
          <Tabs
            value={tab}
            onChange={setTab}
            items={[
              { value: "overview", label: "Обзор" },
              { value: "events", label: "События" },
              ...(actualKind === "pods"
                ? [{ value: "logs", label: "Логи" }]
                : []),
              { value: "metadata", label: "Метаданные" },
            ]}
          />
          {tab === "overview" && (
            <>
              <Panel
                title="Состояние"
                actions={<KubeStatus value={item.health || item.phase} />}
              >
                <div className="section-body">
                  <KubeFacts
                    data={item}
                    fields={[
                      ["name", "Имя"],
                      ["namespace", "Пространство имён"],
                      ["kind", "Тип"],
                      ["owner", "Владелец"],
                      ["owner_name", "Родитель"],
                      ["node_name", "Узел"],
                      ["pod_ip", "IP pod"],
                      ["restart_count", "Перезапуски"],
                      ["version", "Версия"],
                    ]}
                  />
                  <p className="muted">
                    Обновлено {formatDate(str(item.last_sync_at, ""))}
                  </p>
                </div>
              </Panel>
              {[
                ["workloads", "Нагрузки", "workloads"],
                ["owner_workloads", "Родительские нагрузки", "workloads"],
                ["pods", "Pods", "pods"],
                ["sibling_pods", "Связанные pods", "pods"],
                ["network_refs", "Сетевые ресурсы", "network"],
              ].map(
                ([key, label, k]) =>
                  rows(d[key]).length > 0 && (
                    <Panel title={label} key={key}>
                      <ItemTable items={rows(d[key])} kind={k} />
                    </Panel>
                  ),
              )}
            </>
          )}
          {tab === "events" && (
            <Panel title="События ресурса">
              <KubeEvents events={rows(d.events)} />
            </Panel>
          )}
          {tab === "metadata" && (
            <Panel title="Метки и метаданные">
              <div className="section-body">
                <KubeFacts
                  data={obj(item.labels)}
                  fields={Object.keys(obj(item.labels)).map((k) => [k, k])}
                />
                <JsonDetails data={d.summary} label="Сводка инвентаря" />
              </div>
            </Panel>
          )}
          {tab === "logs" && (
            <Panel
              title="Снимок логов"
              actions={
                <Button
                  onClick={() => logs.refetch()}
                  loading={logs.isFetching}
                >
                  Обновить
                </Button>
              }
            >
              <div className="section-body stack">
                <Field label="Количество строк" htmlFor="kube-tail">
                  <select
                    id="kube-tail"
                    value={tail}
                    onChange={(e) => setTail(Number(e.target.value))}
                  >
                    <option value={100}>100</option>
                    <option value={200}>200</option>
                    <option value={500}>500</option>
                  </select>
                </Field>
                {logs.isPending ? (
                  <LoadingState />
                ) : logs.error ? (
                  <ErrorState error={logs.error} />
                ) : logs.data?.available ? (
                  <>
                    <pre className="kube-log">
                      {Array.isArray(logs.data.lines)
                        ? logs.data.lines.map((l) => str(l, "")).join("\n")
                        : ""}
                    </pre>
                    {logs.data.truncated && (
                      <p className="muted">Показана последняя часть логов.</p>
                    )}
                  </>
                ) : (
                  <EmptyState
                    title="Логи недоступны"
                    description={str(
                      logs.data?.message,
                      "Провайдер не вернул логов.",
                    )}
                  />
                )}
              </div>
            </Panel>
          )}
        </div>
      )}
    </>
  );
}
export function ReadinessPage() {
  const q = useQuery({
    queryKey: ["kubernetes", "readiness"],
    queryFn: kubernetesApi.readiness,
  });
  const cap = useKubeCapabilities();
  const names: Record<string, string> = {
    safe_cockpit: "Инвентарь и обзор",
    live_resource_explorer: "Просмотр live-ресурсов",
    logs_stream: "Поток логов",
    secret_values: "Просмотр значений Secret",
    dry_run_apply: "Проверка манифеста",
    apply_yaml: "Применение YAML",
    patch: "Изменение полей",
    scale: "Масштабирование",
    rollout_restart: "Перезапуск нагрузки",
    delete: "Удаление ресурса",
    pod_exec: "Команда в pod",
    port_forward: "Переадресация порта",
    node_maintenance: "Обслуживание узлов",
    node_drain: "Освобождение узла",
    cluster_terminal: "Терминал кластера",
    node_debug: "Диагностика узла",
    action_request: "Запрос изменения",
    diagnosis_draft: "Черновик диагностики",
  };
  return (
    <>
      <PageHeader
        eyebrow="Kubernetes"
        title="Готовность и возможности"
        description="Результаты проверок backend и доступные операции для текущего пользователя."
        actions={
          <Button
            onClick={() => {
              void q.refetch();
              void cap.refetch();
            }}
          >
            <RefreshCw size={16} /> Обновить
          </Button>
        }
      />
      <KubeNav />
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : (
        <div className="stack">
          <Panel
            title="Проверки системы"
            actions={<KubeStatus value={q.data?.status} />}
          >
            <DataTable
              rows={rows(q.data?.checks)}
              rowKey={(r) => str(r.id)}
              emptyTitle="Проверки не получены"
              columns={[
                {
                  key: "name",
                  label: "Проверка",
                  render: (r) => (
                    <strong>{str(r.id).replaceAll("_", " ")}</strong>
                  ),
                },
                {
                  key: "status",
                  label: "Состояние",
                  render: (r) => <KubeStatus value={r.status} />,
                },
                {
                  key: "details",
                  label: "Результат",
                  render: (r) => str(r.detail),
                },
                {
                  key: "required",
                  label: "Обязательность",
                  render: (r) =>
                    r.required ? "Обязательная" : "Дополнительная",
                },
              ]}
            />
          </Panel>
          <Panel
            title="Операции"
            description="Доступность определяется правами, режимом backend и настройками транспорта."
          >
            <div className="section-body">
              {cap.error ? (
                <ErrorState error={cap.error} />
              ) : cap.isPending ? (
                <LoadingState />
              ) : (
                cap.data?.workflows.map((w) => (
                  <div className="kube-capability" key={w.id}>
                    <div>
                      <strong>{names[w.id] || w.id}</strong>
                      <p>
                        {w.available && w.transport_enabled !== false
                          ? "Доступно при соблюдении области и срока сессии."
                          : w.transport_enabled === false
                            ? "Транспорт операции выключен в настройках backend."
                            : w.blocked_reason || "Операция недоступна."}
                      </p>
                    </div>
                    <KubeStatus
                      value={
                        w.available && w.transport_enabled !== false
                          ? "ready"
                          : "not_configured"
                      }
                    />
                  </div>
                ))
              )}
            </div>
          </Panel>
        </div>
      )}
    </>
  );
}
