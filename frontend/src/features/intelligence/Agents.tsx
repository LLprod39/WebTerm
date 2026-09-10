import { useState } from "react";
import { useLive } from "./useLive";
import {
  AgentRuntimeFields,
  type AgentRuntimeFieldsValue,
} from "./AgentMaterials";
import {
  AgentRuntimeDrawer,
  PlanTaskEditor,
  ScheduleFields,
  scheduleLabels,
} from "./Operations";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowUpRight,
  Bot,
  Check,
  Download,
  Play,
  Plus,
  RefreshCw,
  Square,
  Trash2,
} from "lucide-react";
import {
  intelligenceApi as service,
  type Agent,
  type PlanTask,
  type Details,
} from "@/api/intelligence";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
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
import { usePermission } from "@/app/session";
import { formatDate } from "@/lib/utils";
import {
  activeRun,
  DetailCards,
  DetailRows,
  IntelStatus,
  Markdown,
  list,
  text,
  useOperation,
} from "./common";

function AgentEditor({
  agent,
  onClose,
}: {
  agent: Agent | null;
  onClose: () => void;
}) {
  const [runtimeFields, setRuntimeFields] = useState<AgentRuntimeFieldsValue>({
    sudo_policy: agent?.sudo_policy || "disabled",
    allow_multi_server: agent?.allow_multi_server || false,
    max_connections: agent?.max_connections || 1,
    input_artifacts: list(agent?.input_artifacts),
    report_delivery: agent?.report_delivery || {
      telegram: { enabled: false, format: "brief", include_link: true },
    },
  });
  const op = useOperation();
  const navigate = useNavigate();
  const canServers = usePermission("servers");
  const canAutomate = usePermission("automation");
  const servers = useQuery({
    queryKey: ["intelligence", "servers"],
    queryFn: service.servers,
    enabled: canServers,
  });
  const templates = useQuery({
    queryKey: ["intelligence", "templates"],
    queryFn: service.templates,
  });
  const [name, setName] = useState(agent?.name || "");
  const [mode, setMode] = useState(agent?.mode || "full");
  const [goal, setGoal] = useState(agent?.goal || agent?.ai_prompt || "");
  const [commands, setCommands] = useState(
    (agent?.commands || [])
      .map((c) => (typeof c === "string" ? c : JSON.stringify(c)))
      .join("\n"),
  );
  const [serverIds, setServerIds] = useState(agent?.server_ids || []);
  const [template, setTemplate] = useState(agent?.agent_type || "custom");
  const [iterations, setIterations] = useState(agent?.max_iterations || 12);
  const [timeout, setTimeout] = useState(agent?.session_timeout_seconds || 300);
  const [schedule, setSchedule] = useState<Details>(
    agent?.schedule_config || {
      mode: "manual",
      timezone: "UTC",
      time: "09:00",
      weekdays: [0, 1, 2, 3, 4],
    },
  );
  const [enabled, setEnabled] = useState(agent?.is_enabled ?? true);
  const [system, setSystem] = useState(agent?.system_prompt || "");
  const [tools, setTools] = useState(
    JSON.stringify(agent?.tools_config || {}, null, 2),
  );
  const [skills, setSkills] = useState((agent?.skill_slugs || []).join(", "));
  const [stop, setStop] = useState((agent?.stop_conditions || []).join("\n"));
  const save = () =>
    void op.run(
      async () => {
        const parsed = JSON.parse(tools) as unknown;
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
          throw new Error("Настройки инструментов должны быть объектом JSON.");
        if (
          !Number.isInteger(runtimeFields.max_connections) ||
          runtimeFields.max_connections < 1 ||
          runtimeFields.max_connections > 10
        )
          throw new Error("Число подключений должно быть от 1 до 10.");
        const body: Details = {
          ...runtimeFields,
          name: name.trim(),
          mode,
          agent_type: template,
          goal: goal.trim(),
          ai_prompt: goal.trim(),
          commands: commands
            .split("\n")
            .map((c) => c.trim())
            .filter(Boolean),
          server_ids: serverIds,
          max_iterations: iterations,
          session_timeout_seconds: timeout,
          system_prompt: system,
          tools_config: parsed,
          skill_slugs: skills
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          stop_conditions: stop.split("\n").filter(Boolean),
          is_enabled: enabled,
        };
        if (canAutomate) {
          if (schedule.mode === "once" && !schedule.run_at)
            throw new Error("Укажите дату однократного запуска.");
          if (
            schedule.mode === "weekly" &&
            (!Array.isArray(schedule.weekdays) || !schedule.weekdays.length)
          )
            throw new Error("Выберите дни недели.");
          if (schedule.mode !== "manual" && schedule.timezone) {
            try {
              new Intl.DateTimeFormat("ru", {
                timeZone: String(schedule.timezone),
              });
            } catch {
              throw new Error("Проверьте название часового пояса.");
            }
          }
          body.schedule_config = schedule;
        }
        if (agent) {
          await service.updateAgent(agent.id, body);
          return agent.id;
        }
        return (await service.createAgent(body)).id;
      },
      "Агент сохранён",
      (id) => {
        onClose();
        navigate(`/intelligence/agents/${id}`);
      },
    );
  return (
    <Drawer
      open
      onOpenChange={(v) => {
        if (!v && !op.pending) onClose();
      }}
      title={agent ? "Настройка агента" : "Новый агент"}
      description="Задайте цель, область доступа и условия выполнения."
      wide
      footer={
        <>
          <Button disabled={op.pending} onClick={onClose}>
            Отмена
          </Button>
          <Button
            variant="primary"
            loading={op.pending}
            disabled={
              !name.trim() ||
              (mode === "mini" ? !commands.trim() : !goal.trim())
            }
            onClick={save}
          >
            Сохранить агента
          </Button>
        </>
      }
    >
      <div className="intel-form">
        {op.feedback}
        <Field label="Название" htmlFor="agent-name">
          <input
            id="agent-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
          />
        </Field>
        {!agent && (
          <div className="intel-grid-2">
            <Field label="Способ работы" htmlFor="agent-mode">
              <select
                id="agent-mode"
                value={mode}
                onChange={(e) => setMode(e.target.value)}
              >
                <option value="full">Автономный агент</option>
                <option value="mini">Команды и анализ</option>
                <option value="multi">Командная работа</option>
              </select>
            </Field>
            <Field label="Шаблон" htmlFor="agent-template">
              <select
                id="agent-template"
                value={template}
                onChange={(e) => {
                  const value = e.target.value;
                  setTemplate(value);
                  const chosen = templates.data?.templates.find(
                    (t) => text(t.id || t.type || t.key) === value,
                  );
                  if (chosen) {
                    if (!name) setName(text(chosen.name, ""));
                    setGoal(text(chosen.goal || chosen.ai_prompt, ""));
                    setCommands(
                      Array.isArray(chosen.commands)
                        ? chosen.commands.map(String).join("\n")
                        : "",
                    );
                  }
                }}
              >
                <option value="custom">Свой сценарий</option>
                {templates.data?.templates.map((t, i) => (
                  <option
                    key={text(t.id || t.type || t.key, String(i))}
                    value={text(t.id || t.type || t.key)}
                  >
                    {text(t.name)}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        )}
        <Field
          label="Ожидаемый результат"
          htmlFor="agent-goal"
          description="Опишите задачу и признаки успешного результата."
        >
          <textarea
            id="agent-goal"
            rows={5}
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
          />
        </Field>
        {mode === "mini" && (
          <Field label="Команды — по одной в строке" htmlFor="agent-commands">
            <textarea
              id="agent-commands"
              rows={5}
              className="intel-mono"
              value={commands}
              onChange={(e) => setCommands(e.target.value)}
            />
          </Field>
        )}
        <Field
          label="Серверы"
          description="Выберите только серверы, необходимые для задачи. Запуск дополнительно проверит право выполнения команд."
        >
          <div className="intel-checkbox-list">
            {servers.isPending && canServers ? (
              <LoadingState />
            ) : servers.error ? (
              <ErrorState error={servers.error} />
            ) : servers.data?.servers.length ? (
              servers.data.servers.map((s) => (
                <label key={s.id}>
                  <input
                    type="checkbox"
                    checked={serverIds.includes(s.id)}
                    onChange={(e) =>
                      setServerIds(
                        e.target.checked
                          ? [...serverIds, s.id]
                          : serverIds.filter((id) => id !== s.id),
                      )
                    }
                  />
                  <span>
                    {s.name}
                    <small>{s.host}</small>
                  </span>
                </label>
              ))
            ) : (
              <p className="muted">
                Доступных серверов нет. Можно сохранить задачу, не требующую
                доступа к инфраструктуре.
              </p>
            )}
          </div>
        </Field>
        <div className="intel-grid-2">
          <Field label="Лимит шагов" htmlFor="agent-budget">
            <input
              id="agent-budget"
              type="number"
              min={1}
              max={100}
              value={iterations}
              onChange={(e) => setIterations(Number(e.target.value))}
            />
          </Field>
          <Field label="Лимит времени, секунд" htmlFor="agent-timeout">
            <input
              id="agent-timeout"
              type="number"
              min={30}
              max={3600}
              value={timeout}
              onChange={(e) => setTimeout(Number(e.target.value))}
            />
          </Field>
        </div>
        {canAutomate && (
          <ScheduleFields value={schedule} onChange={setSchedule} />
        )}
        {agent && (
          <label className="intel-check">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            Агент включён
          </label>
        )}
        <details className="intel-advanced">
          <summary>Дополнительные условия</summary>
          <div className="intel-form">
            <AgentRuntimeFields
              value={runtimeFields}
              onChange={setRuntimeFields}
            />
            <Field label="Инструкции агента" htmlFor="agent-system">
              <textarea
                id="agent-system"
                rows={4}
                value={system}
                onChange={(e) => setSystem(e.target.value)}
              />
            </Field>
            <Field
              label="Условия остановки — по одному в строке"
              htmlFor="agent-stop"
            >
              <textarea
                id="agent-stop"
                rows={3}
                value={stop}
                onChange={(e) => setStop(e.target.value)}
              />
            </Field>
            <Field label="Навыки, через запятую" htmlFor="agent-skills">
              <input
                id="agent-skills"
                value={skills}
                onChange={(e) => setSkills(e.target.value)}
              />
            </Field>
            <Field
              label="Разрешённые инструменты (JSON)"
              htmlFor="agent-tools"
              description="Доступность инструментов дополнительно ограничена вашей ролью."
            >
              <textarea
                id="agent-tools"
                className="intel-mono"
                rows={7}
                value={tools}
                onChange={(e) => setTools(e.target.value)}
              />
            </Field>
          </div>
        </details>
      </div>
    </Drawer>
  );
}

export function AgentsPage() {
  const [runtime, setRuntime] = useState(false);
  const [create, setCreate] = useState(false);
  const q = useQuery({
    queryKey: ["intelligence", "agents"],
    queryFn: service.agents,
    refetchInterval: 15000,
  });
  const rows = q.data?.agents || [];
  return (
    <>
      <PageHeader
        eyebrow="Интеллект"
        title="Агенты"
        description="Повторяемые задачи, автономные исследования и управляемое выполнение."
        actions={
          <>
            <Button onClick={() => setRuntime(true)}>
              Расписания и процессы
            </Button>
            <Button onClick={() => void q.refetch()}>
              <RefreshCw size={15} />
              Обновить
            </Button>
            <Button variant="primary" onClick={() => setCreate(true)}>
              <Plus size={16} />
              Создать агента
            </Button>
          </>
        }
      />
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} retry={() => void q.refetch()} />
      ) : (
        <>
          <div className="intel-metrics">
            <Metric
              label="Агентов"
              value={rows.length}
              icon={<Bot size={16} />}
            />
            <Metric
              label="В работе"
              value={rows.filter((a) => a.active_run_id).length}
            />
            <Metric
              label="По расписанию"
              value={rows.filter((a) => a.schedule_minutes > 0).length}
            />
          </div>
          <Panel>
            <DataTable
              rows={rows}
              rowKey={(a) => a.id}
              searchValue={(a) =>
                `${a.name} ${a.goal} ${a.server_names.join(" ")}`
              }
              searchPlaceholder="Найти агента или сервер"
              emptyTitle="Создайте первого агента"
              emptyDescription="Начните с конкретной задачи: проверки конфигурации, анализа журналов или подготовки отчёта."
              emptyAction={
                <Button variant="primary" onClick={() => setCreate(true)}>
                  Создать агента
                </Button>
              }
              columns={[
                {
                  key: "name",
                  label: "Агент",
                  sortValue: (a) => a.name,
                  render: (a) => (
                    <Link
                      className="intel-entity-link"
                      to={`/intelligence/agents/${a.id}`}
                    >
                      <span className="intel-avatar">
                        <Bot size={18} />
                      </span>
                      <span>
                        <strong>{a.name}</strong>
                        <small>
                          {a.goal || a.ai_prompt || "Командный сценарий"}
                        </small>
                      </span>
                    </Link>
                  ),
                },
                {
                  key: "mode",
                  label: "Режим",
                  render: (a) => <IntelStatus value={a.mode} />,
                },
                {
                  key: "servers",
                  label: "Область",
                  render: (a) => a.server_names.join(", ") || "Без серверов",
                },
                {
                  key: "status",
                  label: "Последний запуск",
                  render: (a) =>
                    a.active_run_id ? (
                      <Link to={`/intelligence/runs/${a.active_run_id}`}>
                        <IntelStatus value={a.active_run_status || "running"} />
                      </Link>
                    ) : a.last_run_id ? (
                      <Link to={`/intelligence/runs/${a.last_run_id}`}>
                        <IntelStatus value={a.last_run_status || "unknown"} />
                      </Link>
                    ) : (
                      <span className="muted">Ещё не запускался</span>
                    ),
                },
                {
                  key: "next",
                  label: "Следующий запуск",
                  render: (a) =>
                    a.next_due_at ? formatDate(a.next_due_at) : "Вручную",
                },
                {
                  key: "open",
                  label: "",
                  render: (a) => (
                    <Link
                      className="text-link"
                      aria-label={`Открыть ${a.name}`}
                      to={`/intelligence/agents/${a.id}`}
                    >
                      <ArrowUpRight size={17} />
                    </Link>
                  ),
                },
              ]}
            />
          </Panel>
        </>
      )}
      {runtime && <AgentRuntimeDrawer onClose={() => setRuntime(false)} />}{" "}
      {create && <AgentEditor agent={null} onClose={() => setCreate(false)} />}
    </>
  );
}

export function AgentDetailPage() {
  const { id } = useParams();
  const agentId = Number(id);
  const nav = useNavigate();
  const op = useOperation();
  const [edit, setEdit] = useState(false);
  const [remove, setRemove] = useState(false);
  const [launch, setLaunch] = useState(false);
  const q = useQuery({
    queryKey: ["intelligence", "agents"],
    queryFn: service.agents,
  });
  const runs = useQuery({
    queryKey: ["intelligence", "agent-runs", agentId],
    queryFn: () => service.runs(agentId),
    refetchInterval: 15000,
  });
  const agent = q.data?.agents.find((a) => a.id === agentId);
  if (q.isPending) return <LoadingState />;
  if (q.error)
    return <ErrorState error={q.error} retry={() => void q.refetch()} />;
  if (!agent)
    return (
      <EmptyState
        title="Агент не найден"
        action={<Link to="/intelligence/agents">К списку агентов</Link>}
      />
    );
  return (
    <>
      <Link className="intel-back" to="/intelligence/agents">
        <ArrowLeft size={15} />
        Агенты
      </Link>
      <PageHeader
        title={agent.name}
        description={agent.goal || agent.ai_prompt}
        actions={
          <>
            <Button onClick={() => setEdit(true)}>Настроить</Button>
            <Button
              variant="primary"
              disabled={!!agent.active_run_id}
              onClick={() => setLaunch(true)}
            >
              <Play size={15} />
              Запустить
            </Button>
          </>
        }
      />
      {op.feedback}
      <div className="intel-metrics">
        <Metric label="Режим" value={<IntelStatus value={agent.mode} />} />
        <Metric
          label="Область"
          value={
            agent.server_ids.length
              ? `${agent.server_ids.length} серверов`
              : "Без серверов"
          }
        />
        <Metric
          label="Лимит выполнения"
          value={`${agent.max_iterations} шагов`}
          detail={`${agent.session_timeout_seconds} секунд`}
        />
      </div>
      {agent.active_run_id && (
        <div className="notice">
          <IntelStatus value={agent.active_run_status || "running"} />
          <Link to={`/intelligence/runs/${agent.active_run_id}`}>
            Открыть текущий запуск #{agent.active_run_id}
          </Link>
        </div>
      )}
      <div className="intel-grid-main">
        <Panel title="История выполнения">
          {runs.isPending ? (
            <LoadingState />
          ) : runs.error ? (
            <ErrorState error={runs.error} />
          ) : (
            <DataTable
              rows={runs.data?.runs || []}
              rowKey={(r) => r.id}
              emptyTitle="История появится после первого запуска"
              columns={[
                {
                  key: "id",
                  label: "Запуск",
                  render: (r) => (
                    <Link
                      className="text-link"
                      to={`/intelligence/runs/${r.id}`}
                    >
                      #{r.id}
                    </Link>
                  ),
                },
                {
                  key: "status",
                  label: "Состояние",
                  render: (r) => <IntelStatus value={r.status} />,
                },
                {
                  key: "server",
                  label: "Сервер",
                  render: (r) => r.server_name,
                },
                {
                  key: "date",
                  label: "Начало",
                  render: (r) => formatDate(r.started_at),
                },
              ]}
            />
          )}
        </Panel>
        <Panel title="Условия работы">
          <DetailRows
            items={[
              {
                label: "Серверы",
                value: agent.server_names.join(", ") || "Не требуются",
              },
              {
                label: "Расписание",
                value:
                  scheduleLabels[text(agent.schedule_config.mode)] ||
                  "По настройке",
              },
              {
                label: "Состояние",
                value: agent.is_enabled ? "Включён" : "Отключён",
              },
              {
                label: "Инструкции",
                value: agent.system_prompt || "По цели задачи",
              },
            ]}
          />
          <JsonDetails
            data={agent.execution_readiness}
            label="Готовность среды выполнения"
          />
          <div className="intel-pad">
            <Button variant="danger" onClick={() => setRemove(true)}>
              <Trash2 size={15} />
              Удалить агента
            </Button>
          </div>
        </Panel>
      </div>
      {edit && <AgentEditor agent={agent} onClose={() => setEdit(false)} />}
      <ConfirmDialog
        open={launch}
        onOpenChange={setLaunch}
        title="Запустить агента?"
        description={
          <>
            <p>{agent.goal || agent.ai_prompt}</p>
            <p>
              Область: {agent.server_names.join(", ") || "без серверов"}. Агент
              выполнит действия в пределах заданных прав.
            </p>
          </>
        }
        confirmLabel="Запустить"
        pending={op.pending}
        onConfirm={() =>
          void op.run(
            () => service.launchAgent(agent.id),
            "",
            (result) => {
              setLaunch(false);
              nav(`/intelligence/runs/${result.run_id}`);
            },
          )
        }
      />
      <ConfirmDialog
        open={remove}
        onOpenChange={setRemove}
        title="Удалить агента?"
        description={`Конфигурация «${agent.name}» будет удалена.`}
        confirmLabel="Удалить"
        typedText={agent.name}
        pending={op.pending}
        onConfirm={() =>
          void op.run(
            () => service.deleteAgent(agent.id),
            "",
            () => nav("/intelligence/agents"),
          )
        }
      />
    </>
  );
}

export function AgentRunPage() {
  const { id } = useParams();
  const runId = Number(id);
  const op = useOperation();
  const [editTask, setEditTask] = useState<PlanTask | null>(null);
  const [tab, setTab] = useState("report");
  const [answer, setAnswer] = useState("");
  const [confirm, setConfirm] = useState<"stop" | "approve" | "deliver" | null>(
    null,
  );
  const [cursor, setCursor] = useState("");
  const [history, setHistory] = useState<Details[]>([]);
  const q = useQuery({
    queryKey: ["intelligence", "run", runId],
    queryFn: () => service.run(runId),
    refetchInterval: (query) =>
      activeRun(query.state.data?.run.status) ? 4000 : false,
  });
  const r = q.data?.run;
  const live = useLive(
    activeRun(r?.status) ? "/ws/agents/" + runId + "/live/" : null,
    (event) => {
      if (
        [
          "agent_status",
          "agent_question",
          "agent_plan",
          "agent_report",
          "agent_init",
        ].includes(String(event.type))
      )
        void q.refetch();
    },
  );
  const control = (type: string) => {
    if (!live.send({ type }))
      throw new Error(
        "Нет соединения с запуском. Переподключитесь и повторите действие.",
      );
    return Promise.resolve();
  };
  const report = useQuery({
    queryKey: ["intelligence", "report", runId],
    queryFn: () => service.report(runId),
    refetchInterval: activeRun(r?.status) ? 5000 : false,
  });
  const details = useQuery({
    queryKey: ["intelligence", "run-details", runId, tab, cursor],
    queryFn: async () => {
      if (tab === "artifacts") {
        const result = await service.artifacts(runId);
        const items = result.items || result.artifacts || [];
        return {
          items,
          total: items.length,
          page: { has_more: false, next_cursor: null as string | null },
        };
      }
      return tab === "activity"
        ? service.activity(runId, cursor)
        : service.events(runId, cursor);
    },
    enabled: ["events", "activity", "artifacts"].includes(tab),
  });
  const items = details.data?.items || [];
  const changeTask = (taskId: number, action: string) =>
    void op.run(() => service.task(runId, taskId, { action }), "План обновлён");
  if (q.isPending) return <LoadingState />;
  if (q.error || !r) return <ErrorState error={q.error} />;
  const rep = report.data;
  return (
    <>
      <Link
        className="intel-back"
        to={
          r.agent_id
            ? `/intelligence/agents/${r.agent_id}`
            : "/intelligence/agents"
        }
      >
        <ArrowLeft size={15} />
        {r.agent_name}
      </Link>
      <PageHeader
        eyebrow={`Выполнение · #${runId}`}
        title={r.agent_name}
        description={
          <span className="intel-row">
            <IntelStatus value={r.status} />
            <span>
              {formatDate(r.started_at)} · {r.server_name}
            </span>
          </span>
        }
        actions={
          <>
            {activeRun(r.status) && (
              <Button
                variant="danger"
                disabled={live.state !== "connected"}
                onClick={() => setConfirm("stop")}
              >
                <Square size={14} />
                Остановить
              </Button>
            )}
            {activeRun(r.status) && (
              <Button
                disabled={live.state !== "connected"}
                loading={op.pending}
                onClick={() =>
                  void op.run(
                    () =>
                      control(
                        r.status === "paused" ? "agent_resume" : "agent_pause",
                      ),
                    "Запрос отправлен",
                  )
                }
              >
                {r.status === "paused" ? "Продолжить" : "Приостановить"}
              </Button>
            )}
            {activeRun(r.status) && live.state !== "connected" && (
              <Button onClick={live.reconnect}>Переподключить</Button>
            )}
            <Button
              onClick={() => {
                void q.refetch();
                void report.refetch();
              }}
            >
              <RefreshCw size={15} />
              Обновить
            </Button>
          </>
        }
      />
      {op.feedback}
      {r.status === "waiting" && (
        <Panel title="Агенту нужен ваш ответ">
          <div className="intel-pad intel-form">
            <Markdown>{r.pending_question}</Markdown>
            <Field label="Ответ" htmlFor="run-answer">
              <textarea
                id="run-answer"
                rows={3}
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
              />
            </Field>
            <Button
              variant="primary"
              disabled={!answer.trim()}
              loading={op.pending}
              onClick={() =>
                void op.run(
                  () => service.runAction(runId, "reply", { answer }),
                  "Ответ отправлен",
                  () => setAnswer(""),
                )
              }
            >
              Отправить ответ
            </Button>
          </div>
        </Panel>
      )}
      {!!r.plan_tasks?.length && (
        <Panel
          title={
            r.status === "plan_review"
              ? "Согласуйте план выполнения"
              : "План выполнения"
          }
          actions={
            r.status === "plan_review" && (
              <Button variant="primary" onClick={() => setConfirm("approve")}>
                <Check size={15} />
                Одобрить план
              </Button>
            )
          }
        >
          <div className="intel-pad intel-form">
            {(r.plan_tasks || []).map((t) => (
              <article key={t.id} className="intel-evidence">
                <div className="intel-row">
                  <strong>{t.name}</strong>
                  <IntelStatus value={t.status} />
                  {["pending", "failed", "skipped"].includes(t.status) && (
                    <>
                      <Button
                        size="sm"
                        disabled={op.pending}
                        onClick={() => setEditTask(t)}
                      >
                        Изменить
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={op.pending}
                        onClick={() => changeTask(t.id, "delete")}
                      >
                        Исключить
                      </Button>
                    </>
                  )}
                </div>
                <p>{t.description}</p>
              </article>
            ))}
          </div>
        </Panel>
      )}
      <Tabs
        value={tab}
        onChange={(value) => {
          setTab(value);
          setCursor("");
          setHistory([]);
        }}
        items={[
          { value: "report", label: "Результат" },
          { value: "activity", label: "Действия" },
          { value: "events", label: "События" },
          { value: "artifacts", label: "Материалы" },
        ]}
      />
      {tab === "report" ? (
        report.isPending ? (
          <LoadingState />
        ) : report.error ? (
          <ErrorState error={report.error} />
        ) : (
          rep && (
            <>
              <div className="intel-metrics">
                <Metric
                  label="Результат задачи"
                  value={
                    <IntelStatus
                      value={text(
                        rep.outcome.status || rep.outcome.execution_outcome,
                        "unknown",
                      )}
                    />
                  }
                  detail={text(rep.outcome.summary || rep.outcome.label, "")}
                />
                <Metric
                  label="Доказательства"
                  value={text(
                    rep.evidence_state.label || rep.evidence_state.status,
                  )}
                  detail={text(rep.evidence_state.summary, "")}
                />
                <Metric
                  label="Отчёт"
                  value={text(
                    rep.report_generation.label || rep.report_generation.status,
                  )}
                  detail={text(rep.report_generation.summary, "")}
                />
              </div>
              <div className="intel-grid-main">
                <Panel title="Выводы и рекомендации">
                  {r.final_report || r.ai_analysis ? (
                    <div className="intel-pad">
                      <Markdown>{r.final_report || r.ai_analysis}</Markdown>
                    </div>
                  ) : (
                    <DetailCards
                      items={rep.findings}
                      empty={
                        activeRun(r.status)
                          ? "Отчёт появится по мере выполнения задачи."
                          : "Итоговый текст не сформирован. Откройте события и действия для проверки результата."
                      }
                    />
                  )}
                </Panel>
                <div className="intel-stack">
                  <Panel title="Этапы">
                    <DetailCards items={rep.phases} />
                  </Panel>
                  <Panel title="Документы">
                    <div className="intel-pad intel-form">
                      {rep.document.available ? (
                        <a
                          className="btn btn-secondary btn-md"
                          href={`${rep.evidence_links.document}${rep.evidence_links.document.includes("?") ? "&" : "?"}download=1`}
                        >
                          <Download size={15} />
                          Скачать отчёт
                        </a>
                      ) : (
                        <p className="muted">Документ ещё не готов</p>
                      )}
                      <a
                        className="text-link"
                        href={rep.evidence_links.audit_export}
                      >
                        Экспорт журнала аудита
                      </a>
                      {rep.delivery.can_retry === true && (
                        <Button onClick={() => setConfirm("deliver")}>
                          Повторить доставку
                        </Button>
                      )}
                      <p className="muted">{text(rep.delivery.summary, "")}</p>
                    </div>
                  </Panel>
                </div>
              </div>
              {rep.findings.length > 0 && (r.final_report || r.ai_analysis) && (
                <Panel title="Подтверждённые находки">
                  <DetailCards items={rep.findings} />
                </Panel>
              )}
            </>
          )
        )
      ) : (
        <Panel
          title={
            tab === "events"
              ? "Журнал событий"
              : tab === "activity"
                ? "Выполненные действия"
                : "Материалы запуска"
          }
        >
          {details.isPending ? (
            <LoadingState />
          ) : details.error ? (
            <ErrorState error={details.error} />
          ) : (
            <>
              <DetailCards items={[...history, ...items]} />
              {details.data &&
                "page" in details.data &&
                details.data.page.has_more && (
                  <div className="intel-pad">
                    <Button
                      onClick={() => {
                        setHistory([...history, ...items]);
                        setCursor(details.data?.page.next_cursor || "");
                      }}
                    >
                      Загрузить более ранние
                    </Button>
                  </div>
                )}
            </>
          )}
        </Panel>
      )}
      {editTask && (
        <PlanTaskEditor
          runId={runId}
          task={editTask}
          onClose={() => setEditTask(null)}
        />
      )}
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(v) => {
          if (!v) setConfirm(null);
        }}
        title={
          confirm === "stop"
            ? "Остановить выполнение?"
            : confirm === "approve"
              ? "Одобрить план?"
              : "Повторить доставку отчёта?"
        }
        description={
          confirm === "stop"
            ? "Агент получит запрос остановки. Уже выполненные изменения сохранятся."
            : confirm === "approve"
              ? "После согласования агент приступит к выполнению задач плана."
              : "Отчёт будет отправлен по настроенному внешнему каналу."
        }
        pending={op.pending}
        confirmLabel={
          confirm === "stop"
            ? "Остановить"
            : confirm === "approve"
              ? "Одобрить"
              : "Отправить"
        }
        onConfirm={() =>
          void op.run(
            () =>
              confirm === "stop"
                ? control("agent_stop")
                : service.runAction(
                    runId,
                    confirm === "approve" ? "approve-plan" : "report/deliver",
                  ),
            "Запрос принят",
            () => setConfirm(null),
          )
        }
      />
    </>
  );
}
