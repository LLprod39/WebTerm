import { useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Drawer, Field, JsonDetails, Panel } from "@/components/ui";
import { useSession } from "@/app/session";
import { RealtimeConnection, type ConnectionState } from "@/realtime/socket";
import {
  kubernetesApi,
  kubeQuery,
  type KubeData,
  type KubeSession,
  type KubeWorkflow,
} from "@/api/kubernetes";
import { kubeBase, KubeStatus, obj, str, useKubeOperation } from "./common";
import { useActiveKubeSession } from "./common";
type ShellKind = "terminal" | "node-debug";
type ShellTarget = {
  namespace?: string;
  pod?: string;
  container?: string;
  command?: string;
};
export function ShellSession({
  session,
  kind,
  node,
  reason,
  onEnd,
  namespace,
  pod,
  container,
  command,
}: {
  session: KubeSession;
  kind: ShellKind | "exec";
  node: string;
  reason: string;
  onEnd: () => void;
} & ShellTarget) {
  const active = useActiveKubeSession(session);
  const { user } = useSession();
  const cache = useQueryClient();
  const mount = useRef<HTMLDivElement>(null);
  const connection = useRef<RealtimeConnection<KubeData> | null>(null);
  const [state, setState] = useState<ConnectionState>("connecting");
  const [error, setError] = useState("");
  const [summary, setSummary] = useState<KubeData>();
  useEffect(() => {
    if (!mount.current || !active) return;
    let writable = false;
    const term = new Terminal({
      fontFamily: "Consolas, monospace",
      fontSize: 13,
      rows: 24,
      cursorBlink: true,
      scrollback: 1500,
      convertEol: true,
      theme: { background: "#11151c", foreground: "#e8edf5" },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(mount.current);
    fit.fit();
    const observer = new ResizeObserver(() => fit.fit());
    observer.observe(mount.current);
    const socket = new RealtimeConnection<KubeData>({
      path:
        `/ws/kubernetes/admin/${kind}/${session.id}/` +
        kubeQuery({
          stream: true,
          reason,
          node: kind === "node-debug" ? node : undefined,
          max_frames: 2000,
          cluster_id: session.cluster_id,
          namespace,
          pod,
          container,
          command,
          tty: kind === "exec" ? true : undefined,
          stdin: kind === "exec" ? true : undefined,
        }),
      maxRetries: 0,
      onState: (s) => {
        setState(s);
        if (s === "failed" || s === "disconnected") writable = false;
      },
      onMessage: (m) => {
        const type = str(m.type, "");
        if (
          type === "terminal_started" ||
          type === "node_debug_started" ||
          type === "exec_started"
        ) {
          writable = true;
          term.focus();
        }
        if (
          type === "cluster_terminal_output" ||
          type === "node_debug_output" ||
          type === "exec_output"
        )
          term.write(str(m.data, ""));
        if (
          type.endsWith("_error") ||
          type.endsWith("_rejected") ||
          type.endsWith("_blocked")
        ) {
          setError(
            str(
              m.message,
              str(
                obj(m.payload).blocked_reason,
                "Операция отклонена сервером.",
              ),
            ),
          );
          writable = false;
        }
        if (
          type === "terminal_stopped" ||
          type === "node_debug_stopped" ||
          type === "exec_stopped"
        ) {
          setSummary(obj(m.summary));
          writable = false;
          void cache.invalidateQueries({ queryKey: ["kubernetes", "actions"] });
        }
      },
    });
    connection.current = socket;
    const input = term.onData((data) => {
      if (writable) socket.send({ type: "stdin", data });
    });
    const connectTimer = window.setTimeout(() => socket.connect(), 0);
    return () => {
      window.clearTimeout(connectTimer);
      writable = false;
      socket.close();
      connection.current = null;
      input.dispose();
      observer.disconnect();
      term.dispose();
    };
  }, [
    session.id,
    session.cluster_id,
    active,
    kind,
    node,
    reason,
    namespace,
    pod,
    container,
    command,
    user?.id,
    user?.active_project?.id,
    cache,
  ]);
  return (
    <div className="stack">
      {!active && (
        <p role="alert" className="notice">
          Сессия доступа завершена. Соединение закрыто.
        </p>
      )}
      <div className="spread">
        <KubeStatus value={state} />
        <Button
          variant="danger"
          onClick={() => {
            connection.current?.close();
            onEnd();
          }}
        >
          Закрыть соединение
        </Button>
      </div>
      {error && (
        <p role="alert" className="notice">
          {error}
        </p>
      )}
      <div
        ref={mount}
        aria-label="Терминал Kubernetes"
        style={{
          height: 420,
          background: "#11151c",
          padding: 8,
          borderRadius: 6,
        }}
      />
      {summary && <JsonDetails data={summary} label="Итог сессии" />}
      <p className="muted">
        Соединение не восстанавливается автоматически. Ввод и вывод
        регистрируются согласно политике backend.
      </p>
      <Link to={`${kubeBase}/activity?session=${session.id}`}>
        Журнал и запись сессии
      </Link>
    </div>
  );
}
export function EmergencyTools({
  session,
  workflows,
}: {
  session: KubeSession;
  workflows: KubeWorkflow[];
}) {
  const [kind, setKind] = useState<ShellKind>();
  const [node, setNode] = useState("");
  const [reason, setReason] = useState("");
  const [started, setStarted] = useState<{
    kind: ShellKind;
    node: string;
    reason: string;
  }>();
  const [maintenance, setMaintenance] = useState("");
  const [confirm, setConfirm] = useState("");
  const [review, setReview] = useState(false);
  const [result, setResult] = useState<KubeData>();
  const op = useKubeOperation();
  const available = (id: string) =>
    workflows.some(
      (w) => w.id === id && w.available && w.transport_enabled !== false,
    );
  const active = useActiveKubeSession(session);
  const blocked = (id: string) =>
    workflows.find((w) => w.id === id)?.blocked_reason ||
    "Операция не разрешена настройками backend.";
  function selectShell(value: ShellKind) {
    setKind(value);
    setReason("");
    setNode("");
    setReview(false);
  }
  function selectMaintenance(value: string) {
    setMaintenance(value);
    setReason("");
    setNode("");
    setConfirm("");
    setReview(false);
    setResult(undefined);
  }
  return (
    <Panel
      title="Аварийные операции"
      description="Операции выполняются в согласованной break-glass сессии и требуют последующего разбора."
    >
      <div className="section-body stack">
        <div className="row">
          <Button
            disabled={!active || !available("cluster_terminal")}
            title={
              !available("cluster_terminal")
                ? blocked("cluster_terminal")
                : undefined
            }
            onClick={() => selectShell("terminal")}
          >
            Терминал кластера
          </Button>
          <Button
            disabled={!active || !available("node_debug")}
            title={!available("node_debug") ? blocked("node_debug") : undefined}
            onClick={() => selectShell("node-debug")}
          >
            Диагностика узла
          </Button>
          <Button
            disabled={!active || !available("node_maintenance")}
            onClick={() => selectMaintenance("cordon")}
          >
            Запретить размещение
          </Button>
          <Button
            disabled={!active || !available("node_maintenance")}
            onClick={() => selectMaintenance("uncordon")}
          >
            Разрешить размещение
          </Button>
          <Button
            disabled={!active || !available("node_drain")}
            onClick={() => selectMaintenance("drain")}
          >
            Освободить узел
          </Button>
        </div>
        <Button
          disabled={op.pending || !active}
          onClick={() =>
            void op.run(async () => {
              setResult(
                await kubernetesApi.sessionAction(
                  session.id,
                  "restricted-context",
                  { include_manifest: true },
                ),
              );
            }, "Ограниченный контекст получен")
          }
        >
          Просмотреть ограниченный контекст доступа
        </Button>
        {result && !maintenance && (
          <JsonDetails
            data={result.restricted_context || result}
            label="Ограниченный контекст и RBAC"
          />
        )}
        {op.feedback}
      </div>
      <Drawer
        open={!!kind}
        wide
        onOpenChange={(open) => {
          if (!open) {
            setStarted(undefined);
            setKind(undefined);
          }
        }}
        title={kind === "node-debug" ? "Диагностика узла" : "Терминал кластера"}
        description={session.cluster_name}
      >
        {started ? (
          <ShellSession
            session={session}
            {...started}
            onEnd={() => setStarted(undefined)}
          />
        ) : (
          <div className="stack">
            {kind === "node-debug" && (
              <Field label="Точное имя узла" htmlFor="kt-node">
                <input
                  id="kt-node"
                  value={node}
                  onChange={(e) => setNode(e.target.value)}
                  disabled={review}
                />
              </Field>
            )}
            <Field label="Причина аварийного доступа" htmlFor="kt-reason">
              <textarea
                id="kt-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                disabled={review}
              />
            </Field>
            {review && (
              <div className="notice">
                <strong>
                  {session.cluster_name}
                  {node ? ` / ${node}` : ""}
                </strong>
                <p>
                  Будет открыт интерактивный доступ в пределах согласованной
                  сессии. Причина: {reason}
                </p>
              </div>
            )}
            <Button
              variant="primary"
              disabled={
                !active ||
                !reason.trim() ||
                (kind === "node-debug" && !node.trim()) ||
                !available(
                  kind === "terminal" ? "cluster_terminal" : "node_debug",
                )
              }
              onClick={() => {
                if (!review) setReview(true);
                else if (kind) setStarted({ kind, node, reason });
              }}
            >
              {review ? "Открыть соединение" : "Проверить и продолжить"}
            </Button>
          </div>
        )}
      </Drawer>
      <Drawer
        open={!!maintenance}
        onOpenChange={(o) => !o && setMaintenance("")}
        title={
          maintenance === "drain"
            ? "Освободить узел"
            : maintenance === "cordon"
              ? "Запретить размещение на узле"
              : "Разрешить размещение на узле"
        }
        description={session.cluster_name}
      >
        <div className="stack">
          {op.feedback}
          {result ? (
            <>
              <KubeStatus value={obj(result.action).status || result.status} />
              <JsonDetails data={result} label="Результат обслуживания" />
              <Link to={`${kubeBase}/activity?session=${session.id}`}>
                Открыть журнал
              </Link>
            </>
          ) : (
            <>
              <Field label="Точное имя узла" htmlFor="kn-name">
                <input
                  id="kn-name"
                  value={node}
                  disabled={review || op.pending}
                  onChange={(e) => setNode(e.target.value)}
                />
              </Field>
              <Field label="Причина изменения" htmlFor="kn-reason">
                <textarea
                  id="kn-reason"
                  value={reason}
                  disabled={review || op.pending}
                  onChange={(e) => setReason(e.target.value)}
                />
              </Field>
              {maintenance === "drain" && (
                <>
                  <p className="notice">
                    Backend проверит возможность эвакуации pods. Принудительное
                    удаление и потеря emptyDir данных не разрешаются этим
                    запросом.
                  </p>
                  <Field
                    label={`Введите drain Node ${node}`}
                    htmlFor="kn-confirm"
                  >
                    <input
                      id="kn-confirm"
                      value={confirm}
                      disabled={review || op.pending}
                      onChange={(e) => setConfirm(e.target.value)}
                    />
                  </Field>
                </>
              )}
              {review && (
                <p className="notice">
                  Подтвердите {maintenance} для узла {node} в{" "}
                  {session.cluster_name}.
                </p>
              )}
              <Button
                variant="danger"
                loading={op.pending}
                disabled={
                  !active ||
                  !node.trim() ||
                  !reason.trim() ||
                  (maintenance === "drain" && confirm !== `drain Node ${node}`)
                }
                onClick={() => {
                  if (!review) {
                    setReview(true);
                    return;
                  }
                  void op.run(async () => {
                    setResult(
                      await kubernetesApi.nodeAction(
                        session.cluster_id,
                        maintenance,
                        {
                          session_id: session.id,
                          node_name: node,
                          reason,
                          confirmation: confirm,
                          options: {
                            ignore_daemonsets: true,
                            delete_emptydir_data: false,
                            force: false,
                          },
                        },
                      ),
                    );
                  }, "Проверьте результат обслуживания узла");
                }}
              >
                {review ? "Подтвердить выполнение" : "Проверить и продолжить"}
              </Button>
            </>
          )}
        </div>
      </Drawer>
    </Panel>
  );
}
