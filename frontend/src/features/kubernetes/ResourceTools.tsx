import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Button,
  DataTable,
  Drawer,
  ErrorState,
  Field,
  JsonDetails,
  LoadingState,
  Metric,
  Panel,
} from "@/components/ui";
import { useSession } from "@/app/session";
import { formatDate, downloadText } from "@/lib/utils";
import { RealtimeConnection, type ConnectionState } from "@/realtime/socket";
import {
  kubernetesApi,
  kubeQuery,
  type KubeData,
  type KubeSession,
  type KubeWorkflow,
  type ResourceTarget,
} from "@/api/kubernetes";
import { KubeStatus, obj, rows, str, useActiveKubeSession } from "./common";
import { ShellSession } from "./Emergency";

export function ResourceTransport({
  session,
  target,
  workflows,
}: {
  session: KubeSession;
  target: ResourceTarget;
  workflows: KubeWorkflow[];
}) {
  const [mode, setMode] = useState<"exec" | "forward">();
  const [reason, setReason] = useState("");
  const [container, setContainer] = useState("");
  const [command, setCommand] = useState("/bin/sh");
  const [port, setPort] = useState(8080);
  const [duration, setDuration] = useState(300);
  const [review, setReview] = useState(false);
  const [started, setStarted] = useState(false);
  const active = useActiveKubeSession(session);
  const allowed = (id: string) =>
    active &&
    session.mode === "break_glass" &&
    workflows.some(
      (w) => w.id === id && w.available && w.transport_enabled !== false,
    );
  function open(value: "exec" | "forward") {
    setMode(value);
    setStarted(false);
    setReason("");
    setReview(false);
  }
  function close() {
    setStarted(false);
    setMode(undefined);
  }
  return (
    <>
      <div className="row">
        {target.kind.toLowerCase() === "pod" && (
          <Button disabled={!allowed("pod_exec")} onClick={() => open("exec")}>
            Терминал контейнера
          </Button>
        )}
        {["pod", "service"].includes(target.kind.toLowerCase()) && (
          <Button
            disabled={!allowed("port_forward")}
            onClick={() => open("forward")}
          >
            Подключение к порту
          </Button>
        )}
      </div>
      <Drawer
        open={!!mode}
        wide
        onOpenChange={(v) => !v && close()}
        title={mode === "exec" ? "Терминал контейнера" : "Диагностика порта"}
        description={`${target.namespace}/${target.name} · ${session.cluster_name}`}
      >
        {started ? (
          mode === "exec" ? (
            <ShellSession
              session={session}
              kind="exec"
              node=""
              reason={reason}
              namespace={target.namespace}
              pod={target.name}
              container={container}
              command={command}
              onEnd={() => setStarted(false)}
            />
          ) : (
            <PortTunnel
              session={session}
              target={target}
              reason={reason}
              port={port}
              duration={duration}
              onEnd={() => setStarted(false)}
            />
          )
        ) : (
          <div className="stack">
            {mode === "exec" ? (
              <>
                <Field label="Контейнер" htmlFor="pod-exec-container">
                  <input
                    id="pod-exec-container"
                    value={container}
                    disabled={review}
                    onChange={(e) => setContainer(e.target.value)}
                    placeholder="Контейнер по умолчанию"
                  />
                </Field>
                <Field
                  label="Команда запуска"
                  htmlFor="pod-exec-command"
                  description="Команда и аргументы дополнительно проверяются политикой backend."
                >
                  <input
                    id="pod-exec-command"
                    value={command}
                    disabled={review}
                    onChange={(e) => setCommand(e.target.value)}
                  />
                </Field>
              </>
            ) : (
              <>
                <Field label="Порт ресурса" htmlFor="pod-forward-port">
                  <input
                    id="pod-forward-port"
                    type="number"
                    min={1}
                    max={65535}
                    value={port}
                    onChange={(e) => setPort(Number(e.target.value))}
                    disabled={review}
                  />
                </Field>
                <Field
                  label="Срок подключения, секунд"
                  htmlFor="pod-forward-duration"
                >
                  <input
                    id="pod-forward-duration"
                    type="number"
                    min={1}
                    max={900}
                    value={duration}
                    onChange={(e) => setDuration(Number(e.target.value))}
                    disabled={review}
                  />
                </Field>
                <p className="muted">
                  После подключения можно отправить HTTP-запрос или данные прямо
                  из браузера через защищённый туннель. Локальный TCP-порт на
                  компьютере не открывается.
                </p>
              </>
            )}
            <Field
              label="Причина аварийного доступа"
              htmlFor="pod-transport-reason"
            >
              <textarea
                id="pod-transport-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                disabled={review}
              />
            </Field>
            {review && (
              <div className="notice">
                Подтвердите доступ к {target.namespace}/{target.name}
                {mode === "forward" ? `:${port}` : ` · ${command}`} в{" "}
                {session.cluster_name}. Причина: {reason}.
              </div>
            )}
            <div className="row">
              {review && (
                <Button onClick={() => setReview(false)}>
                  Изменить параметры
                </Button>
              )}
              <Button
                variant="primary"
                disabled={
                  !allowed(mode === "exec" ? "pod_exec" : "port_forward") ||
                  !reason.trim() ||
                  (mode === "exec"
                    ? !command.trim()
                    : !Number.isInteger(port) ||
                      port < 1 ||
                      port > 65535 ||
                      !Number.isInteger(duration) ||
                      duration < 1 ||
                      duration > 900)
                }
                onClick={() => (review ? setStarted(true) : setReview(true))}
              >
                {review ? "Открыть соединение" : "Проверить и продолжить"}
              </Button>
            </div>
          </div>
        )}
      </Drawer>
    </>
  );
}

function PortTunnel({
  session,
  target,
  reason,
  port,
  duration,
  onEnd,
}: {
  session: KubeSession;
  target: ResourceTarget;
  reason: string;
  port: number;
  duration: number;
  onEnd: () => void;
}) {
  const { user } = useSession();
  const active = useActiveKubeSession(session);
  const connection = useRef<RealtimeConnection<KubeData> | null>(null);
  const [state, setState] = useState<ConnectionState>("connecting");
  const [started, setStarted] = useState(false);
  const [error, setError] = useState("");
  const [received, setReceived] = useState("");
  const [receivedBytes, setReceivedBytes] = useState(0);
  const [payload, setPayload] = useState("");
  const [encoding, setEncoding] = useState("utf8");
  const [path, setPath] = useState("/");
  const [host, setHost] = useState(target.name);
  const [summary, setSummary] = useState<KubeData>();
  useEffect(() => {
    if (!active) return;
    const decoder = new TextDecoder();
    const c = new RealtimeConnection<KubeData>({
      path:
        `/ws/kubernetes/admin/port-forward/${session.id}/` +
        kubeQuery({
          stream: true,
          cluster_id: session.cluster_id,
          ...target,
          remote_port: port,
          duration_seconds: duration,
          reason,
          max_frames: 1000,
        }),
      maxRetries: 0,
      onState: (s) => {
        setState(s);
        if (s === "disconnected" || s === "failed") setStarted(false);
      },
      onMessage: (m) => {
        const type = str(m.type, "");
        if (type === "port_forward_started") setStarted(true);
        if (type === "port_forward_data") {
          try {
            const bytes = Uint8Array.from(atob(str(m.data, "")), (char) =>
              char.charCodeAt(0),
            );
            setReceivedBytes((n) => n + bytes.length);
            const text = decoder.decode(bytes, { stream: true });
            setReceived((prev) => (prev + text).slice(-200_000));
          } catch {
            setError("Сервер вернул некорректный пакет туннеля.");
          }
        }
        if (type === "port_forward_stopped") {
          setStarted(false);
          setSummary(obj(m.summary));
        }
        if (
          type.endsWith("_error") ||
          type.endsWith("_rejected") ||
          type.endsWith("_blocked")
        ) {
          setError(
            str(
              m.message,
              m.reason ? str(m.reason) : "Запрос отклонён сервером.",
            ),
          );
          if (type !== "port_forward_input_rejected") setStarted(false);
        }
      },
    });
    connection.current = c;
    const connectTimer = window.setTimeout(() => c.connect(), 0);
    return () => {
      window.clearTimeout(connectTimer);
      c.close();
      connection.current = null;
    };
  }, [
    active,
    session.id,
    session.cluster_id,
    target,
    reason,
    port,
    duration,
    user?.id,
    user?.active_project?.id,
  ]);
  function send(value: string, base64 = false) {
    setError("");
    if (!started || !active) return;
    if (new TextEncoder().encode(value).length > 65536) {
      setError("Один пакет ограничен 64 КиБ.");
      return;
    }
    if (base64) {
      try {
        atob(value);
      } catch {
        setError("Проверьте данные Base64.");
        return;
      }
    }
    if (
      !connection.current?.send({
        type: "client_data",
        data: value,
        encoding: base64 ? "base64" : "utf8",
      })
    )
      setError("Соединение потеряно. Откройте новый туннель.");
  }
  return (
    <div className="stack">
      <div className="spread">
        <div className="row">
          <KubeStatus value={state} />
          <span>Получено {receivedBytes.toLocaleString("ru")} байт</span>
        </div>
        <Button
          variant="danger"
          onClick={() => {
            connection.current?.close();
            onEnd();
          }}
        >
          Закрыть туннель
        </Button>
      </div>
      {error && (
        <p className="notice" role="alert">
          {error}
        </p>
      )}
      {!active && <p className="notice">Сессия завершена. Туннель закрыт.</p>}
      <div className="form-grid">
        <Field label="HTTP Host" htmlFor="forward-host">
          <input
            id="forward-host"
            value={host}
            onChange={(e) => setHost(e.target.value.replace(/[\r\n]/g, ""))}
          />
        </Field>
        <Field label="HTTP-путь" htmlFor="forward-path">
          <input
            id="forward-path"
            value={path}
            onChange={(e) => setPath(e.target.value.replace(/[\r\n]/g, ""))}
          />
        </Field>
      </div>
      <Button
        disabled={!started || !active || !path.startsWith("/")}
        onClick={() =>
          send(
            `GET ${path} HTTP/1.1\r\nHost: ${host}\r\nConnection: close\r\n\r\n`,
          )
        }
      >
        Отправить GET-запрос
      </Button>
      <details>
        <summary>Отправить свои данные</summary>
        <div className="stack">
          <Field label="Кодировка" htmlFor="forward-encoding">
            <select
              id="forward-encoding"
              value={encoding}
              onChange={(e) => setEncoding(e.target.value)}
            >
              <option value="utf8">Текст UTF-8</option>
              <option value="base64">Бинарные данные Base64</option>
            </select>
          </Field>
          <Field label="Данные пакета" htmlFor="forward-payload">
            <textarea
              id="forward-payload"
              className="kube-code"
              value={payload}
              onChange={(e) => setPayload(e.target.value)}
              maxLength={65536}
            />
          </Field>
          <Button
            disabled={!started || !active || !payload}
            onClick={() => send(payload, encoding === "base64")}
          >
            Отправить пакет
          </Button>
        </div>
      </details>
      <pre className="kube-log" aria-label="Ответ через туннель">
        {received || "Ожидание данных от ресурса…"}
      </pre>
      {received && (
        <Button
          onClick={() =>
            downloadText(`${target.name}-${port}-response.txt`, received)
          }
        >
          Скачать показанный ответ
        </Button>
      )}
      <p className="muted">
        Показан ответ как UTF-8, последние 200 000 символов. Соединение
        ограничено сроком сессии и не восстанавливается автоматически.
      </p>
      {summary && <JsonDetails data={summary} label="Итог туннеля" />}
    </div>
  );
}

export function ResourceWatch({
  session,
  target,
}: {
  session: KubeSession;
  target: ResourceTarget;
}) {
  const { user } = useSession();
  const [watching, setWatching] = useState(false);
  const [items, setItems] = useState<KubeData[]>([]);
  const [error, setError] = useState("");
  const [state, setState] = useState<ConnectionState>("disconnected");
  const active = useActiveKubeSession(session);
  useEffect(() => {
    if (!active || !watching) return;
    const c = new RealtimeConnection<KubeData>({
      path:
        `/ws/kubernetes/admin/watch/${session.id}/` +
        kubeQuery({
          cluster_id: session.cluster_id,
          ...target,
          follow: true,
          max_batches: 20,
          timeout_seconds: 10,
          limit: 30,
        }),
      maxRetries: 0,
      onState: setState,
      onMessage: (m) => {
        if (m.type === "watch_batch")
          setItems((prev) =>
            [...prev, ...rows(obj(m.payload).events)].slice(-300),
          );
        if (m.type === "stream_error") {
          setError(str(m.message));
          setWatching(false);
        }
        if (m.type === "stream_stopped") setWatching(false);
      },
    });
    c.connect();
    return () => c.close();
  }, [
    active,
    watching,
    session.id,
    session.cluster_id,
    target,
    user?.id,
    user?.active_project?.id,
  ]);
  return (
    <div className="stack">
      <div className="row">
        <Button
          disabled={!active}
          onClick={() => {
            if (!watching) {
              setItems([]);
              setError("");
            }
            setWatching(!watching);
          }}
        >
          {watching ? "Остановить наблюдение" : "Начать наблюдение"}
        </Button>
        <KubeStatus value={state} />
      </div>
      {error && (
        <p role="alert" className="notice">
          {error}
        </p>
      )}
      <DataTable
        rows={items}
        rowKey={(r) =>
          str(r.resource_version) +
          str(r.type) +
          str(obj(obj(r.object).metadata).uid)
        }
        emptyTitle="Событий потока пока нет"
        columns={[
          {
            key: "type",
            label: "Изменение",
            render: (r) => <KubeStatus value={r.type} />,
          },
          {
            key: "version",
            label: "Версия",
            render: (r) => str(r.resource_version),
          },
          {
            key: "resource",
            label: "Объект",
            render: (r) => str(obj(obj(r.object).metadata).name),
          },
          {
            key: "details",
            label: "Данные",
            render: (r) => (
              <JsonDetails data={r.object} label="Состояние ресурса" />
            ),
          },
        ]}
      />
      <p className="muted">
        Поток ограничен 20 пакетами. В окне сохраняются последние 300 событий.
      </p>
    </div>
  );
}

export function MetricsDrawer({
  session,
  onClose,
}: {
  session: KubeSession;
  onClose: () => void;
}) {
  const [scope, setScope] = useState("nodes");
  const [namespace, setNamespace] = useState(session.namespace || "");
  const active = useActiveKubeSession(session);
  const q = useQuery({
    queryKey: ["kubernetes", "metrics", session.id, scope, namespace],
    queryFn: () =>
      kubernetesApi.resourceRead(session.cluster_id, "metrics", {
        session_id: session.id,
        scope,
        namespace: scope === "pods" ? namespace : "",
        limit: 100,
      }),
    enabled: active,
  });
  const summary = obj(q.data?.summary);
  const number = (value: unknown) =>
    typeof value === "number"
      ? value.toLocaleString("ru", { maximumFractionDigits: 1 })
      : "—";
  return (
    <Drawer
      open
      wide
      onOpenChange={(v) => !v && onClose()}
      title="Ресурсы CPU и памяти"
      description={`${session.cluster_name} · metrics.k8s.io`}
    >
      <div className="stack">
        <div className="row">
          <Field label="Область метрик" htmlFor="metrics-scope">
            <select
              id="metrics-scope"
              value={scope}
              onChange={(e) => setScope(e.target.value)}
            >
              <option value="nodes">Узлы</option>
              <option value="pods">Pods</option>
            </select>
          </Field>
          {scope === "pods" && (
            <Field label="Пространство имён" htmlFor="metrics-namespace">
              <input
                id="metrics-namespace"
                value={namespace}
                onChange={(e) => setNamespace(e.target.value)}
              />
            </Field>
          )}
          <Button
            onClick={() => q.refetch()}
            disabled={!active}
            loading={q.isFetching}
          >
            Обновить
          </Button>
        </div>
        {!active ? (
          <p className="notice">Сессия доступа завершена.</p>
        ) : q.isPending ? (
          <LoadingState />
        ) : q.error ? (
          <ErrorState error={q.error} retry={() => q.refetch()} />
        ) : (
          <>
            <div className="kube-grid">
              <Metric
                label="CPU, millicores"
                value={number(summary.total_cpu_millicores)}
              />
              <Metric
                label="Память, МиБ"
                value={
                  typeof summary.total_memory_bytes === "number"
                    ? number(summary.total_memory_bytes / 1024 / 1024)
                    : "—"
                }
              />
              <Metric label="Объекты" value={str(summary.item_count, "0")} />
            </div>
            <Panel>
              <DataTable
                rows={rows(q.data?.items)}
                rowKey={(r) => str(r.namespace, "") + "/" + str(r.name)}
                emptyTitle="Метрик нет"
                columns={[
                  {
                    key: "name",
                    label: "Объект",
                    render: (r) => (
                      <>
                        <strong>{str(r.name)}</strong>
                        <p className="muted">{str(r.namespace, "")}</p>
                      </>
                    ),
                  },
                  {
                    key: "cpu",
                    label: "CPU, m",
                    render: (r) =>
                      number(obj(r.usage_normalized).cpu_millicores),
                  },
                  {
                    key: "memory",
                    label: "Память, МиБ",
                    render: (r) =>
                      typeof obj(r.usage_normalized).memory_bytes === "number"
                        ? number(
                            Number(obj(r.usage_normalized).memory_bytes) /
                              1024 /
                              1024,
                          )
                        : "—",
                  },
                  {
                    key: "time",
                    label: "Снимок",
                    render: (r) => formatDate(str(r.timestamp, "")),
                  },
                  {
                    key: "details",
                    label: "Контейнеры",
                    render: (r) =>
                      Array.isArray(r.containers) && (
                        <JsonDetails
                          data={r.containers}
                          label="По контейнерам"
                        />
                      ),
                  },
                ]}
              />
            </Panel>
            {summary.truncated === true && (
              <p className="notice">
                Список ограничен сервером. Выберите более узкую область.
              </p>
            )}
          </>
        )}
      </div>
    </Drawer>
  );
}
