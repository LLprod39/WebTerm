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
  PageHeader,
  Panel,
  Tabs,
} from "@/components/ui";
import { useSession } from "@/app/session";
import { formatDate, downloadText } from "@/lib/utils";
import { kubernetesApi, type KubeData } from "@/api/kubernetes";
import { kubeWorkflows, type KubeRequest } from "@/api/kubernetes-workflows";
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

export const requestLabels: Record<string, string> = {
  "k8s.rollout.restart": "Перезапуск нагрузки",
  "k8s.workload.scale": "Число реплик",
  "k8s.resource.apply": "Применение манифеста",
  "k8s.resource.patch": "Изменение полей",
  "k8s.resource.delete": "Удаление ресурса",
  "fleet.rollout.pause": "Приостановка Fleet",
  "fleet.rollout.resume": "Продолжение Fleet",
  "gitops.create_merge_request": "Изменение через GitOps",
  "devtron.open_rollback": "Откат Devtron",
};
export function CreateRequest({
  initialAction = "k8s.rollout.restart",
  initialTarget = {},
  onClose,
}: {
  initialAction?: string;
  initialTarget?: KubeData;
  onClose: () => void;
}) {
  const nav = useNavigate();
  const op = useKubeOperation();
  const [action, setAction] = useState(initialAction);
  const [target, setTarget] = useState<KubeData>(initialTarget);
  const [reason, setReason] = useState("");
  const [patch, setPatch] = useState("");
  const [review, setReview] = useState(false);
  const clusters = useQuery({
    queryKey: ["kubernetes", "clusters"],
    queryFn: kubernetesApi.clusters,
  });
  const delivery = useQuery({
    queryKey: ["kubernetes", "request-targets", action],
    queryFn: () =>
      kubeWorkflows.delivery(action.startsWith("fleet.") ? "fleet" : "devtron"),
    enabled: action.startsWith("fleet.") || action.startsWith("devtron."),
  });
  const proofs = useQuery({
    queryKey: ["kubernetes", "dry-run-proofs"],
    queryFn: () =>
      kubernetesApi.actions({ verb: "dry_run_apply", status: "dry_run" }),
    enabled: action === "k8s.resource.apply",
  });
  const set = (key: string, value: unknown) =>
    setTarget((t) => ({ ...t, [key]: value }));
  const field = (
    key: string,
    label: string,
    type = "text",
    description?: string,
  ) => (
    <Field
      key={key}
      label={label}
      htmlFor={`rq-${key}`}
      description={description}
    >
      <input
        id={`rq-${key}`}
        type={type}
        value={str(target[key], "")}
        disabled={review || op.pending}
        onChange={(e) =>
          set(key, type === "number" ? Number(e.target.value) : e.target.value)
        }
      />
    </Field>
  );
  const resource = action.startsWith("k8s.") && action !== "k8s.resource.apply";
  const needsCluster = resource || action === "gitops.create_merge_request";
  const exact = `delete ${str(target.kind, "")} ${str(target.namespace, "")}/${str(target.name, "")}`;
  async function submit() {
    await op.run(async () => {
      const payload = { ...target };
      if (action === "k8s.resource.delete")
        payload.propagation_policy = payload.propagation_policy || "Foreground";
      if (
        action === "k8s.workload.scale" &&
        (!Number.isInteger(target.replicas) || Number(target.replicas) < 0)
      )
        throw new Error(
          "Число реплик должно быть целым неотрицательным числом.",
        );
      if (action === "k8s.resource.patch") {
        let value: unknown;
        try {
          value = JSON.parse(patch);
        } catch {
          throw new Error("Проверьте JSON изменяемых полей.");
        }
        if (!value || typeof value !== "object")
          throw new Error(
            "Изменение должно быть объектом или массивом операций.",
          );
        payload.patch_body = value;
      }
      const result = await kubeWorkflows.create(action, payload, reason.trim());
      onClose();
      nav(`${kubeBase}/requests/${result.request.id}`);
    }, "Заявка создана");
  }
  const valid =
    reason.trim() &&
    (!resource ||
      (target.cluster_id && target.namespace && target.kind && target.name)) &&
    (action !== "k8s.resource.delete" || target.confirmation === exact) &&
    (action !== "k8s.resource.apply" || target.dry_run_action_id);
  return (
    <Drawer
      open
      wide
      onOpenChange={(v) => {
        if (!v && !op.pending) onClose();
      }}
      title="Заявка на изменение"
      description="Backend подготовит область воздействия, условия выполнения и план проверки. Создание заявки не выполняет изменение."
    >
      <div className="stack">
        {op.feedback}
        <Field label="Операция" htmlFor="rq-action">
          <select
            id="rq-action"
            value={action}
            disabled={review || op.pending}
            onChange={(e) => {
              setAction(e.target.value);
              setTarget({});
              setPatch("");
            }}
          >
            {Object.entries(requestLabels).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        {needsCluster && (
          <Field label="Кластер" htmlFor="rq-cluster">
            <select
              id="rq-cluster"
              value={str(target.cluster_id, "")}
              disabled={review || op.pending}
              onChange={(e) => set("cluster_id", e.target.value)}
            >
              <option value="">
                {action === "gitops.create_merge_request"
                  ? "Без привязки к кластеру"
                  : "Выберите кластер"}
              </option>
              {clusters.data?.clusters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            {clusters.error && <ErrorState error={clusters.error} />}
          </Field>
        )}
        {resource && (
          <div className="form-grid">
            {field("namespace", "Пространство имён")}
            {field(
              "kind",
              "Kind ресурса",
              "text",
              "Например, Deployment или ConfigMap. Регистр важен для подтверждения удаления.",
            )}
            {field("name", "Точное имя")}
            {field(
              "api_version",
              "Версия API",
              "text",
              "Например, apps/v1 или v1.",
            )}
          </div>
        )}
        {action === "k8s.workload.scale" &&
          field("replicas", "Желаемое число реплик", "number")}
        {action === "k8s.resource.apply" && (
          <Field
            label="Успешная проверка манифеста"
            htmlFor="rq-proof"
            description="Создайте dry-run в ресурсах кластера. Эта заявка закрепит точный результат проверки."
          >
            <select
              id="rq-proof"
              value={str(target.dry_run_action_id, "")}
              disabled={review || op.pending}
              onChange={(e) => set("dry_run_action_id", e.target.value)}
            >
              <option value="">Выберите проверку</option>
              {proofs.data?.actions.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.cluster_name} · {a.namespace}/{a.resource_name} ·{" "}
                  {formatDate(a.created_at)}
                </option>
              ))}
            </select>
            {proofs.error && <ErrorState error={proofs.error} />}
            <Link to={`${kubeBase}/sessions`}>
              Открыть сессию для проверки манифеста
            </Link>
          </Field>
        )}
        {action === "k8s.resource.patch" && (
          <>
            <Field label="Тип изменения" htmlFor="rq-patch-type">
              <select
                id="rq-patch-type"
                disabled={review || op.pending}
                value={str(target.patch_type, "merge")}
                onChange={(e) => set("patch_type", e.target.value)}
              >
                <option value="merge">JSON Merge Patch</option>
                <option value="strategic">Strategic Merge Patch</option>
                <option value="json">JSON Patch</option>
              </select>
            </Field>
            <Field label="Изменяемые поля JSON" htmlFor="rq-patch">
              <textarea
                id="rq-patch"
                className="kube-code"
                value={patch}
                onChange={(e) => setPatch(e.target.value)}
                disabled={review || op.pending}
              />
            </Field>
          </>
        )}
        {action === "k8s.resource.delete" && (
          <>
            {field("confirmation", `Для удаления введите: ${exact}`)}
            <Field label="Удаление зависимых ресурсов" htmlFor="rq-propagation">
              <select
                id="rq-propagation"
                value={str(target.propagation_policy, "Foreground")}
                onChange={(e) => set("propagation_policy", e.target.value)}
                disabled={review || op.pending}
              >
                <option value="Foreground">
                  Дождаться удаления зависимостей
                </option>
                <option value="Background">Удалять зависимости в фоне</option>
                <option value="Orphan">Сохранить зависимые ресурсы</option>
              </select>
            </Field>
          </>
        )}
        {(action.startsWith("fleet.") || action.startsWith("devtron.")) && (
          <Field
            label={
              action.startsWith("fleet.")
                ? "Fleet bundle"
                : "Приложение Devtron"
            }
            htmlFor="rq-delivery"
          >
            <select
              id="rq-delivery"
              disabled={review || op.pending}
              value={str(
                target[action.startsWith("fleet.") ? "bundle_id" : "app_id"],
                "",
              )}
              onChange={(e) =>
                set(
                  action.startsWith("fleet.") ? "bundle_id" : "app_id",
                  e.target.value,
                )
              }
            >
              <option value="">Выберите объект</option>
              {rows(
                delivery.data?.[
                  action.startsWith("fleet.") ? "bundles" : "apps"
                ],
              ).map((item) => (
                <option key={str(item.id)} value={str(item.id)}>
                  {str(item.name)}
                </option>
              ))}
            </select>
            {delivery.error && <ErrorState error={delivery.error} />}
          </Field>
        )}
        {action === "gitops.create_merge_request" && (
          <>
            {field("repository", "URL репозитория")}
            {field("path", "Путь файла в репозитории")}
            <div className="form-grid">
              {field("source_branch", "Ветка изменений")}
              {field("target_branch", "Целевая ветка")}
            </div>
            {field("title", "Название изменения")}
            {field(
              "diff_summary",
              "Что изменится",
              "text",
              "Кратко опишите изменения декларативной конфигурации.",
            )}
          </>
        )}
        <Field label="Причина изменения" htmlFor="rq-reason">
          <textarea
            id="rq-reason"
            value={reason}
            maxLength={1000}
            onChange={(e) => setReason(e.target.value)}
            disabled={review || op.pending}
          />
        </Field>
        {review && (
          <div className="notice">
            <strong>{requestLabels[action]}</strong>
            <KubeFacts
              data={target}
              fields={Object.keys(target)
                .filter((k) => k !== "confirmation")
                .map((k) => [k, k])}
            />
            <p>{reason}</p>
          </div>
        )}
        <div className="row">
          <Button
            disabled={op.pending}
            onClick={() => (review ? setReview(false) : onClose())}
          >
            {review ? "Изменить параметры" : "Отмена"}
          </Button>
          <Button
            variant="primary"
            disabled={!valid}
            loading={op.pending}
            onClick={() => (review ? void submit() : setReview(true))}
          >
            {review ? "Создать заявку" : "Рассмотреть заявку"}
          </Button>
        </div>
      </div>
    </Drawer>
  );
}

function RequestTransition({
  item,
  mode,
  onClose,
}: {
  item: KubeRequest;
  mode: "approve" | "execute" | "verify";
  onClose: () => void;
}) {
  const op = useKubeOperation();
  const [reference, setReference] = useState(item.approval_ref);
  const [summary, setSummary] = useState("");
  const [outcome, setOutcome] = useState("succeeded");
  const [checks, setChecks] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [manifest, setManifest] = useState("");
  const [review, setReview] = useState(false);
  const sessions = useQuery({
    queryKey: ["kubernetes", "sessions", false],
    queryFn: () => kubernetesApi.sessions(),
    enabled: mode === "execute",
  });
  const eligible = (sessions.data?.sessions || []).filter(
    (s) =>
      s.status === "active" &&
      s.mode === "write" &&
      (!item.target.cluster_id || s.cluster_id === item.target.cluster_id),
  );
  async function submit() {
    await op.run(async () => {
      if (mode === "approve")
        await kubeWorkflows.approve(item.id, {
          approval_ref: reference,
          summary,
        });
      else if (mode === "verify")
        await kubeWorkflows.verify(item.id, {
          outcome,
          summary,
          external_ref: reference,
          checks: checks
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean),
        });
      else {
        const body: KubeData = { session_id: sessionId };
        if (item.action === "k8s.resource.apply") {
          let data: unknown;
          try {
            data = JSON.parse(manifest);
          } catch {
            throw new Error(
              "Манифест для выполнения заявки должен быть корректным JSON.",
            );
          }
          if (!data || typeof data !== "object" || Array.isArray(data))
            throw new Error("Ожидается один объект манифеста.");
          body.manifest = data;
        }
        await kubeWorkflows.execute(item.id, body);
      }
      onClose();
    }, "Состояние заявки обновлено");
  }
  const valid =
    mode === "approve"
      ? !!reference.trim()
      : mode === "verify"
        ? !!summary.trim()
        : !!sessionId &&
          (item.action !== "k8s.resource.apply" || !!manifest.trim());
  return (
    <Drawer
      open
      onOpenChange={(v) => {
        if (!v && !op.pending) onClose();
      }}
      title={
        mode === "approve"
          ? "Согласование изменения"
          : mode === "execute"
            ? "Выполнение согласованной заявки"
            : "Проверка результата"
      }
      description={requestLabels[item.action]}
    >
      <div className="stack">
        <KubeFacts
          data={item.target}
          fields={[
            ["cluster_name", "Кластер"],
            ["namespace", "Пространство"],
            ["kind", "Тип"],
            ["name", "Имя"],
          ]}
        />
        <p>{item.reason}</p>
        {op.feedback}
        {mode !== "execute" && (
          <>
            {
              <Field
                label={
                  mode === "approve"
                    ? "Номер или ссылка согласования"
                    : "Ссылка на доказательства"
                }
                htmlFor="rt-reference"
              >
                <input
                  id="rt-reference"
                  disabled={review || op.pending}
                  value={reference}
                  onChange={(e) => setReference(e.target.value)}
                />
              </Field>
            }
            <Field
              label={
                mode === "approve"
                  ? "Комментарий согласующего"
                  : "Что проверено и с каким результатом"
              }
              htmlFor="rt-summary"
            >
              <textarea
                id="rt-summary"
                disabled={review || op.pending}
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                maxLength={1000}
              />
            </Field>
          </>
        )}
        {mode === "verify" && (
          <>
            <Field label="Результат проверки" htmlFor="rt-outcome">
              <select
                id="rt-outcome"
                value={outcome}
                onChange={(e) => setOutcome(e.target.value)}
                disabled={review || op.pending}
              >
                <option value="succeeded">Подтверждён</option>
                <option value="failed">Не подтверждён</option>
              </select>
            </Field>
            <Field
              label="Выполненные проверки — по одной в строке"
              htmlFor="rt-checks"
            >
              <textarea
                id="rt-checks"
                value={checks}
                onChange={(e) => setChecks(e.target.value)}
                disabled={review || op.pending}
              />
            </Field>
          </>
        )}
        {mode === "execute" && (
          <>
            <p className="notice">
              Будут выполнены параметры, закреплённые в согласованной заявке.
              Права, срок сессии и разрешение владельца ресурса проверяются
              повторно.
            </p>
            <Field label="Активная сессия изменений" htmlFor="rt-session">
              <select
                id="rt-session"
                value={sessionId}
                disabled={review || op.pending}
                onChange={(e) => setSessionId(e.target.value)}
              >
                <option value="">Выберите сессию</option>
                {eligible.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.cluster_name} · {s.allowed_namespaces.join(", ")} · до{" "}
                    {formatDate(s.expires_at)}
                  </option>
                ))}
              </select>
              {sessions.error && <ErrorState error={sessions.error} />}
            </Field>
            {item.action === "k8s.resource.apply" && (
              <Field
                label="Точный манифест JSON из согласованной проверки"
                htmlFor="rt-manifest"
                description="Backend сверит отпечаток с dry-run. Изменённый манифест будет отклонён."
              >
                <textarea
                  id="rt-manifest"
                  className="kube-code"
                  value={manifest}
                  onChange={(e) => setManifest(e.target.value)}
                  disabled={review || op.pending}
                />
              </Field>
            )}
          </>
        )}
        {review && (
          <p className="notice">
            {mode === "execute"
              ? "Подтвердите выполнение реального изменения."
              : mode === "approve"
                ? "Согласование разрешит дальнейшее выполнение согласно политике."
                : "Результат и доказательства будут сохранены в журнале заявки."}
          </p>
        )}
        <div className="row">
          <Button
            disabled={op.pending}
            onClick={() => (review ? setReview(false) : onClose())}
          >
            {review ? "Вернуться" : "Отмена"}
          </Button>
          <Button
            variant={mode === "execute" ? "danger" : "primary"}
            loading={op.pending}
            disabled={!valid}
            onClick={() => (review ? void submit() : setReview(true))}
          >
            {review ? "Подтвердить" : "Проверить и продолжить"}
          </Button>
        </div>
      </div>
    </Drawer>
  );
}

export function RequestsPage() {
  const { user } = useSession();
  const [all, setAll] = useState(false);
  const [status, setStatus] = useState("");
  const [create, setCreate] = useState(false);
  const q = useQuery({
    queryKey: ["kubernetes", "requests", all, status],
    queryFn: () => kubeWorkflows.requests(all, status),
    refetchInterval: 15_000,
  });
  return (
    <>
      <PageHeader
        eyebrow="Kubernetes"
        title="Заявки на изменения"
        description="От намерения и согласования до подтверждённого результата."
        actions={
          <Button variant="primary" onClick={() => setCreate(true)}>
            Создать заявку
          </Button>
        }
      />
      <KubeNav />
      <div className="stack">
        <div className="row">
          <Field label="Состояние" htmlFor="requests-status">
            <select
              id="requests-status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">Все состояния</option>
              {[
                "pending_approval",
                "approved_external",
                "executed_native",
                "verified_external",
                "verified_native",
                "verification_failed",
                "execution_blocked",
              ].map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
          {user?.is_staff && (
            <label className="row">
              <input
                type="checkbox"
                checked={all}
                onChange={(e) => setAll(e.target.checked)}
              />
              Заявки всех сотрудников
            </label>
          )}
        </div>
        <Panel>
          {q.isPending ? (
            <LoadingState />
          ) : q.error ? (
            <ErrorState error={q.error} retry={() => q.refetch()} />
          ) : (
            <DataTable
              rows={q.data?.requests || []}
              rowKey={(r) => r.id}
              searchValue={(r) => `${r.action} ${r.cluster} ${r.reason}`}
              emptyTitle="Заявок пока нет"
              columns={[
                {
                  key: "action",
                  label: "Изменение",
                  render: (r) => (
                    <Link
                      className="text-link"
                      to={`${kubeBase}/requests/${r.id}`}
                    >
                      {requestLabels[r.action] || r.action}
                      <small className="intel-block muted">{r.reason}</small>
                    </Link>
                  ),
                },
                {
                  key: "target",
                  label: "Область",
                  render: (r) =>
                    `${r.cluster} ${str(r.target.namespace, "")} / ${str(r.target.name, r.target.bundle_name ? str(r.target.bundle_name) : "")}`,
                },
                {
                  key: "status",
                  label: "Состояние",
                  render: (r) => <KubeStatus value={r.status} />,
                },
                {
                  key: "owner",
                  label: "Инициатор",
                  render: (r) => r.requested_by,
                },
                {
                  key: "created",
                  label: "Создана",
                  render: (r) => formatDate(r.created_at),
                },
              ]}
            />
          )}
        </Panel>
        {q.data && q.data.count === q.data.limit && (
          <p className="muted">
            Показаны последние {q.data.limit} заявок. Уточните фильтр состояния.
          </p>
        )}
      </div>
      {create && <CreateRequest onClose={() => setCreate(false)} />}
    </>
  );
}
export function RequestPage() {
  const { id = "" } = useParams();
  const { user } = useSession();
  const [tab, setTab] = useState("review");
  const [transition, setTransition] = useState<
    "approve" | "execute" | "verify"
  >();
  const q = useQuery({
    queryKey: ["kubernetes", "request", id],
    queryFn: () => kubeWorkflows.request(id),
    refetchInterval: 15_000,
  });
  const report = useQuery({
    queryKey: ["kubernetes", "request-report", id],
    queryFn: () => kubeWorkflows.report(id),
  });
  const readiness = useQuery({
    queryKey: ["kubernetes", "readiness"],
    queryFn: kubernetesApi.readiness,
  });
  const item = q.data?.request;
  const canExecute =
    obj(readiness.data?.access_policy).can_execute_approved_action === true;
  return (
    <>
      <PageHeader
        eyebrow="Kubernetes"
        title={
          item
            ? requestLabels[item.action] || item.action
            : "Заявка на изменение"
        }
        description={item?.reason}
      />
      <KubeNav />
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : (
        item && (
          <div className="stack">
            <div className="spread">
              <div className="row">
                <KubeStatus value={item.status} />
                <span>
                  {item.requested_by} · {formatDate(item.created_at)}
                </span>
              </div>
              <div className="row">
                {user?.is_staff &&
                  item.status === "pending_approval" &&
                  item.requested_by !== user.username && (
                    <Button
                      variant="primary"
                      onClick={() => setTransition("approve")}
                    >
                      Согласовать
                    </Button>
                  )}
                {user?.is_staff &&
                  item.status === "approved_external" &&
                  item.action.startsWith("k8s.") && (
                    <Button
                      disabled={!canExecute}
                      title={
                        !canExecute
                          ? "Native execution не разрешён правами или настройками backend"
                          : undefined
                      }
                      variant="danger"
                      onClick={() => setTransition("execute")}
                    >
                      Выполнить в WebTerm
                    </Button>
                  )}
                {user?.is_staff &&
                  ["approved_external", "executed_native"].includes(
                    item.status,
                  ) && (
                    <Button onClick={() => setTransition("verify")}>
                      Зафиксировать проверку
                    </Button>
                  )}
                <Button
                  onClick={() =>
                    downloadText(
                      `kubernetes-request-${id}.json`,
                      JSON.stringify(report.data || item, null, 2),
                      "application/json",
                    )
                  }
                >
                  Экспорт отчёта
                </Button>
              </div>
            </div>
            {item.requested_by === user?.username &&
              item.status === "pending_approval" && (
                <p className="notice">
                  Заявку должен согласовать другой сотрудник с правами
                  администратора.
                </p>
              )}
            <Tabs
              value={tab}
              onChange={setTab}
              items={[
                { value: "review", label: "Область и план" },
                { value: "result", label: "Результат" },
                { value: "audit", label: "Журнал" },
              ]}
            />
            {tab === "review" && (
              <>
                <Panel title="Цель изменения">
                  <div className="section-body">
                    <KubeFacts
                      data={item.target}
                      fields={Object.keys(item.target)
                        .filter(
                          (k) =>
                            ![
                              "patch_body",
                              "confirmation",
                              "changes",
                              "manifest_fingerprint",
                            ].includes(k),
                        )
                        .map((k) => [k, k])}
                    />
                    {item.target.patch_body !== undefined && (
                      <JsonDetails
                        data={item.target.patch_body}
                        label="Согласуемые поля"
                      />
                    )}
                    <p>{str(item.preview.summary, "")}</p>
                  </div>
                </Panel>
                <Panel title="Область воздействия и план проверки">
                  <div className="section-body">
                    <p>{str(item.preview.blast_radius, "")}</p>
                    <ul>
                      {Array.isArray(item.preview.expected_verification) &&
                        item.preview.expected_verification.map((v, i) => (
                          <li key={i}>{str(v)}</li>
                        ))}
                    </ul>
                    <JsonDetails
                      data={item.preview.rollback_plan}
                      label="План возврата"
                    />
                    <JsonDetails
                      data={item.preview}
                      label="Полная предварительная проверка"
                    />
                    <JsonDetails
                      data={item.execution_policy}
                      label="Политика выполнения"
                    />
                  </div>
                </Panel>
              </>
            )}
            {tab === "result" && (
              <Panel title="Результат и доказательства">
                <div className="section-body">
                  <KubeFacts
                    data={item.report}
                    fields={[
                      ["status", "Состояние"],
                      ["summary", "Вывод"],
                      ["approved_by", "Согласовал"],
                      ["executed_by", "Выполнил"],
                      ["verified_by", "Проверил"],
                      ["external_ref", "Внешнее подтверждение"],
                    ]}
                  />
                  <JsonDetails data={item.report} label="Полный отчёт" />
                  {report.error && <ErrorState error={report.error} />}
                </div>
              </Panel>
            )}
            {tab === "audit" && (
              <Panel title="Журнал заявки">
                {report.isPending ? (
                  <LoadingState />
                ) : report.error ? (
                  <ErrorState error={report.error} />
                ) : (
                  <KubeEvents events={rows(report.data?.timeline)} />
                )}
              </Panel>
            )}
            {transition && (
              <RequestTransition
                item={item}
                mode={transition}
                onClose={() => setTransition(undefined)}
              />
            )}
          </div>
        )
      )}
    </>
  );
}
