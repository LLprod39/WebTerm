import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ReactFlow, Background, Controls } from "@xyflow/react";
import {
  Check,
  Clock,
  Copy,
  Eye,
  Plus,
  Send,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { api } from "@/api/client";
import { useTheme } from "@/app/theme";
import {
  automationApi,
  studioBase,
  type DraftSession,
  type Pipeline,
  type Trigger,
  type Values,
} from "@/api/automation";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
  EmptyState,
  ErrorState,
  Feedback,
  Field,
  PageHeader,
  Panel,
  Skeleton,
  StatusBadge,
} from "@/components/ui";
import { formatDate } from "@/lib/utils";
import { KeyValues, ValidationResult } from "./shared";
import { toCanvas } from "./graph";
import { pipelineNodeTypes } from "./editor/nodes/StepNode";
import "./editor/editor.css";

export function DraftLibrary() {
  const query = useQuery({
    queryKey: ["automation", "drafts"],
    queryFn: ({ signal }) => automationApi.drafts(signal),
  });
  const [open, setOpen] = useState(false);
  const [goal, setGoal] = useState("");
  const [title, setTitle] = useState("");
  const navigate = useNavigate();
  const create = useMutation({
    mutationFn: () =>
      automationApi.createSessionDraft({
        user_message: goal,
        pipeline_name: title,
        intent: "create",
        draft_mode: true,
        nodes: [],
        edges: [],
      }),
    onSuccess: (d) => navigate(`/automation/drafts/${d.id}`),
  });
  return (
    <>
      <PageHeader
        eyebrow="Автоматизация"
        title="Черновики процессов"
        description="Опишите задачу, проверьте предложенный граф и примените изменения после проверки."
        actions={
          <Button variant="primary" onClick={() => setOpen(true)}>
            <Plus size={15} />
            Новый черновик
          </Button>
        }
      />
      <Panel>
        {query.isPending ? (
          <Skeleton />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : (
          <DataTable
            rows={query.data ?? []}
            rowKey={(r) => r.id}
            searchValue={(r) => `${r.title} ${r.user_goal}`}
            emptyTitle="Черновиков пока нет"
            emptyDescription="Начните с цели. Ассистент предложит шаги и уточнит недостающие условия."
            emptyAction={
              <Button variant="primary" onClick={() => setOpen(true)}>
                Описать задачу
              </Button>
            }
            columns={[
              {
                key: "title",
                label: "Черновик",
                render: (r) => (
                  <div className="auto-row-title">
                    <Link to={`/automation/drafts/${r.id}`}>
                      {r.title || `Черновик #${r.id}`}
                    </Link>
                    <small>{r.user_goal}</small>
                  </div>
                ),
              },
              {
                key: "status",
                label: "Состояние",
                render: (r) => <StatusBadge status={r.status} />,
              },
              {
                key: "updated",
                label: "Изменён",
                render: (r) => formatDate(r.updated_at),
              },
              {
                key: "pipeline",
                label: "Процесс",
                render: (r) =>
                  r.applied_pipeline_id ? (
                    <Link to={`/automation/pipelines/${r.applied_pipeline_id}`}>
                      Открыть процесс →
                    </Link>
                  ) : r.source_pipeline_id ? (
                    <Link to={`/automation/pipelines/${r.source_pipeline_id}`}>
                      Исходный процесс
                    </Link>
                  ) : (
                    "Новый процесс"
                  ),
              },
            ]}
          />
        )}
      </Panel>
      <Drawer
        open={open}
        onOpenChange={setOpen}
        title="Новый черновик процесса"
      >
        <form
          className="auto-form"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <Field label="Название" htmlFor="draft-title">
            <input
              id="draft-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </Field>
          <Field
            label="Что должен делать процесс?"
            htmlFor="draft-goal"
            description="Укажите цели, условия запуска, допустимые изменения и ожидаемый результат."
          >
            <textarea
              id="draft-goal"
              rows={7}
              required
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
            />
          </Field>
          <Feedback error={create.error} />
          {create.isPending && (
            <p role="status" className="muted text-sm">
              Ассистент готовит граф. Это может занять некоторое время.
            </p>
          )}
          <Button type="submit" variant="primary" loading={create.isPending}>
            <Send size={14} />
            Подготовить черновик
          </Button>
        </form>
      </Drawer>
    </>
  );
}
function readable(value: unknown): string {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") {
    const item = value as Record<string, unknown>;
    return String(
      item.question ??
        item.message ??
        item.description ??
        item.label ??
        item.title ??
        item.name ??
        item.code ??
        "Требуется уточнение",
    );
  }
  return String(value ?? "");
}
export function DraftWorkspace() {
  const { theme } = useTheme();
  const { id } = useParams();
  const draftId = Number(id);
  const query = useQuery({
    queryKey: ["automation", "draft", draftId],
    queryFn: ({ signal }) => automationApi.sessionDraft(draftId, signal),
  });
  const manifests = useQuery({
    queryKey: ["automation", "node-manifests"],
    queryFn: ({ signal }) => automationApi.manifests(signal),
  });
  const templates = useQuery({
    queryKey: ["automation", "pipeline-templates"],
    queryFn: ({ signal }) => automationApi.templates(signal),
  });
  const [message, setMessage] = useState("");
  const [template, setTemplate] = useState("");
  const [discard, setDiscard] = useState(false);
  const client = useQueryClient();
  const navigate = useNavigate();
  const update = (draft: DraftSession) => {
    client.setQueryData(["automation", "draft", draftId], draft);
    void client.invalidateQueries({ queryKey: ["automation", "drafts"] });
  };
  const revise = useMutation({
    mutationFn: () =>
      api.post<DraftSession>(
        `${studioBase}assistant/drafts/${draftId}/revise/`,
        { user_message: message },
      ),
    onSuccess: (d) => {
      update(d);
      setMessage("");
    },
  });
  const validate = useMutation({
    mutationFn: () =>
      api.post<{ draft: DraftSession }>(
        `${studioBase}assistant/drafts/${draftId}/validate/`,
      ),
    onSuccess: (r) => update(r.draft),
  });
  const useTemplate = useMutation({
    mutationFn: () =>
      api.post<DraftSession>(
        `${studioBase}assistant/drafts/${draftId}/use-template/`,
        { template_slug: template },
      ),
    onSuccess: update,
  });
  const apply = useMutation({
    mutationFn: () =>
      api.post<{ draft: DraftSession; pipeline: Pipeline }>(
        `${studioBase}assistant/drafts/${draftId}/apply/`,
        {},
      ),
    onSuccess: (r) => {
      update(r.draft);
      void client.invalidateQueries({ queryKey: ["automation", "pipelines"] });
      navigate(`/automation/pipelines/${r.pipeline.id}`);
    },
  });
  const remove = useMutation({
    mutationFn: () =>
      api.delete<DraftSession>(`${studioBase}assistant/drafts/${draftId}/`),
    onSuccess: (d) => {
      update(d);
      setDiscard(false);
    },
  });
  if (query.isPending) return <Skeleton />;
  if (query.error)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  const draft = query.data!;
  const response = draft.latest_revision?.response;
  const closed = ["applied", "discarded"].includes(draft.status);
  const graph = toCanvas(
    draft.latest_revision?.preview_nodes ?? [],
    manifests.data?.nodes ?? [],
  );
  return (
    <>
      <PageHeader
        eyebrow="Автоматизация / Черновики"
        title={draft.title || `Черновик #${draft.id}`}
        description={<StatusBadge status={draft.status} />}
        actions={
          <>
            <Link className="btn btn-ghost" to="/automation/drafts">
              К черновикам
            </Link>
            {draft.applied_pipeline_id ? (
              <Link
                className="btn btn-primary"
                to={`/automation/pipelines/${draft.applied_pipeline_id}`}
              >
                Открыть процесс
              </Link>
            ) : (
              !closed && (
                <>
                  <Button
                    loading={validate.isPending}
                    onClick={() => validate.mutate()}
                  >
                    <ShieldCheck size={14} />
                    Проверить
                  </Button>
                  <Button
                    variant="primary"
                    loading={apply.isPending}
                    disabled={
                      draft.status !== "ready" ||
                      response?.validation?.ok === false ||
                      response?.risk?.level === "dangerous"
                    }
                    onClick={() => apply.mutate()}
                  >
                    <Check size={14} />
                    Применить черновик
                  </Button>
                </>
              )
            )}
          </>
        }
      />
      <Feedback
        error={
          revise.error ||
          validate.error ||
          apply.error ||
          remove.error ||
          useTemplate.error
        }
      />
      <div className="auto-detail-grid">
        <div className="auto-stack">
          <Panel title="Предварительный граф">
            <div className="auto-canvas" style={{ height: 430 }}>
              {graph.length ? (
                <ReactFlow
                  colorMode={theme}
                  nodes={graph}
                  edges={(draft.latest_revision?.preview_edges ?? []).map(
                    (edge) => ({
                      ...edge,
                      type: "smoothstep",
                    }),
                  )}
                  nodeTypes={pipelineNodeTypes}
                  fitView
                  nodesDraggable={false}
                  nodesConnectable={false}
                  elementsSelectable={true}
                  deleteKeyCode={null}
                >
                  <Background />
                  <Controls showInteractive={false} />
                </ReactFlow>
              ) : (
                <EmptyState
                  title="Граф ещё не готов"
                  description="Ответьте на уточняющие вопросы ассистента."
                />
              )}
            </div>
          </Panel>
          <Panel title="Предложение ассистента">
            <p className="auto-draft-message">
              {response?.reply || "Ожидается предложение."}
            </p>
            <div className="auto-pad">
              {response?.patch_summary && <p>{response.patch_summary}</p>}
              {response?.validation && (
                <ValidationResult value={response.validation} />
              )}
              <div>
                {(response?.warnings ?? []).map((v, i) => (
                  <p className="notice notice-warning" key={i}>
                    {readable(v)}
                  </p>
                ))}
              </div>
            </div>
          </Panel>
          {!closed && (
            <Panel title="Уточнить задачу">
              <form
                className="auto-pad auto-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  revise.mutate();
                }}
              >
                {(response?.questions ?? []).map((question, i) => (
                  <p className="auto-question" key={i}>
                    {readable(question)}
                  </p>
                ))}
                <Field
                  label="Ответ или изменение требований"
                  htmlFor="draft-answer"
                >
                  <textarea
                    id="draft-answer"
                    required
                    rows={4}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                  />
                </Field>
                <div>
                  <Button
                    type="submit"
                    variant="primary"
                    loading={revise.isPending}
                  >
                    <Send size={14} />
                    Обновить предложение
                  </Button>
                </div>
              </form>
            </Panel>
          )}
        </div>
        <Panel title="Контекст черновика">
          <div className="auto-summary">
            <p>{draft.user_goal}</p>
            <dl>
              <div>
                <dt>Последнее изменение</dt>
                <dd>{formatDate(draft.updated_at)}</dd>
              </div>
              <div>
                <dt>Оценка риска</dt>
                <dd>
                  <StatusBadge
                    status={
                      response?.risk?.level === "dangerous" ? "danger" : "info"
                    }
                  >
                    {response?.risk?.level || "Не оценён"}
                  </StatusBadge>
                </dd>
              </div>
            </dl>
            {(response?.requirements ?? []).map((item, i) => (
              <p className="auto-muted" key={i}>
                {readable(item)}
              </p>
            ))}
            {!closed && (
              <>
                <Field label="Использовать шаблон" htmlFor="draft-template">
                  <select
                    id="draft-template"
                    value={template}
                    onChange={(e) => setTemplate(e.target.value)}
                  >
                    <option value="">Выберите шаблон</option>
                    {templates.data?.map((t) => (
                      <option key={t.slug} value={t.slug}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Button
                  disabled={!template}
                  loading={useTemplate.isPending}
                  onClick={() => useTemplate.mutate()}
                >
                  Подготовить из шаблона
                </Button>
                <Button variant="ghost" onClick={() => setDiscard(true)}>
                  <Trash2 size={14} />
                  Отбросить черновик
                </Button>
              </>
            )}
          </div>
        </Panel>
      </div>
      <ConfirmDialog
        open={discard}
        onOpenChange={setDiscard}
        title="Отбросить черновик?"
        description="Черновик станет недоступен для дальнейшего изменения. Рабочий процесс останется без изменений."
        confirmLabel="Отбросить"
        pending={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </>
  );
}
export function Schedules() {
  const query = useQuery({
    queryKey: ["automation", "triggers"],
    queryFn: ({ signal }) => automationApi.triggers(signal),
  });
  const pipelines = useQuery({
    queryKey: ["automation", "pipelines"],
    queryFn: ({ signal }) => automationApi.pipelines(signal),
  });
  const [type, setType] = useState("schedule");
  const [editing, setEditing] = useState<Trigger | null | undefined>(undefined);
  const [remove, setRemove] = useState<Trigger | null>(null);
  const toggle = useMutation({
    mutationFn: (trigger: Trigger) =>
      api.put<Trigger>(`${studioBase}triggers/${trigger.id}/`, {
        is_active: !trigger.is_active,
      }),
    onSuccess: () => void query.refetch(),
  });
  const deletion = useMutation({
    mutationFn: () => api.delete(`${studioBase}triggers/${remove!.id}/`),
    onSuccess: () => {
      setRemove(null);
      void query.refetch();
    },
  });
  return (
    <>
      <PageHeader
        eyebrow="Автоматизация"
        title="Расписания и триггеры"
        description="Управляйте автоматическим запуском процессов и внешними событиями."
        actions={
          <Button variant="primary" onClick={() => setEditing(null)}>
            <Plus size={15} />
            Настроить триггер
          </Button>
        }
      />
      <Feedback error={toggle.error || deletion.error} />
      <Panel>
        {query.isPending ? (
          <Skeleton />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : (
          <DataTable
            rows={(query.data ?? []).filter(
              (t) => type === "all" || t.trigger_type === type,
            )}
            rowKey={(r) => r.id}
            emptyTitle="Триггеры этого типа не настроены"
            emptyDescription="Добавьте соответствующий триггер в граф процесса, затем настройте запуск."
            toolbar={
              <select
                aria-label="Тип триггера"
                value={type}
                onChange={(e) => setType(e.target.value)}
              >
                <option value="schedule">Расписания</option>
                <option value="webhook">Webhooks</option>
                <option value="monitoring">Мониторинг</option>
                <option value="manual">Ручные</option>
                <option value="all">Все</option>
              </select>
            }
            columns={[
              {
                key: "name",
                label: "Триггер / Процесс",
                render: (r) => (
                  <div className="auto-row-title">
                    <strong>{r.name || r.node_id}</strong>
                    <Link to={`/automation/pipelines/${r.pipeline_id}`}>
                      {pipelines.data?.find((p) => p.id === r.pipeline_id)
                        ?.name || `Процесс #${r.pipeline_id}`}
                    </Link>
                  </div>
                ),
              },
              {
                key: "schedule",
                label: "Условие запуска",
                render: (r) =>
                  r.trigger_type === "schedule" ? (
                    <span className="mono">
                      {r.cron_expression || "Не задано"}
                    </span>
                  ) : (
                    r.trigger_type
                  ),
              },
              {
                key: "status",
                label: "Состояние",
                render: (r) => (
                  <StatusBadge status={r.is_active ? "active" : "disabled"} />
                ),
              },
              {
                key: "last",
                label: "Последний запуск",
                render: (r) => formatDate(r.last_triggered_at),
              },
              {
                key: "actions",
                label: "Действия",
                render: (r) => (
                  <div className="auto-toolbar">
                    <Button size="sm" onClick={() => setEditing(r)}>
                      Настроить
                    </Button>
                    <Button
                      size="sm"
                      disabled={toggle.isPending}
                      onClick={() => toggle.mutate(r)}
                    >
                      {r.is_active ? "Выключить" : "Включить"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Удалить триггер"
                      onClick={() => setRemove(r)}
                    >
                      <Trash2 size={14} />
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        )}
      </Panel>
      <Drawer
        open={editing !== undefined}
        onOpenChange={(v) => !v && setEditing(undefined)}
        title={editing ? "Настроить триггер" : "Новый триггер"}
      >
        {editing !== undefined && (
          <TriggerForm
            key={editing?.id ?? "new"}
            trigger={editing}
            pipelines={pipelines.data ?? []}
            done={() => {
              setEditing(undefined);
              void query.refetch();
            }}
          />
        )}
      </Drawer>
      <ConfirmDialog
        open={!!remove}
        onOpenChange={(v) => !v && setRemove(null)}
        title="Удалить триггер?"
        description="Автоматические запуски по этому триггеру прекратятся. При сохранении графа соответствующий узел может создать его снова; удалите узел из графа для окончательного удаления."
        onConfirm={() => deletion.mutate()}
        pending={deletion.isPending}
        confirmLabel="Удалить"
      />
    </>
  );
}
function TriggerForm({
  trigger,
  pipelines,
  done,
}: {
  trigger: Trigger | null;
  pipelines: Pipeline[];
  done: () => void;
}) {
  const [pipelineId, setPipelineId] = useState(trigger?.pipeline_id ?? 0);
  const [node, setNode] = useState(trigger?.node_id ?? "");
  const [type, setType] = useState(trigger?.trigger_type ?? "schedule");
  const [name, setName] = useState(trigger?.name ?? "");
  const [cron, setCron] = useState(trigger?.cron_expression ?? "");
  const [active, setActive] = useState(trigger?.is_active ?? false);
  const [mapping, setMapping] = useState<Values>(
    trigger?.webhook_payload_map ?? {},
  );
  const [filters, setFilters] = useState<Values>(
    trigger?.monitoring_filters ?? {},
  );
  const [secret, setSecret] = useState("");
  const [reveal, setReveal] = useState(false);
  const [copied, setCopied] = useState(false);
  const pipeline = useQuery({
    queryKey: ["automation", "pipeline", pipelineId],
    queryFn: ({ signal }) => automationApi.pipeline(pipelineId, signal),
    enabled: !!pipelineId,
  });
  const save = useMutation({
    mutationFn: () => {
      const body = {
        pipeline_id: pipelineId,
        node_id: node,
        name,
        trigger_type: type,
        is_active: active,
        cron_expression: cron,
        webhook_payload_map: mapping,
        monitoring_filters: filters,
        ...(secret ? { signing_secret: secret } : {}),
      };
      return trigger
        ? api.put(`${studioBase}triggers/${trigger.id}/`, body)
        : api.post(`${studioBase}triggers/`, body);
    },
    onSuccess: () => {
      setSecret("");
      done();
    },
  });
  const eligible =
    pipeline.data?.nodes?.filter((n) => n.type === `trigger/${type}`) ?? [];
  return (
    <form
      className="auto-form"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <Field label="Процесс" htmlFor="trigger-pipeline">
        <select
          id="trigger-pipeline"
          required
          disabled={!!trigger}
          value={pipelineId}
          onChange={(e) => {
            setPipelineId(Number(e.target.value));
            setNode("");
          }}
        >
          <option value={0}>Выберите процесс</option>
          {pipelines.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Тип триггера" htmlFor="trigger-type">
        <select
          id="trigger-type"
          value={type}
          onChange={(e) => {
            setType(e.target.value);
            setNode("");
          }}
        >
          {["schedule", "webhook", "monitoring", "manual"].map((t) => (
            <option value={t} key={t}>
              {t}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Узел в графе" htmlFor="trigger-node">
        <select
          id="trigger-node"
          required
          value={node}
          onChange={(e) => setNode(e.target.value)}
        >
          <option value="">Выберите узел</option>
          {eligible.map((n) => (
            <option value={n.id} key={n.id}>
              {String(n.data.label || n.id)}
            </option>
          ))}
        </select>
      </Field>
      {pipelineId !== 0 && !eligible.length && !pipeline.isPending && (
        <p className="notice notice-info">
          Добавьте узел trigger/{type} в{" "}
          <Link to={`/automation/pipelines/${pipelineId}`}>
            редакторе процесса
          </Link>
          .
        </p>
      )}
      <Field label="Название" htmlFor="trigger-name">
        <input
          id="trigger-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      {type === "schedule" && (
        <Field
          label="Расписание cron"
          htmlFor="trigger-cron"
          description="Пять полей: минута, час, день месяца, месяц, день недели. Часовой пояс — серверный."
        >
          <input
            id="trigger-cron"
            className="mono"
            required
            placeholder="0 9 * * 1-5"
            value={cron}
            onChange={(e) => setCron(e.target.value)}
          />
        </Field>
      )}
      {type === "webhook" && (
        <>
          <KeyValues
            label="Поля webhook → контекст"
            value={mapping}
            onChange={setMapping}
          />
          <Field
            label="Новый секрет подписи"
            htmlFor="trigger-secret"
            description={
              trigger?.has_signing_secret
                ? "Секрет уже настроен. Оставьте поле пустым, чтобы сохранить его."
                : undefined
            }
          >
            <input
              id="trigger-secret"
              type="password"
              autoComplete="off"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
            />
          </Field>
          {trigger && (
            <div className="auto-form">
              <code>{trigger.webhook_header_url}</code>
              <Field label="X-WebTerm-Trigger-Token" htmlFor="trigger-token">
                <input
                  id="trigger-token"
                  type={reveal ? "text" : "password"}
                  readOnly
                  value={trigger.webhook_token}
                />
              </Field>
              <div className="auto-toolbar">
                <Button size="sm" onClick={() => setReveal(!reveal)}>
                  <Eye size={13} />
                  {reveal ? "Скрыть" : "Показать"}
                </Button>
                <Button
                  size="sm"
                  onClick={() => {
                    void navigator.clipboard
                      .writeText(trigger.webhook_token)
                      .then(() => setCopied(true));
                  }}
                >
                  <Copy size={13} />
                  {copied ? "Скопировано" : "Копировать"}
                </Button>
              </div>
            </div>
          )}
        </>
      )}
      {type === "monitoring" && (
        <KeyValues
          label="Фильтры оповещений"
          value={filters}
          onChange={setFilters}
        />
      )}
      <label className="auto-check-row">
        <input
          type="checkbox"
          checked={active}
          onChange={(e) => setActive(e.target.checked)}
        />
        Триггер включён
      </label>
      <Feedback error={save.error || pipeline.error} />
      <Button
        type="submit"
        variant="primary"
        loading={save.isPending}
        disabled={!pipelineId || !node}
      >
        <Clock size={14} />
        Сохранить триггер
      </Button>
    </form>
  );
}
