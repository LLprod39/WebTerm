import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
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
import {
  kubernetesApi,
  type KubeAction,
  type KubeRecording,
} from "@/api/kubernetes";
import {
  KubeNav,
  KubeStatus,
  KubeFacts,
  KubeEvents,
  obj,
  rows,
  str,
  useKubeCapabilities,
  useKubeOperation,
} from "./common";
function ActionReport({
  action,
  onClose,
}: {
  action: KubeAction;
  onClose: () => void;
}) {
  const { user } = useSession();
  const cap = useKubeCapabilities();
  const q = useQuery({
    queryKey: ["kubernetes", "action-report", action.id],
    queryFn: () => kubernetesApi.actionReport(action.id),
  });
  const op = useKubeOperation();
  const [review, setReview] = useState(false);
  const [outcome, setOutcome] = useState("verified");
  const [summary, setSummary] = useState("");
  const [evidence, setEvidence] = useState("");
  const [followup, setFollowup] = useState("");
  const r = q.data?.report || {};
  const latest = { ...action, ...obj(r.action) };
  const breakGlass = obj(r.session).mode === "break_glass";
  const permitted =
    user?.is_staff &&
    cap.data?.modes.some(
      (m) =>
        m.id ===
          (breakGlass ? "kubernetes_break_glass" : "kubernetes_admin_write") &&
        m.active,
    );
  async function submit(e: FormEvent) {
    e.preventDefault();
    await op.run(async () => {
      await kubernetesApi.reviewAction(action.id, {
        outcome,
        summary,
        evidence_ref: evidence,
        follow_up_ref: followup,
      });
      setReview(false);
    }, "Разбор действия сохранён");
  }
  return (
    <Drawer
      open
      wide
      onOpenChange={(o) => !o && onClose()}
      title={`${action.verb} · ${action.resource_name}`}
      description={action.id}
    >
      <div className="stack">
        {op.feedback}
        {q.isPending ? (
          <LoadingState />
        ) : q.error ? (
          <ErrorState error={q.error} />
        ) : (
          <>
            <KubeStatus value={latest.status} />
            <KubeFacts
              data={latest}
              fields={[
                ["cluster_name", "Кластер"],
                ["namespace", "Область"],
                ["resource_kind", "Тип"],
                ["resource_name", "Ресурс"],
                ["created_by", "Оператор"],
                ["post_review_status", "Разбор"],
              ]}
            />
            <p className="muted">Выполнено {formatDate(action.created_at)}</p>
            <JsonDetails
              data={latest.request_payload_sanitized}
              label="Отправленные параметры"
            />
            <JsonDetails data={latest.diff_summary} label="Изменения" />
            <JsonDetails data={latest.response_summary} label="Результат" />
            <Panel title="События операции">
              <KubeEvents events={rows(r.timeline)} />
            </Panel>
            <Button
              onClick={() =>
                downloadText(
                  `kubernetes-action-${action.id}.json`,
                  JSON.stringify(r, null, 2),
                  "application/json",
                )
              }
            >
              Скачать отчёт
            </Button>
            {latest.post_review_required && permitted && !review && (
              <Button variant="primary" onClick={() => setReview(true)}>
                Зафиксировать итог проверки
              </Button>
            )}
            {review && (
              <form className="stack kube-target" onSubmit={submit}>
                <Field label="Итог" htmlFor="ka-outcome">
                  <select
                    id="ka-outcome"
                    value={outcome}
                    onChange={(e) => setOutcome(e.target.value)}
                  >
                    <option value="verified">Результат проверен</option>
                    <option value="accepted">Принято</option>
                    <option value="needs_followup">
                      Нужны дальнейшие действия
                    </option>
                    <option value="incident_created">Создан инцидент</option>
                  </select>
                </Field>
                <Field
                  label="Что проверено и полученный результат"
                  htmlFor="ka-summary"
                >
                  <textarea
                    id="ka-summary"
                    required
                    maxLength={2000}
                    value={summary}
                    onChange={(e) => setSummary(e.target.value)}
                  />
                </Field>
                <Field label="Доказательства" htmlFor="ka-evidence">
                  <input
                    id="ka-evidence"
                    value={evidence}
                    onChange={(e) => setEvidence(e.target.value)}
                  />
                </Field>
                <Field label="Связанная задача" htmlFor="ka-followup">
                  <input
                    id="ka-followup"
                    value={followup}
                    onChange={(e) => setFollowup(e.target.value)}
                  />
                </Field>
                <Button type="submit" variant="primary" loading={op.pending}>
                  Сохранить разбор
                </Button>
              </form>
            )}
          </>
        )}
      </div>
    </Drawer>
  );
}
function RecordingDetail({
  recording,
  onClose,
}: {
  recording: KubeRecording;
  onClose: () => void;
}) {
  const q = useQuery({
    queryKey: ["kubernetes", "recording", recording.id],
    queryFn: () => kubernetesApi.recording(recording.id),
  });
  const r = q.data?.recording;
  return (
    <Drawer
      open
      wide
      onOpenChange={(o) => !o && onClose()}
      title={`Запись · ${recording.operation}`}
      description={recording.id}
    >
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : (
        r && (
          <div className="stack">
            <KubeStatus value={r.status} />
            <KubeFacts
              data={r}
              fields={[
                ["cluster_name", "Кластер"],
                ["namespace", "Область"],
                ["resource_name", "Ресурс"],
                ["event_count", "Событий"],
                ["created_by", "Оператор"],
                ["transcript_delete_after", "Удаление транскрипта"],
                ["metadata_delete_after", "Удаление метаданных"],
              ]}
            />
            {!r.transcript_stored && (
              <p className="notice">
                Содержимое транскрипта не сохранено политикой записи. Доступны
                метаданные и итог.
              </p>
            )}
            <pre className="kube-log">
              {rows(r.events)
                .map(
                  (e) =>
                    `${str(e.sequence, "")} [${str(e.stream)}] ${str(e.data, "")}${e.truncated ? " … [сокращено]" : ""}`,
                )
                .join("\n") || "Сохранённых событий нет."}
            </pre>
            <JsonDetails data={r.summary} label="Итог записи" />
            <Button
              onClick={() =>
                downloadText(
                  `kubernetes-recording-${r.id}.json`,
                  JSON.stringify(r, null, 2),
                  "application/json",
                )
              }
            >
              Скачать доступную запись
            </Button>
          </div>
        )
      )}
    </Drawer>
  );
}
export function ActivityPage() {
  const { user } = useSession();
  const [params] = useSearchParams();
  const [tab, setTab] = useState("actions");
  const [all, setAll] = useState(false);
  const [reviewFilter, setReviewFilter] = useState("");
  const [selected, setSelected] = useState<KubeAction>();
  const [recording, setRecording] = useState<KubeRecording>();
  const session = params.get("session") || undefined;
  const actions = useQuery({
    queryKey: ["kubernetes", "actions", all, session, reviewFilter],
    queryFn: () =>
      kubernetesApi.actions({
        all,
        session_id: session,
        post_review_status: reviewFilter,
      }),
    enabled: tab === "actions",
  });
  const recordings = useQuery({
    queryKey: ["kubernetes", "recordings", all, session],
    queryFn: () => kubernetesApi.recordings({ all, session_id: session }),
    enabled: tab === "recordings",
  });
  const audit = useQuery({
    queryKey: ["kubernetes", "audit"],
    queryFn: kubernetesApi.audit,
    enabled: tab === "audit",
  });
  return (
    <>
      <PageHeader
        eyebrow="Kubernetes"
        title="Действия и записи"
        description="Результаты операций, доказательства выполнения и последующий разбор."
      />
      <KubeNav />
      <div className="stack">
        <Tabs
          value={tab}
          onChange={setTab}
          items={[
            { value: "actions", label: "Действия" },
            { value: "recordings", label: "Записи сессий" },
            { value: "audit", label: "Аудит" },
          ]}
        />
        <div className="kube-toolbar">
          {user?.is_staff && tab !== "audit" && (
            <label className="row">
              <input
                type="checkbox"
                checked={all}
                onChange={(e) => setAll(e.target.checked)}
              />{" "}
              Все пользователи
            </label>
          )}
          {tab === "actions" && (
            <Field label="Последующий разбор" htmlFor="ka-filter">
              <select
                id="ka-filter"
                value={reviewFilter}
                onChange={(e) => setReviewFilter(e.target.value)}
              >
                <option value="">Все действия</option>
                <option value="pending">Ожидает разбора</option>
                <option value="completed">Разбор завершён</option>
                <option value="not_ready">Выполняется</option>
              </select>
            </Field>
          )}
        </div>
        {session && <p className="notice">Фильтр по сессии: {session}</p>}
        {tab === "actions" &&
          (actions.isPending ? (
            <LoadingState />
          ) : actions.error ? (
            <ErrorState error={actions.error} retry={() => actions.refetch()} />
          ) : (
            <Panel
              title="История операций"
              description="Последние 100 действий в выбранной области."
            >
              <DataTable
                rows={actions.data?.actions || []}
                rowKey={(r) => r.id}
                searchValue={(r) =>
                  `${r.verb} ${r.resource_name} ${r.cluster_name} ${r.created_by}`
                }
                emptyTitle="Действий нет"
                columns={[
                  {
                    key: "name",
                    label: "Операция",
                    render: (r) => (
                      <Button variant="ghost" onClick={() => setSelected(r)}>
                        {r.verb} · {r.resource_name || r.resource_kind}
                      </Button>
                    ),
                  },
                  {
                    key: "target",
                    label: "Цель",
                    render: (r) => (
                      <>
                        {r.cluster_name}
                        <p className="muted">{r.namespace}</p>
                      </>
                    ),
                  },
                  {
                    key: "status",
                    label: "Результат",
                    render: (r) => <KubeStatus value={r.status} />,
                  },
                  {
                    key: "review",
                    label: "Разбор",
                    render: (r) => <KubeStatus value={r.post_review_status} />,
                  },
                  {
                    key: "time",
                    label: "Время",
                    render: (r) => formatDate(r.created_at),
                  },
                  {
                    key: "user",
                    label: "Оператор",
                    render: (r) => r.created_by,
                  },
                ]}
              />
            </Panel>
          ))}
        {tab === "recordings" &&
          (recordings.isPending ? (
            <LoadingState />
          ) : recordings.error ? (
            <ErrorState
              error={recordings.error}
              retry={() => recordings.refetch()}
            />
          ) : (
            <Panel title="Записи сессий">
              <DataTable
                rows={recordings.data?.recordings || []}
                rowKey={(r) => r.id}
                searchValue={(r) =>
                  `${r.operation} ${r.cluster_name} ${r.resource_name}`
                }
                emptyTitle="Записей нет"
                emptyDescription="Здесь появятся записи действий, для которых backend включает аудит потока."
                columns={[
                  {
                    key: "name",
                    label: "Операция",
                    render: (r) => (
                      <Button variant="ghost" onClick={() => setRecording(r)}>
                        {r.operation} · {r.resource_name}
                      </Button>
                    ),
                  },
                  {
                    key: "cluster",
                    label: "Кластер",
                    render: (r) => r.cluster_name,
                  },
                  {
                    key: "status",
                    label: "Статус",
                    render: (r) => <KubeStatus value={r.status} />,
                  },
                  {
                    key: "count",
                    label: "Событий",
                    render: (r) => r.event_count,
                  },
                  {
                    key: "time",
                    label: "Время",
                    render: (r) => formatDate(r.created_at),
                  },
                ]}
              />
            </Panel>
          ))}
        {tab === "audit" &&
          (audit.isPending ? (
            <LoadingState />
          ) : audit.error ? (
            <ErrorState error={audit.error} retry={() => audit.refetch()} />
          ) : (
            <Panel title="Аудит Kubernetes">
              <KubeEvents events={rows(audit.data?.events)} />
            </Panel>
          ))}
      </div>
      {selected && (
        <ActionReport
          action={selected}
          onClose={() => setSelected(undefined)}
        />
      )}{" "}
      {recording && (
        <RecordingDetail
          recording={recording}
          onClose={() => setRecording(undefined)}
        />
      )}
    </>
  );
}
