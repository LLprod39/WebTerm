import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Button,
  DataTable,
  Drawer,
  ErrorState,
  Field,
  JsonDetails,
  LoadingState,
  Metric,
  PageHeader,
  Panel,
  Tabs,
} from "@/components/ui";
import { usePermission, useSession } from "@/app/session";
import { formatDate } from "@/lib/utils";
import { kubernetesApi, type KubeData } from "@/api/kubernetes";
import { kubeWorkflows } from "@/api/kubernetes-workflows";
import {
  kubeBase,
  KubeNav,
  KubeFacts,
  KubeEvents,
  KubeStatus,
  obj,
  rows,
  str,
  useKubeOperation,
} from "./common";
import { CreateRequest, requestLabels } from "./Requests";

function Related({
  items,
  kind,
}: {
  items: KubeData[];
  kind: "workloads" | "pods" | "devtron" | "fleet";
}) {
  return (
    <DataTable
      rows={items}
      rowKey={(r) => str(r.id)}
      emptyTitle="Связанных объектов нет"
      columns={[
        {
          key: "name",
          label: "Объект",
          render: (r) => (
            <Link
              className="text-link"
              to={
                kind === "devtron" || kind === "fleet"
                  ? `${kubeBase}/delivery/${kind}/${str(r.id)}`
                  : `${kubeBase}/resources/${kind}/${str(r.id)}`
              }
            >
              {str(r.name)}
            </Link>
          ),
        },
        { key: "ns", label: "Пространство", render: (r) => str(r.namespace) },
        {
          key: "state",
          label: "Состояние",
          render: (r) => <KubeStatus value={r.health || r.status} />,
        },
        { key: "owner", label: "Владелец", render: (r) => str(r.owner) },
        {
          key: "ready",
          label: "Готово",
          render: (r) => `${str(r.ready, "—")} / ${str(r.desired, "—")}`,
        },
      ]}
    />
  );
}
function ExternalLinks({
  item,
  kind,
}: {
  item: KubeData;
  kind: "fleet" | "devtron";
}) {
  const { user } = useSession();
  const op = useKubeOperation();
  const [ready, setReady] = useState<{ label: string; url: string }>();
  const links = Object.entries(obj(item.links)).filter(
    ([, url]) => typeof url === "string" && /^https?:\/\//i.test(url),
  );
  if (!user?.is_staff || !links.length) return null;
  return (
    <div className="stack">
      <p className="muted">Административные переходы во внешнюю систему</p>
      <div className="row">
        {links.map(([key, url]) => (
          <Button
            key={key}
            size="sm"
            loading={op.pending}
            onClick={() =>
              void op.run(async () => {
                await kubeWorkflows.auditLink({
                  target_type: kind === "devtron" ? "app" : "fleet_bundle",
                  target_id: item.id,
                  target_name: item.name,
                  cluster_id: item.cluster_id,
                  provider: kind,
                  link_key: key,
                  url,
                });
                setReady({ label: key, url: String(url) });
              }, "Переход записан в журнал")
            }
          >
            {key}
          </Button>
        ))}
      </div>
      {ready && (
        <a
          className="text-link"
          href={ready.url}
          target="_blank"
          rel="noreferrer"
        >
          Открыть {ready.label} во внешней системе
        </a>
      )}
      {op.feedback}
    </div>
  );
}
export function DeliveryPage() {
  const [tab, setTab] = useState<"helm" | "fleet" | "devtron">("helm");
  const [cluster, setCluster] = useState("");
  const [release, setRelease] = useState<KubeData>();
  const clusters = useQuery({
    queryKey: ["kubernetes", "clusters"],
    queryFn: kubernetesApi.clusters,
  });
  const q = useQuery({
    queryKey: ["kubernetes", "delivery", tab, cluster],
    queryFn: () => kubeWorkflows.delivery(tab, cluster),
  });
  const items = rows(
    q.data?.[tab === "helm" ? "items" : tab === "fleet" ? "bundles" : "apps"],
  ).filter(
    (r) =>
      !cluster || tab === "helm" || tab === "fleet" || r.cluster_id === cluster,
  );
  const summary = obj(q.data?.summary);
  return (
    <>
      <PageHeader
        eyebrow="Kubernetes"
        title="Поставки и владельцы"
        description="Helm-релизы, Fleet bundles и приложения Devtron с проверяемым маршрутом изменения."
      />
      <KubeNav />
      <div className="stack">
        <Tabs
          value={tab}
          onChange={(v) => {
            setTab(v as typeof tab);
            setRelease(undefined);
          }}
          items={[
            { value: "helm", label: "Helm-релизы" },
            { value: "fleet", label: "Fleet" },
            { value: "devtron", label: "Devtron" },
          ]}
        />
        {tab !== "fleet" && (
          <Field label="Кластер" htmlFor="delivery-cluster">
            <select
              id="delivery-cluster"
              value={cluster}
              onChange={(e) => setCluster(e.target.value)}
            >
              <option value="">Все кластеры</option>
              {clusters.data?.clusters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </Field>
        )}
        {q.isPending ? (
          <LoadingState />
        ) : q.error ? (
          <ErrorState error={q.error} retry={() => q.refetch()} />
        ) : (
          <>
            {tab === "helm" && (
              <div className="kube-grid">
                <Metric
                  label="Релизы"
                  value={str(summary.release_count, "0")}
                />
                <Metric
                  label="Конфликт владельцев"
                  value={str(summary.conflict_count, "0")}
                />
                <Metric
                  label="Требуют маршрута владельца"
                  value={str(summary.guarded_count, "0")}
                />
              </div>
            )}
            <Panel>
              <DataTable
                rows={items}
                rowKey={(r) =>
                  str(r.id, r.release_key ? str(r.release_key) : "")
                }
                searchValue={(r) =>
                  `${str(r.name, r.release_name ? str(r.release_name) : "")} ${str(r.namespace, "")} ${str(r.owner, "")}`
                }
                emptyTitle="Поставок пока нет"
                emptyDescription="Синхронизируйте провайдеры, чтобы получить сведения о релизах и приложениях."
                columns={[
                  {
                    key: "name",
                    label:
                      tab === "helm"
                        ? "Релиз"
                        : tab === "fleet"
                          ? "Bundle"
                          : "Приложение",
                    render: (r) =>
                      tab === "helm" ? (
                        <Button variant="ghost" onClick={() => setRelease(r)}>
                          {str(r.release_name)}
                        </Button>
                      ) : (
                        <Link
                          className="text-link"
                          to={`${kubeBase}/delivery/${tab}/${str(r.id)}`}
                        >
                          {str(r.name)}
                        </Link>
                      ),
                  },
                  {
                    key: "scope",
                    label: "Область",
                    render: (r) =>
                      `${str(r.cluster_name, "")} ${str(r.namespace, r.target ? str(r.target) : "")}`,
                  },
                  {
                    key: "owner",
                    label: "Владелец / источник",
                    render: (r) => str(r.primary_owner || r.owner || r.source),
                  },
                  {
                    key: "status",
                    label: "Состояние",
                    render: (r) => (
                      <KubeStatus
                        value={r.conflict ? "warning" : r.health || r.status}
                      />
                    ),
                  },
                  {
                    key: "version",
                    label: "Версия / готовность",
                    render: (r) =>
                      r.version
                        ? str(r.version)
                        : `${str(r.ready, "—")} / ${str(r.desired, "—")}`,
                  },
                  {
                    key: "sync",
                    label: "Обновлено",
                    render: (r) => formatDate(str(r.last_sync_at, "")),
                  },
                ]}
              />
            </Panel>
          </>
        )}
      </div>
      <Drawer
        open={!!release}
        wide
        onOpenChange={(v) => !v && setRelease(undefined)}
        title={str(release?.release_name, "Helm-релиз")}
        description={`${str(release?.cluster_name, "")} · ${str(release?.namespace, "")}`}
      >
        {release && (
          <div className="stack">
            {release.conflict === true && (
              <p className="notice">
                Для релиза обнаружено несколько владельцев. Сначала определите
                единственный источник изменений.
              </p>
            )}
            <KubeFacts
              data={release}
              fields={[
                ["primary_owner", "Владелец"],
                ["owners", "Все обнаруженные владельцы"],
                ["status", "Состояние"],
                ["evidence", "Признаки владения"],
              ]}
            />
            <p className="muted">
              Маршрут изменения: {str(obj(release.policy).change_path)}. Прямое
              изменение: {str(obj(release.policy).direct_mutation_policy)}.
            </p>
            <Panel title="Нагрузки">
              <Related items={rows(release.workloads)} kind="workloads" />
            </Panel>
            <Panel title="Приложения">
              <Related
                items={rows(release.apps).filter((a) => a.owner === "devtron")}
                kind="devtron"
              />
            </Panel>
            <Panel title="Fleet bundles">
              <Related items={rows(release.fleet_bundles)} kind="fleet" />
            </Panel>
          </div>
        )}
      </Drawer>
    </>
  );
}

export function DeliveryDetailPage() {
  const { kind = "", id = "" } = useParams();
  const category = kind === "fleet" ? "fleet" : "devtron";
  const canDiagnose = usePermission("studio_pipelines");
  const nav = useNavigate();
  const op = useKubeOperation();
  const [tab, setTab] = useState("overview");
  const [request, setRequest] = useState<string>();
  const [diagnosis, setDiagnosis] = useState(false);
  const q = useQuery({
    queryKey: ["kubernetes", "delivery-detail", category, id],
    queryFn: () => kubeWorkflows.deliveryDetail(category, id),
  });
  const data = q.data || {};
  const item = obj(data[category === "fleet" ? "bundle" : "app"]);
  const context = obj(data.delivery_context);
  const allowed = Array.isArray(obj(data.policy).requestable_actions)
    ? (obj(data.policy).requestable_actions as string[])
    : [];
  return (
    <>
      <PageHeader
        eyebrow={category === "fleet" ? "Fleet bundle" : "Devtron"}
        title={str(item.name, "Поставка")}
        description={`${str(item.cluster_name, "")} ${str(item.namespace, item.source ? str(item.source) : "")}`}
        actions={
          <div className="row">
            {allowed
              .filter((a) => a in requestLabels)
              .map((a) => (
                <Button key={a} onClick={() => setRequest(a)}>
                  {requestLabels[a]}
                </Button>
              ))}
            {canDiagnose && category === "devtron" && (
              <Button onClick={() => setDiagnosis(true)}>
                Подготовить диагностику
              </Button>
            )}
          </div>
        }
      />
      <KubeNav />
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} retry={() => q.refetch()} />
      ) : (
        <div className="stack">
          {op.feedback}
          <Tabs
            value={tab}
            onChange={setTab}
            items={[
              { value: "overview", label: "Обзор" },
              { value: "workloads", label: "Нагрузки" },
              ...(category === "devtron"
                ? [
                    { value: "pods", label: "Pods" },
                    { value: "delivery", label: "История и values" },
                  ]
                : []),
              { value: "events", label: "События" },
            ]}
          />
          {tab === "overview" && (
            <>
              <Panel
                title="Состояние поставки"
                actions={<KubeStatus value={item.health || item.status} />}
              >
                <div className="section-body stack">
                  <KubeFacts
                    data={item}
                    fields={[
                      ["owner", "Владелец"],
                      ["source", "Источник"],
                      ["target", "Целевая область"],
                      ["version", "Версия"],
                      ["ready", "Готово"],
                      ["desired", "Ожидается"],
                      ["team", "Команда"],
                    ]}
                  />
                  <p className="muted">
                    Синхронизировано {formatDate(str(item.last_sync_at, ""))}
                  </p>
                  {item.partitions !== undefined && (
                    <JsonDetails
                      data={item.partitions}
                      label="Группы раскатки"
                    />
                  )}
                  <ExternalLinks item={item} kind={category} />
                </div>
              </Panel>
              {category === "fleet" && (
                <Panel title="Приложения Devtron">
                  <Related
                    items={rows(data.apps).filter((a) => a.owner === "devtron")}
                    kind="devtron"
                  />
                </Panel>
              )}
            </>
          )}
          {tab === "workloads" && (
            <Panel title="Нагрузки поставки">
              <Related items={rows(data.workloads)} kind="workloads" />
            </Panel>
          )}
          {tab === "pods" && (
            <Panel title="Pods приложения">
              <Related items={rows(data.pods)} kind="pods" />
            </Panel>
          )}
          {tab === "events" && (
            <Panel title="События поставки">
              <KubeEvents events={rows(data.events)} />
            </Panel>
          )}
          {tab === "delivery" && (
            <>
              <Panel title="Релиз и последнее развёртывание">
                <div className="section-body stack">
                  <KubeFacts
                    data={obj(context.chart)}
                    fields={[
                      ["name", "Chart"],
                      ["version", "Версия"],
                      ["release", "Релиз"],
                    ]}
                  />
                  <KubeFacts
                    data={obj(obj(context.history).evidence)}
                    fields={[
                      ["deployment_id", "Развёртывание"],
                      ["deployed_at", "Дата"],
                      ["deployed_by", "Выполнил"],
                    ]}
                  />
                </div>
              </Panel>
              <Panel title="Конфигурация Helm values">
                <div className="section-body stack">
                  {obj(context.values).available ? (
                    <>
                      <p>Отпечаток: {str(obj(context.values).digest)}</p>
                      <JsonDetails
                        data={obj(context.values).preview}
                        label="Доступный редактированный обзор values"
                      />
                    </>
                  ) : (
                    <p className="muted">
                      Источник не передал сведения о values.
                    </p>
                  )}
                  <p className="muted">
                    Изменения и откат проходят через владельца поставки и заявку
                    на согласование.
                  </p>
                </div>
              </Panel>
            </>
          )}
          {request && (
            <CreateRequest
              initialAction={request}
              initialTarget={
                category === "fleet"
                  ? { bundle_id: id, bundle_name: item.name }
                  : { app_id: id }
              }
              onClose={() => setRequest(undefined)}
            />
          )}
          <Drawer
            open={diagnosis}
            onOpenChange={setDiagnosis}
            title="Подготовить диагностику"
          >
            <div className="stack">
              <p>
                Будет создан черновик диагностики для приложения{" "}
                {str(item.name)}. Проверьте предложенный план в разделе
                автоматизации перед запуском.
              </p>
              {op.feedback}
              <Button
                variant="primary"
                loading={op.pending}
                onClick={() =>
                  void op.run(async () => {
                    const result = await kubeWorkflows.diagnose(id);
                    nav(`/automation/drafts/${str(result.draft.id)}`);
                  }, "Черновик создан")
                }
              >
                Создать черновик
              </Button>
            </div>
          </Drawer>
        </div>
      )}
    </>
  );
}
