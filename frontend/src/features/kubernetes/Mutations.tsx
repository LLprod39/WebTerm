import { useState } from "react";
import { Link } from "react-router-dom";
import { Button, DataTable, Drawer, Field, JsonDetails } from "@/components/ui";
import {
  kubernetesApi,
  type KubeData,
  type KubeSession,
  type KubeWorkflow,
  type ResourceTarget,
} from "@/api/kubernetes";
import {
  kubeBase,
  KubeFacts,
  KubeStatus,
  obj,
  rows,
  str,
  useKubeOperation,
} from "./common";
import { useActiveKubeSession } from "./common";
export type MutationKind = "apply" | "patch" | "scale" | "restart" | "delete";
const titles: Record<MutationKind, string> = {
  apply: "Применить манифест",
  patch: "Изменить поля ресурса",
  scale: "Изменить число реплик",
  restart: "Перезапустить нагрузку",
  delete: "Удалить ресурс",
};
export function deleteConfirmation(target: ResourceTarget) {
  return `delete ${target.kind} ${target.namespace ? target.namespace + "/" : ""}${target.name}`;
}
export function MutationDrawer({
  session,
  target,
  kind,
  workflows,
  onClose,
}: {
  session: KubeSession;
  target: ResourceTarget;
  kind: MutationKind;
  workflows: KubeWorkflow[];
  onClose: () => void;
}) {
  const [manifest, setManifest] = useState("");
  const [patch, setPatch] = useState("");
  const [patchType, setPatchType] = useState("merge");
  const [namespace, setNamespace] = useState(target.namespace);
  const [replicas, setReplicas] = useState(1);
  const [reason, setReason] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [review, setReview] = useState(false);
  const [proof, setProof] = useState<KubeData>();
  const [result, setResult] = useState<KubeData>();
  const [validation, setValidation] = useState<KubeData>();
  const op = useKubeOperation();
  const capability = workflows.find(
    (w) =>
      w.id ===
      (kind === "apply"
        ? "apply_yaml"
        : kind === "restart"
          ? "rollout_restart"
          : kind),
  );
  const dryAvailable =
    workflows.some((w) => w.id === "dry_run_apply" && w.available) &&
    session.mode === "write";
  const exact = deleteConfirmation(target);
  const active = useActiveKubeSession(session);
  const available = active && session.mode !== "read" && capability?.available;
  const actionId = str(obj(proof?.action).id, "");
  const body = { session_id: session.id, ...target, namespace };
  function editManifest(value: string) {
    setManifest(value);
    setProof(undefined);
    setValidation(undefined);
    setReview(false);
  }
  async function dryRun() {
    await op.run(async () => {
      const p = await kubernetesApi.resourceWrite(
        session.cluster_id,
        "dry-run-apply",
        {
          session_id: session.id,
          manifest_yaml: manifest,
          namespace,
          resource: target.resource,
        },
      );
      setProof(p);
      setReview(false);
    }, "Проверка выполнена без изменений в кластере");
  }
  async function execute() {
    await op.run(async () => {
      const data: KubeData = { ...body, reason };
      if (kind === "apply") {
        if (!actionId || !proof)
          throw new Error("Сначала выполните проверку текущего манифеста.");
        Object.assign(data, {
          manifest_yaml: manifest,
          dry_run_action_id: actionId,
        });
      }
      if (kind === "patch") {
        let parsed: unknown;
        try {
          parsed = JSON.parse(patch);
        } catch {
          throw new Error("Укажите корректный JSON patch.");
        }
        if (parsed === null || typeof parsed !== "object")
          throw new Error("Patch должен быть объектом или массивом операций.");
        Object.assign(data, { patch: parsed, patch_type: patchType });
      }
      if (kind === "scale") data.replicas = replicas;
      if (kind === "delete")
        Object.assign(data, { confirmation, propagation_policy: "Foreground" });
      const r = await kubernetesApi.resourceWrite(
        session.cluster_id,
        kind,
        data,
      );
      setResult(r);
      setProof(undefined);
      setReview(false);
    }, "Операция выполнена. Проверьте состояние ресурса и итоговый отчёт.");
  }
  const canReview =
    available &&
    reason.trim() &&
    (kind !== "apply" || !!actionId) &&
    (kind !== "delete" || confirmation === exact) &&
    (kind !== "patch" || !!patch.trim());
  return (
    <Drawer
      open
      wide
      onOpenChange={(o) => !o && onClose()}
      title={titles[kind]}
      description={`${session.cluster_name} · сессия до ${new Date(session.expires_at).toLocaleString("ru-RU")}`}
    >
      <div className="stack">
        {op.feedback}
        <div className="kube-target">
          <KubeFacts
            data={{ ...target, cluster: session.cluster_name }}
            fields={[
              ["cluster", "Кластер"],
              ["namespace", "Пространство имён"],
              ["kind", "Тип"],
              ["name", "Ресурс"],
            ]}
          />
        </div>
        {result ? (
          <>
            <KubeStatus value={obj(result.action).status || "completed"} />
            <JsonDetails data={result} label="Результат операции" />
            <Link
              className="btn btn-secondary btn-md"
              to={`${kubeBase}/activity?session=${session.id}`}
            >
              Открыть журнал действий
            </Link>
            <Button onClick={onClose}>Закрыть</Button>
          </>
        ) : (
          <>
            {!available && (
              <p className="notice">
                {!active
                  ? "Сессия завершена или истекла."
                  : capability?.blocked_reason ||
                    "Операция недоступна для этой сессии."}
              </p>
            )}
            {kind === "apply" && (
              <>
                <Field
                  label="Пространство имён манифеста"
                  htmlFor="km-namespace"
                >
                  <input
                    id="km-namespace"
                    value={namespace}
                    disabled={op.pending || review}
                    onChange={(e) => {
                      setNamespace(e.target.value);
                      setProof(undefined);
                      setValidation(undefined);
                    }}
                  />
                </Field>
                <Field
                  label="Манифест YAML"
                  htmlFor="km-manifest"
                  description="Вставьте декларативный манифест. После каждого изменения требуется новая проверка."
                >
                  <textarea
                    id="km-manifest"
                    className="kube-code"
                    value={manifest}
                    disabled={op.pending || review}
                    onChange={(e) => editManifest(e.target.value)}
                    spellCheck={false}
                  />
                </Field>
                <div className="row">
                  <Button
                    disabled={
                      !manifest.trim() ||
                      !dryAvailable ||
                      !active ||
                      op.pending ||
                      review
                    }
                    onClick={() =>
                      void op.run(async () => {
                        setValidation(
                          await kubernetesApi.resourceWrite(
                            session.cluster_id,
                            "schema-validate",
                            {
                              session_id: session.id,
                              manifest_yaml: manifest,
                              namespace,
                              resource: target.resource,
                            },
                          ),
                        );
                      }, "Проверка схемы завершена")
                    }
                  >
                    Проверить схему
                  </Button>
                  <Button
                    disabled={
                      !manifest.trim() ||
                      !dryAvailable ||
                      !active ||
                      op.pending ||
                      review
                    }
                    loading={op.pending}
                    onClick={() => void dryRun()}
                  >
                    Проверить на сервере
                  </Button>
                </div>
                {validation && (
                  <JsonDetails
                    data={validation}
                    label="Результат проверки схемы"
                  />
                )}
                {proof && (
                  <div className="kube-manifest-review stack">
                    <strong>Манифест прошёл проверку Kubernetes</strong>
                    <KubeFacts
                      data={obj(proof.target)}
                      fields={[
                        ["kind", "Тип"],
                        ["namespace", "Область"],
                        ["name", "Имя"],
                      ]}
                    />
                    <p className="muted">
                      Сравнение отправленного манифеста с ответом dry-run
                      показывает нормализацию сервером. Это не сравнение с
                      текущим состоянием ресурса.
                    </p>
                    <DataTable
                      rows={rows(obj(proof.diff).changes)}
                      rowKey={(r) => str(r.path)}
                      emptyTitle="Сервер не изменил отправленные поля"
                      columns={[
                        {
                          key: "path",
                          label: "Поле",
                          render: (r) => <code>{str(r.path)}</code>,
                        },
                        {
                          key: "before",
                          label: "Отправлено",
                          render: (r) => str(r.before),
                        },
                        {
                          key: "after",
                          label: "Ответ сервера",
                          render: (r) => str(r.after),
                        },
                      ]}
                    />
                    <JsonDetails
                      data={proof.ownership}
                      label="Владелец ресурса"
                    />
                  </div>
                )}
              </>
            )}
            {kind === "patch" && (
              <>
                <Field label="Тип patch" htmlFor="km-patch-type">
                  <select
                    id="km-patch-type"
                    disabled={review || op.pending}
                    value={patchType}
                    onChange={(e) => setPatchType(e.target.value)}
                  >
                    <option value="merge">JSON Merge Patch</option>
                    <option value="json">JSON Patch</option>
                    <option value="strategic">Strategic Merge Patch</option>
                  </select>
                </Field>
                <Field label="Изменяемые поля JSON" htmlFor="km-patch">
                  <textarea
                    id="km-patch"
                    className="kube-code"
                    disabled={review || op.pending}
                    value={patch}
                    onChange={(e) => setPatch(e.target.value)}
                    spellCheck={false}
                  />
                </Field>
              </>
            )}
            {kind === "scale" && (
              <Field label="Желаемое число реплик" htmlFor="km-replicas">
                <input
                  id="km-replicas"
                  type="number"
                  min={0}
                  step={1}
                  required
                  disabled={review || op.pending}
                  value={replicas}
                  onChange={(e) => setReplicas(Number(e.target.value))}
                />
              </Field>
            )}
            {kind === "restart" && (
              <p className="notice">
                Будет запущен rolling restart выбранной нагрузки. Существующие
                экземпляры будут заменяться по стратегии Kubernetes.
              </p>
            )}
            <Field label="Причина изменения" htmlFor="km-reason">
              <textarea
                id="km-reason"
                required
                disabled={review || op.pending}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={2000}
              />
            </Field>
            {kind === "delete" && (
              <Field
                label={`Для удаления введите: ${exact}`}
                htmlFor="km-confirm"
              >
                <input
                  id="km-confirm"
                  autoComplete="off"
                  value={confirmation}
                  onChange={(e) => setConfirmation(e.target.value)}
                  disabled={op.pending || review}
                />
              </Field>
            )}
            {review && (
              <div className="notice">
                <strong>Подтвердите изменение в {session.cluster_name}</strong>
                <p>
                  {titles[kind]}:{" "}
                  {kind === "apply"
                    ? `${str(obj(proof?.target).kind)} ${str(obj(proof?.target).name)}`
                    : `${target.kind} ${target.name}`}
                  {kind === "scale" ? ` → ${replicas} реплик` : ""}.
                </p>
                <p>Причина: {reason}</p>
              </div>
            )}
            <div className="kube-form-actions">
              <Button
                onClick={() => (review ? setReview(false) : onClose())}
                disabled={op.pending}
              >
                {review ? "Вернуться к параметрам" : "Отмена"}
              </Button>
              {review ? (
                <Button
                  variant={kind === "delete" ? "danger" : "primary"}
                  loading={op.pending}
                  disabled={!canReview}
                  onClick={() => void execute()}
                >
                  Подтвердить выполнение
                </Button>
              ) : (
                <Button
                  variant={kind === "delete" ? "danger" : "primary"}
                  disabled={
                    !canReview ||
                    op.pending ||
                    (kind === "scale" &&
                      (!Number.isInteger(replicas) || replicas < 0))
                  }
                  onClick={() => setReview(true)}
                >
                  Проверить и продолжить
                </Button>
              )}
            </div>
          </>
        )}
      </div>
    </Drawer>
  );
}
