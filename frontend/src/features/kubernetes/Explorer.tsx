import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import {
  Button,
  DataTable,
  Drawer,
  EmptyState,
  ErrorState,
  Field,
  JsonDetails,
  LoadingState,
  PageHeader,
  Panel,
  Tabs,
} from "@/components/ui";
import { useSession } from "@/app/session";
import { formatDate, downloadText } from "@/lib/utils";
import { RealtimeConnection, type ConnectionState } from "@/realtime/socket";
import {
  kubernetesApi,
  kubeQuery,
  type KubeData,
  type KubeResource,
  type KubeSession,
  type KubeWorkflow,
  type ResourceTarget,
} from "@/api/kubernetes";
import {
  kubeBase,
  KubeNav,
  KubeFacts,
  KubeEvents,
  KubeStatus,
  obj,
  rows,
  str,
  useKubeCapabilities,
} from "./common";
import { useActiveKubeSession } from "./common";
import { MutationDrawer, type MutationKind } from "./Mutations";
import { EmergencyTools } from "./Emergency";
import {
  ResourceTransport,
  ResourceWatch,
  MetricsDrawer,
} from "./ResourceTools";
import { ResourceDescription } from "./ResourceDescription";

function ResourceLogs({
  session,
  target,
}: {
  session: KubeSession;
  target: ResourceTarget;
}) {
  const { user } = useSession();
  const [container, setContainer] = useState("");
  const [follow, setFollow] = useState(false);
  const [stream, setStream] = useState<string[]>([]);
  const [streamError, setStreamError] = useState("");
  const [state, setState] = useState<ConnectionState>("disconnected");
  const connection = useRef<RealtimeConnection<KubeData> | null>(null);
  const q = useQuery({
    queryKey: ["kubernetes", "live-logs", session.id, target, container],
    queryFn: () =>
      kubernetesApi.resourceRead(session.cluster_id, "logs", {
        session_id: session.id,
        namespace: target.namespace,
        pod: target.name,
        container,
        tail: 200,
      }),
  });
  useEffect(() => {
    if (!follow) return;
    const c = new RealtimeConnection<KubeData>({
      path:
        `/ws/kubernetes/admin/logs/${session.id}/` +
        kubeQuery({
          cluster_id: session.cluster_id,
          namespace: target.namespace,
          pod: target.name,
          container,
          tail: 100,
          follow: true,
          max_batches: 25,
        }),
      maxRetries: 0,
      onState: setState,
      onMessage: (m) => {
        if (m.type === "log_batch") {
          const payload = obj(m.payload);
          if (payload.available === false)
            setStreamError(str(payload.message, "Логи недоступны."));
          if (Array.isArray(payload.lines))
            setStream((p) =>
              [
                ...p,
                ...(payload.lines as unknown[]).map((l) => str(l, "")),
              ].slice(-1500),
            );
        }
        if (m.type === "stream_error") setStreamError(str(m.message));
        if (m.type === "stream_stopped") setFollow(false);
      },
    });
    connection.current = c;
    c.connect();
    return () => {
      c.close();
      connection.current = null;
    };
  }, [
    follow,
    session.id,
    session.cluster_id,
    target.namespace,
    target.name,
    container,
    user?.id,
    user?.active_project?.id,
  ]);
  const lines = stream.length
    ? stream
    : Array.isArray(q.data?.lines)
      ? q.data.lines.map((l) => str(l, ""))
      : [];
  return (
    <div className="stack">
      <div className="kube-toolbar">
        <Field label="Контейнер" htmlFor="kr-container">
          <input
            id="kr-container"
            value={container}
            disabled={follow}
            placeholder="Контейнер по умолчанию"
            onChange={(e) => setContainer(e.target.value)}
          />
        </Field>
        <Button
          onClick={() => q.refetch()}
          disabled={follow}
          loading={q.isFetching}
        >
          Снимок
        </Button>
        <Button
          onClick={() => {
            setStreamError("");
            if (!follow) setStream([]);
            setFollow(!follow);
          }}
        >
          {follow ? "Остановить поток" : "Следить за логами"}
        </Button>
        <KubeStatus value={state} />
      </div>
      {streamError && (
        <p className="notice" role="alert">
          {streamError}
        </p>
      )}
      {q.error ? (
        <ErrorState error={q.error} />
      ) : q.isPending ? (
        <LoadingState />
      ) : q.data?.available || stream.length ? (
        <pre className="kube-log" aria-label="Логи контейнера">
          {lines.join("\n")}
        </pre>
      ) : (
        <EmptyState
          title="Логи недоступны"
          description={str(q.data?.message, "Провайдер не вернул логи.")}
        />
      )}
      <p className="muted">
        Поток ограничен 25 пакетами; в окне хранятся последние 1500 строк. Для
        продолжения запустите новый поток.
      </p>
    </div>
  );
}
function ResourceDetail({
  session,
  target,
  workflows,
  onClose,
  onMutate,
}: {
  session: KubeSession;
  target: ResourceTarget;
  workflows: KubeWorkflow[];
  onClose: () => void;
  onMutate: (k: MutationKind) => void;
}) {
  const [tab, setTab] = useState("overview");
  const [reveal, setReveal] = useState(false);
  const q = useQuery({
    queryKey: ["kubernetes", "live-detail", session.id, target, reveal],
    queryFn: () =>
      kubernetesApi.resourceRead(session.cluster_id, "resources/detail", {
        session_id: session.id,
        ...target,
        include_secret_values: reveal,
      }),
    gcTime: reveal ? 0 : 300000,
  });
  const yaml = useQuery({
    queryKey: ["kubernetes", "resource-yaml", session.id, target, reveal],
    queryFn: () =>
      kubernetesApi.resourceRead(session.cluster_id, "yaml", {
        session_id: session.id,
        ...target,
        include_secret_values: reveal,
      }),
    gcTime: reveal ? 0 : 300000,
    enabled: tab === "manifest",
  });
  const d = q.data || {};
  const summary = obj(d.summary);
  const canReveal =
    target.kind.toLowerCase() === "secret" &&
    workflows.some((w) => w.id === "secret_values" && w.available);
  return (
    <Drawer
      open
      wide
      onOpenChange={(o) => !o && onClose()}
      title={target.name}
      description={`${target.kind} · ${target.namespace || "уровень кластера"} · ${session.cluster_name}`}
    >
      <div className="stack">
        <Tabs
          value={tab}
          onChange={(v) => {
            setTab(v);
            if (v !== "manifest") setReveal(false);
          }}
          items={[
            { value: "overview", label: "Обзор" },
            { value: "describe", label: "Описание и связи" },
            { value: "events", label: "События" },
            { value: "watch", label: "Наблюдение" },
            { value: "manifest", label: "Манифест" },
            ...(target.kind.toLowerCase() === "pod"
              ? [{ value: "logs", label: "Логи" }]
              : []),
          ]}
        />
        {q.isPending ? (
          <LoadingState />
        ) : q.error ? (
          <ErrorState error={q.error} retry={() => q.refetch()} />
        ) : (
          <>
            {tab === "overview" && (
              <>
                <KubeFacts
                  data={summary}
                  fields={[
                    ["phase", "Фаза"],
                    ["condition_summary", "Состояние"],
                    ["resource_version", "Версия ресурса"],
                    ["generation", "Поколение"],
                    ["owner_references", "Владелец"],
                  ]}
                />
                <p className="muted">
                  Создан {formatDate(str(summary.creation_timestamp, ""))}
                </p>
                {rows(summary.conditions).map((c, i) => (
                  <div className="kube-target" key={`${str(c.type)}-${i}`}>
                    <strong>
                      {str(c.type)} · {str(c.status)}
                    </strong>
                    <p>{str(c.message, c.reason ? str(c.reason) : "")}</p>
                  </div>
                ))}
                <KubeFacts
                  data={obj(summary.replicas)}
                  fields={[
                    ["desired", "Желаемых реплик"],
                    ["ready", "Готовых"],
                    ["available", "Доступных"],
                    ["updated", "Обновлённых"],
                  ]}
                />
                <JsonDetails data={summary.containers} label="Контейнеры" />
                <JsonDetails
                  data={d.ownership}
                  label="Владелец и правила изменения"
                />
                {["pod", "service"].includes(target.kind.toLowerCase()) && (
                  <ResourceTransport
                    session={session}
                    target={target}
                    workflows={workflows}
                  />
                )}{" "}
                {session.mode !== "read" && (
                  <div className="row">
                    {(["scale", "restart", "patch", "delete"] as MutationKind[])
                      .filter(
                        (k) =>
                          k !== "scale" ||
                          ["deployment", "statefulset", "replicaset"].includes(
                            target.kind.toLowerCase(),
                          ),
                      )
                      .filter(
                        (k) =>
                          k !== "restart" ||
                          ["deployment", "statefulset", "daemonset"].includes(
                            target.kind.toLowerCase(),
                          ),
                      )
                      .map((k) => (
                        <Button
                          key={k}
                          variant={k === "delete" ? "danger" : "secondary"}
                          disabled={
                            !workflows.some(
                              (w) =>
                                w.id ===
                                  (k === "restart" ? "rollout_restart" : k) &&
                                w.available,
                            )
                          }
                          onClick={() => onMutate(k)}
                        >
                          {k === "scale"
                            ? "Реплики"
                            : k === "restart"
                              ? "Перезапуск"
                              : k === "patch"
                                ? "Изменить поля"
                                : "Удалить"}
                        </Button>
                      ))}
                  </div>
                )}
              </>
            )}
            {tab === "events" && (
              <>
                {obj(d.events).available === false && (
                  <p className="notice">
                    {str(
                      obj(d.events).message,
                      "События не удалось загрузить.",
                    )}
                  </p>
                )}
                <KubeEvents events={rows(obj(d.events).events)} />
              </>
            )}
            {tab === "manifest" && (
              <>
                {canReveal && (
                  <label className="row">
                    <input
                      type="checkbox"
                      checked={reveal}
                      onChange={(e) => setReveal(e.target.checked)}
                    />{" "}
                    Показать значения Secret · действие регистрируется
                  </label>
                )}
                {yaml.isPending ? (
                  <LoadingState />
                ) : yaml.error ? (
                  <ErrorState error={yaml.error} />
                ) : (
                  <>
                    <p className="muted">
                      Манифест из Kubernetes API в формате JSON. Скрытые backend
                      поля помечены [redacted].
                    </p>
                    <pre className="kube-log">
                      {JSON.stringify(yaml.data?.resource, null, 2)}
                    </pre>
                    <Button
                      onClick={() =>
                        downloadText(
                          `${target.name}.json`,
                          JSON.stringify(yaml.data?.resource, null, 2),
                          "application/json",
                        )
                      }
                    >
                      Скачать манифест
                    </Button>
                  </>
                )}
              </>
            )}
            {tab === "describe" && (
              <ResourceDescription session={session} target={target} />
            )}
            {tab === "watch" && (
              <ResourceWatch session={session} target={target} />
            )}{" "}
            {tab === "logs" && (
              <ResourceLogs session={session} target={target} />
            )}
          </>
        )}
      </div>
    </Drawer>
  );
}
function Explorer({ session }: { session: KubeSession }) {
  const [metrics, setMetrics] = useState(false);
  const cap = useKubeCapabilities();
  const [typeId, setTypeId] = useState("");
  const [namespace, setNamespace] = useState(
    session.namespace ||
      session.allowed_namespaces.find((n) => n !== "*") ||
      "",
  );
  const [selector, setSelector] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState({ selector: "", search: "" });
  const [cursor, setCursor] = useState("");
  const [cursorStack, setCursorStack] = useState<string[]>([]);
  const [selected, setSelected] = useState<ResourceTarget>();
  const [mutation, setMutation] = useState<{
    kind: MutationKind;
    target: ResourceTarget;
  }>();
  const active = useActiveKubeSession(session);
  const discovery = useQuery({
    queryKey: ["kubernetes", "discovery", session.id],
    queryFn: () => kubernetesApi.discovery(session.cluster_id, session.id),
    enabled: active,
    retry: false,
  });
  const types =
    discovery.data?.resource_catalog.items.filter(
      (t) => t.cluster_available && t.verbs.includes("list"),
    ) || [];
  const resourceType = types.find((t) => t.id === typeId);
  const resources = useQuery({
    queryKey: [
      "kubernetes",
      "resources",
      session.id,
      typeId,
      namespace,
      query,
      cursor,
    ],
    queryFn: () =>
      kubernetesApi.resources(session.cluster_id, {
        session_id: session.id,
        api_version: resourceType?.api_version,
        kind: resourceType?.kind,
        resource: resourceType?.resource,
        namespace: resourceType?.namespaced ? namespace : "",
        label_selector: query.selector,
        search: query.search,
        limit: 100,
        continue: cursor,
      }),
    enabled: active && !!resourceType,
    retry: false,
  });
  function targetFor(r: KubeResource): ResourceTarget {
    return {
      api_version: r.apiVersion || resourceType!.api_version,
      kind: r.kind || resourceType!.kind,
      resource: resourceType!.resource,
      name: r.metadata.name,
      namespace: r.metadata.namespace || "",
    };
  }
  function setType(value: string) {
    setTypeId(value);
    setCursor("");
    setCursorStack([]);
  }
  return (
    <div className="stack">
      <div className="spread kube-target">
        <div>
          <strong>{session.cluster_name}</strong>
          <p className="muted">
            {session.mode === "read"
              ? "Просмотр"
              : session.mode === "write"
                ? "Согласованные изменения"
                : "Аварийный доступ"}{" "}
            · {session.allowed_namespaces.join(", ")} · до{" "}
            {formatDate(session.expires_at)}
          </p>
        </div>
        <div className="row">
          <Button disabled={!active} onClick={() => setMetrics(true)}>
            CPU и память
          </Button>
          <KubeStatus value={session.status} />
        </div>
      </div>
      {session.mode === "break_glass" && (
        <EmergencyTools
          session={session}
          workflows={cap.data?.workflows || []}
        />
      )}{" "}
      {!active ? (
        <EmptyState
          title="Сессия не активна"
          description="Чтобы продолжить, запросите новую сессию доступа."
          action={
            <Link
              className="btn btn-primary btn-md"
              to={`${kubeBase}/sessions`}
            >
              Сессии доступа
            </Link>
          }
        />
      ) : (
        <>
          {discovery.isPending ? (
            <LoadingState label="Определяем доступные ресурсы кластера…" />
          ) : discovery.error ? (
            <ErrorState
              error={discovery.error}
              retry={() => discovery.refetch()}
            />
          ) : (
            <>
              <form
                className="kube-toolbar"
                onSubmit={(e) => {
                  e.preventDefault();
                  setQuery({ selector, search });
                  setCursor("");
                  setCursorStack([]);
                }}
              >
                <Field label="Тип ресурса" htmlFor="ke-kind">
                  <select
                    id="ke-kind"
                    value={typeId}
                    onChange={(e) => setType(e.target.value)}
                  >
                    <option value="">Выберите ресурс</option>
                    {types.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.kind} · {t.api_version}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Пространство имён" htmlFor="ke-ns">
                  <input
                    id="ke-ns"
                    disabled={!resourceType?.namespaced}
                    placeholder="Все разрешённые"
                    value={namespace}
                    onChange={(e) => {
                      setNamespace(e.target.value);
                      setCursor("");
                      setCursorStack([]);
                    }}
                  />
                </Field>
                <Field label="Метки" htmlFor="ke-selector">
                  <input
                    id="ke-selector"
                    value={selector}
                    onChange={(e) => setSelector(e.target.value)}
                    placeholder="app=api"
                  />
                </Field>
                <Field label="Поиск имени" htmlFor="ke-search">
                  <input
                    id="ke-search"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </Field>
                <Button type="submit">Применить</Button>
                <Button
                  size="icon"
                  aria-label="Обновить ресурсы"
                  disabled={!resourceType}
                  loading={resources.isFetching}
                  onClick={() => resources.refetch()}
                >
                  <RefreshCw size={16} />
                </Button>
              </form>
              {discovery.data?.resource_catalog.truncated && (
                <p className="notice">
                  Каталог ресурсов ограничен сервером. Показаны доступные
                  записи.
                </p>
              )}
              {session.mode === "write" && (
                <Button
                  disabled={
                    !cap.data?.workflows.some(
                      (w) => w.id === "dry_run_apply" && w.available,
                    )
                  }
                  onClick={() =>
                    setMutation({
                      kind: "apply",
                      target: {
                        api_version: "",
                        kind: "",
                        resource: "",
                        namespace,
                        name: "",
                      },
                    })
                  }
                >
                  Применить YAML…
                </Button>
              )}
              {!resourceType ? (
                <EmptyState
                  title="Выберите тип ресурса"
                  description="Каталог получен непосредственно из API кластера и установленных CRD."
                />
              ) : resources.isPending ? (
                <LoadingState />
              ) : resources.error ? (
                <ErrorState
                  error={resources.error}
                  retry={() => resources.refetch()}
                />
              ) : (
                <Panel
                  title={resourceType.kind}
                  description={`${resources.data?.item_count || 0} ресурсов в текущей выборке`}
                >
                  <DataTable
                    rows={resources.data?.items || []}
                    rowKey={(r) =>
                      r.metadata.uid ||
                      `${r.metadata.namespace}/${r.metadata.name}`
                    }
                    emptyTitle="Ресурсы не найдены"
                    emptyDescription="Измените пространство имён или фильтр меток."
                    columns={[
                      {
                        key: "name",
                        label: "Имя",
                        render: (r) => (
                          <Button
                            variant="ghost"
                            onClick={() => setSelected(targetFor(r))}
                          >
                            {r.metadata.name}
                          </Button>
                        ),
                      },
                      {
                        key: "ns",
                        label: "Область",
                        render: (r) => r.metadata.namespace || "Кластер",
                      },
                      {
                        key: "state",
                        label: "Состояние",
                        render: (r) => (
                          <KubeStatus
                            value={
                              r.summary?.phase ||
                              (r.summary?.ready === true
                                ? "ready"
                                : r.summary?.ready === false
                                  ? "warning"
                                  : "unknown")
                            }
                          />
                        ),
                      },
                      {
                        key: "ready",
                        label: "Реплики",
                        render: (r) => {
                          const rep = obj(r.summary?.replicas);
                          return rep.desired !== null &&
                            rep.desired !== undefined
                            ? `${str(rep.ready, "0")} / ${str(rep.desired)}`
                            : "—";
                        },
                      },
                      {
                        key: "age",
                        label: "Создан",
                        render: (r) => formatDate(r.metadata.creationTimestamp),
                      },
                      {
                        key: "open",
                        label: "",
                        render: (r) => (
                          <Button
                            size="sm"
                            onClick={() => setSelected(targetFor(r))}
                          >
                            Подробнее
                          </Button>
                        ),
                      },
                    ]}
                  />
                  {(cursor || resources.data?.continue_token) && (
                    <div className="section-body spread">
                      <Button
                        disabled={!cursorStack.length}
                        onClick={() => {
                          setCursor(cursorStack[cursorStack.length - 1] || "");
                          setCursorStack((s) => s.slice(0, -1));
                        }}
                      >
                        Предыдущая выборка
                      </Button>
                      <Button
                        disabled={!resources.data?.continue_token}
                        onClick={() => {
                          setCursorStack((s) => [...s, cursor]);
                          setCursor(resources.data!.continue_token);
                        }}
                      >
                        Следующая выборка
                      </Button>
                    </div>
                  )}
                  {resources.data?.truncated &&
                    !resources.data.continue_token && (
                      <p className="section-body muted">
                        Ответ ограничен сервером. Уточните фильтры.
                      </p>
                    )}
                </Panel>
              )}
            </>
          )}
        </>
      )}
      {metrics && (
        <MetricsDrawer session={session} onClose={() => setMetrics(false)} />
      )}{" "}
      {active && selected && !mutation && (
        <ResourceDetail
          session={session}
          target={selected}
          workflows={cap.data?.workflows || []}
          onClose={() => setSelected(undefined)}
          onMutate={(kind) => setMutation({ kind, target: selected })}
        />
      )}{" "}
      {active && mutation && (
        <MutationDrawer
          session={session}
          target={mutation.target}
          kind={mutation.kind}
          workflows={cap.data?.workflows || []}
          onClose={() => {
            setMutation(undefined);
            void resources.refetch();
          }}
        />
      )}
    </div>
  );
}
export function ExplorerPage() {
  const { sessionId = "" } = useParams();
  const q = useQuery({
    queryKey: ["kubernetes", "session", sessionId],
    queryFn: () => kubernetesApi.session(sessionId),
    refetchInterval: 15_000,
  });
  return (
    <>
      <PageHeader
        eyebrow="Kubernetes"
        title="Ресурсы кластера"
        description="Live-инвентарь в границах выданной сессии доступа."
        actions={
          <Link
            className="btn btn-secondary btn-md"
            to={`${kubeBase}/activity?session=${sessionId}`}
          >
            История действий
          </Link>
        }
      />
      <KubeNav />
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} retry={() => q.refetch()} />
      ) : (
        q.data && <Explorer session={q.data.session} />
      )}
    </>
  );
}
