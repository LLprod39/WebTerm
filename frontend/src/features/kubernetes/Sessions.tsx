import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import {
  Button,
  DataTable,
  Drawer,
  ErrorState,
  Field,
  JsonDetails,
  LoadingState,
  PageHeader,
  Panel,
} from "@/components/ui";
import { useSession } from "@/app/session";
import { formatDate } from "@/lib/utils";
import { kubernetesApi, type KubeSession } from "@/api/kubernetes";
import {
  kubeBase,
  KubeNav,
  KubeStatus,
  KubeFacts,
  useKubeCapabilities,
  useKubeOperation,
} from "./common";
const modeNames = {
  read: "Просмотр",
  write: "Изменения",
  break_glass: "Аварийный доступ",
};
function CreateSession({
  initialCluster,
  onClose,
}: {
  initialCluster: string;
  onClose: () => void;
}) {
  const clusters = useQuery({
    queryKey: ["kubernetes", "clusters"],
    queryFn: kubernetesApi.clusters,
  });
  const cap = useKubeCapabilities();
  const [cluster, setCluster] = useState(initialCluster);
  const [namespace, setNamespace] = useState("default");
  const [mode, setMode] = useState<KubeSession["mode"]>("read");
  const [ttl, setTtl] = useState(60);
  const [reason, setReason] = useState("");
  const [kinds, setKinds] = useState("*");
  const op = useKubeOperation();
  const modeAllowed = cap.data?.modes.some(
    (m) =>
      (m.id === `kubernetes_admin_${mode}` && m.active) ||
      (mode === "break_glass" && m.id === "kubernetes_break_glass" && m.active),
  );
  function changeMode(value: KubeSession["mode"]) {
    setMode(value);
    setTtl(value === "read" ? 60 : value === "write" ? 30 : 15);
    setKinds(
      value === "read"
        ? "*"
        : value === "write"
          ? "Deployment, StatefulSet, DaemonSet, Job, CronJob, Service, Ingress"
          : "Pod, Node",
    );
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    await op.run(
      async () => {
        await kubernetesApi.createSession({
          cluster_id: cluster,
          namespace: namespace.split(",").length === 1 ? namespace.trim() : "",
          mode,
          ttl_minutes: ttl,
          reason,
          allowed_namespaces: namespace
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          allowed_kinds: kinds
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        });
        onClose();
      },
      mode === "read"
        ? "Сессия просмотра создана"
        : "Сессия отправлена на согласование",
    );
  }
  return (
    <Drawer
      open
      onOpenChange={(o) => !o && onClose()}
      title="Новая сессия доступа"
      description="Сессия ограничивает кластер, область ресурсов и время выполнения операций."
    >
      <form onSubmit={submit} className="stack">
        {op.feedback}
        {cap.error && <ErrorState error={cap.error} />}
        <Field label="Кластер" htmlFor="ks-cluster">
          <select
            id="ks-cluster"
            required
            value={cluster}
            onChange={(e) => setCluster(e.target.value)}
          >
            <option value="">Выберите кластер</option>
            {clusters.data?.clusters.map((c) => (
              <option value={c.id} key={c.id}>
                {c.name} · {c.environment}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Режим доступа" htmlFor="ks-mode">
          <select
            id="ks-mode"
            value={mode}
            onChange={(e) => changeMode(e.target.value as KubeSession["mode"])}
          >
            {Object.entries(modeNames).map(([v, label]) => (
              <option
                value={v}
                key={v}
                disabled={
                  !cap.data?.modes.some(
                    (m) =>
                      m.id ===
                        (v === "break_glass"
                          ? "kubernetes_break_glass"
                          : `kubernetes_admin_${v}`) && m.active,
                  )
                }
              >
                {label}
              </option>
            ))}
          </select>
        </Field>
        {mode !== "read" && (
          <div className="notice">
            Изменения станут доступны после согласования другим администратором.
            Аварийная сессия требует последующего разбора.
          </div>
        )}
        <Field
          label="Пространство имён"
          htmlFor="ks-namespace"
          description="Пространства через запятую. Для ресурсов уровня кластера нужна область *."
        >
          <input
            id="ks-namespace"
            required
            value={namespace}
            onChange={(e) => setNamespace(e.target.value)}
          />
        </Field>
        <Field
          label="Разрешённые типы ресурсов"
          htmlFor="ks-kinds"
          description="Типы через запятую. * разрешает все типы в пределах режима."
        >
          <input
            id="ks-kinds"
            required
            value={kinds}
            onChange={(e) => setKinds(e.target.value)}
          />
        </Field>
        <Field label="Срок, минуты" htmlFor="ks-ttl">
          <input
            id="ks-ttl"
            type="number"
            min={1}
            max={mode === "read" ? 240 : mode === "write" ? 60 : 30}
            required
            value={ttl}
            onChange={(e) => setTtl(Number(e.target.value))}
          />
        </Field>
        <Field label="Цель доступа" htmlFor="ks-reason">
          <textarea
            id="ks-reason"
            required={mode !== "read"}
            maxLength={2000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </Field>
        <div className="kube-form-actions">
          <Button onClick={onClose}>Отмена</Button>
          <Button
            type="submit"
            variant="primary"
            loading={op.pending}
            disabled={!modeAllowed || !cluster}
          >
            {mode === "read" ? "Открыть сессию" : "Запросить согласование"}
          </Button>
        </div>
      </form>
    </Drawer>
  );
}
function SessionDetail({
  session,
  onClose,
}: {
  session: KubeSession;
  onClose: () => void;
}) {
  const { user } = useSession();
  const cap = useKubeCapabilities();
  const [action, setAction] = useState("");
  const [reference, setReference] = useState("");
  const [reason, setReason] = useState("");
  const [outcome, setOutcome] = useState("accepted");
  const op = useKubeOperation();
  const own = session.created_by === user?.username;
  const canApprove =
    user?.is_staff &&
    !own &&
    cap.data?.modes.some(
      (m) =>
        m.id ===
          (session.mode === "break_glass"
            ? "kubernetes_break_glass"
            : "kubernetes_admin_write") && m.active,
    );
  async function submit(e: FormEvent) {
    e.preventDefault();
    await op.run(async () => {
      await kubernetesApi.sessionAction(
        session.id,
        action,
        action === "approve"
          ? { approval_ref: reference }
          : action === "review"
            ? { outcome, summary: reason, evidence_ref: reference }
            : { reason },
      );
      onClose();
    });
  }
  return (
    <Drawer
      open
      onOpenChange={(o) => !o && onClose()}
      title={`${modeNames[session.mode]} · ${session.cluster_name}`}
      description={`Сессия ${session.id}`}
    >
      <div className="stack">
        {op.feedback}
        <KubeStatus value={session.status} />
        <KubeFacts
          data={session}
          fields={[
            ["created_by", "Запросил"],
            ["reason", "Цель"],
            ["namespace", "Пространство имён"],
            ["allowed_namespaces", "Область"],
            ["allowed_kinds", "Типы ресурсов"],
            ["allowed_verbs", "Операции"],
            ["approval_ref", "Основание согласования"],
            ["approved_by", "Согласовал"],
          ]}
        />
        <p>Доступ до {formatDate(session.expires_at)}</p>
        {own && session.status === "active" && (
          <Link
            className="btn btn-primary btn-md"
            to={`${kubeBase}/explorer/${session.id}`}
          >
            Открыть ресурсы
          </Link>
        )}
        <div className="row">
          {canApprove && session.status === "pending_approval" && (
            <Button onClick={() => setAction("approve")}>Согласовать</Button>
          )}
          {(own || user?.is_staff) &&
            ["active", "pending_approval"].includes(session.status) && (
              <Button onClick={() => setAction("revoke")}>Отозвать</Button>
            )}
          {own && session.status === "active" && (
            <Button onClick={() => setAction("close")}>Завершить</Button>
          )}
          {user?.is_staff &&
            session.mode === "break_glass" &&
            session.post_review_required &&
            !["active", "pending_approval"].includes(session.status) && (
              <Button onClick={() => setAction("review")}>Разбор сессии</Button>
            )}
        </div>
        {own && session.status === "pending_approval" && (
          <p className="notice">
            Ожидается согласование другим администратором. Собственный запрос
            согласовать нельзя.
          </p>
        )}
        {action && (
          <form className="stack kube-target" onSubmit={submit}>
            <strong>
              {action === "approve"
                ? "Согласовать область и срок доступа"
                : action === "review"
                  ? "Итог аварийной сессии"
                  : action === "close"
                    ? "Завершить текущую сессию"
                    : "Отозвать доступ"}
            </strong>
            {action === "approve" || action === "review" ? (
              <Field
                label={
                  action === "approve"
                    ? "Номер заявки или ссылка согласования"
                    : "Ссылка на доказательства"
                }
                htmlFor="ks-ref"
              >
                <input
                  id="ks-ref"
                  required={action === "approve"}
                  value={reference}
                  onChange={(e) => setReference(e.target.value)}
                />
              </Field>
            ) : null}
            {action === "review" && (
              <Field label="Результат" htmlFor="ks-outcome">
                <select
                  id="ks-outcome"
                  value={outcome}
                  onChange={(e) => setOutcome(e.target.value)}
                >
                  <option value="accepted">Принято</option>
                  <option value="needs_followup">
                    Нужны дальнейшие действия
                  </option>
                  <option value="incident_created">Создан инцидент</option>
                </select>
              </Field>
            )}
            {action !== "approve" && (
              <Field
                label={action === "review" ? "Итог разбора" : "Причина"}
                htmlFor="ks-note"
              >
                <textarea
                  id="ks-note"
                  required
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </Field>
            )}
            <Button
              type="submit"
              variant={action === "revoke" ? "danger" : "primary"}
              loading={op.pending}
            >
              Подтвердить
            </Button>
          </form>
        )}
        <JsonDetails data={session.metadata} label="Контекст сессии" />
      </div>
    </Drawer>
  );
}
export function SessionsPage() {
  const { user } = useSession();
  const [params] = useSearchParams();
  const [all, setAll] = useState(false);
  const [create, setCreate] = useState(false);
  const [selected, setSelected] = useState<KubeSession>();
  const q = useQuery({
    queryKey: ["kubernetes", "sessions", all],
    queryFn: () => kubernetesApi.sessions(all),
    refetchInterval: 20_000,
  });
  return (
    <>
      <PageHeader
        eyebrow="Kubernetes"
        title="Сессии доступа"
        description="Ограниченный по времени доступ. Запросы изменений согласует другой администратор."
        actions={
          <Button variant="primary" onClick={() => setCreate(true)}>
            <Plus size={16} /> Запросить доступ
          </Button>
        }
      />
      <KubeNav />
      {user?.is_staff && (
        <label className="row">
          <input
            type="checkbox"
            checked={all}
            onChange={(e) => setAll(e.target.checked)}
          />{" "}
          Показывать сессии всех пользователей
        </label>
      )}
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} retry={() => q.refetch()} />
      ) : (
        <Panel title="Сессии">
          <DataTable
            rows={(q.data?.sessions || []).filter(
              (s) =>
                !params.get("cluster") ||
                s.cluster_id === params.get("cluster"),
            )}
            rowKey={(r) => r.id}
            searchValue={(r) =>
              `${r.cluster_name} ${r.namespace} ${r.created_by} ${r.reason}`
            }
            emptyTitle="Сессий пока нет"
            emptyDescription="Запросите сессию для просмотра live-ресурсов или контролируемого изменения."
            columns={[
              {
                key: "cluster",
                label: "Кластер и область",
                render: (r) => (
                  <Button variant="ghost" onClick={() => setSelected(r)}>
                    {r.cluster_name} /{" "}
                    {r.namespace || r.allowed_namespaces.join(", ")}
                  </Button>
                ),
              },
              { key: "mode", label: "Режим", render: (r) => modeNames[r.mode] },
              {
                key: "owner",
                label: "Пользователь",
                render: (r) => r.created_by,
              },
              {
                key: "status",
                label: "Статус",
                render: (r) => <KubeStatus value={r.status} />,
              },
              {
                key: "expires",
                label: "Доступ до",
                render: (r) => formatDate(r.expires_at),
              },
              {
                key: "actions",
                label: "",
                render: (r) => (
                  <Button size="sm" onClick={() => setSelected(r)}>
                    Подробнее
                  </Button>
                ),
              },
            ]}
          />
        </Panel>
      )}
      {create && (
        <CreateSession
          initialCluster={params.get("cluster") || ""}
          onClose={() => setCreate(false)}
        />
      )}{" "}
      {selected && (
        <SessionDetail
          session={
            q.data?.sessions.find((s) => s.id === selected.id) || selected
          }
          onClose={() => setSelected(undefined)}
        />
      )}
    </>
  );
}
