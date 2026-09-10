import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  GitBranch,
  Play,
  Plus,
  RefreshCw,
  Square,
} from "lucide-react";
import {
  intelligenceApi as service,
  type Details,
  type MarsQuestion,
} from "@/api/intelligence";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  PageHeader,
  Panel,
  Tabs,
} from "@/components/ui";
import { formatDate } from "@/lib/utils";
import {
  activeRun,
  DetailCards,
  DetailRows,
  IntelStatus,
  Markdown,
  text,
  useOperation,
} from "./common";
import { useLive } from "./useLive";

export function MarsPage() {
  const nav = useNavigate();
  const op = useOperation();
  const [create, setCreate] = useState(false);
  const [brief, setBrief] = useState("");
  const q = useQuery({
    queryKey: ["intelligence", "mars-projects"],
    queryFn: service.marsProjects,
  });
  return (
    <>
      <PageHeader
        eyebrow="Интеллект"
        title="MARS · Проектные задачи"
        description="От постановки задачи до согласованного плана, реализации и проверки."
        actions={
          <Button variant="primary" onClick={() => setCreate(true)}>
            <Plus size={16} />
            Новая задача
          </Button>
        }
      />
      {op.feedback}
      <div className="intel-workflow">
        <span>
          <span>1</span>Постановка
        </span>
        <ArrowRight size={15} />
        <span>
          <span>2</span>Согласование плана
        </span>
        <ArrowRight size={15} />
        <span>
          <span>3</span>Выполнение и проверка
        </span>
      </div>
      <Panel>
        {q.isPending ? (
          <LoadingState />
        ) : q.error ? (
          <ErrorState error={q.error} retry={() => void q.refetch()} />
        ) : (
          <DataTable
            rows={q.data?.projects || []}
            rowKey={(p) => p.session.id}
            searchValue={(p) => p.session.task_brief}
            emptyTitle="Превратите задачу в проверенный результат"
            emptyDescription="Опишите требуемое изменение. MARS уточнит условия, подготовит план и начнёт работу после вашего согласования."
            emptyAction={
              <Button variant="primary" onClick={() => setCreate(true)}>
                Создать задачу
              </Button>
            }
            columns={[
              {
                key: "title",
                label: "Задача",
                render: (p) => (
                  <Link
                    className="intel-entity-link"
                    to={`/intelligence/mars/sessions/${p.session.id}`}
                  >
                    <span className="intel-avatar">
                      <GitBranch size={18} />
                    </span>
                    <span>
                      <strong>{p.session.task_brief}</strong>
                      <small>{p.session.workspace.name}</small>
                    </span>
                  </Link>
                ),
              },
              {
                key: "status",
                label: "Состояние",
                render: (p) => (
                  <IntelStatus
                    value={p.latest_run?.status || p.session.status}
                  />
                ),
              },
              { key: "runs", label: "Запусков", render: (p) => p.run_count },
              {
                key: "updated",
                label: "Обновлено",
                sortValue: (p) => p.session.updated_at,
                render: (p) => formatDate(p.session.updated_at),
              },
              {
                key: "open",
                label: "",
                render: (p) =>
                  p.latest_run ? (
                    <Link
                      className="text-link"
                      to={`/intelligence/mars/runs/${p.latest_run.id}`}
                    >
                      Запуск #{p.latest_run.id}
                    </Link>
                  ) : (
                    <Link
                      className="text-link"
                      to={`/intelligence/mars/sessions/${p.session.id}`}
                    >
                      Продолжить
                    </Link>
                  ),
              },
            ]}
          />
        )}
      </Panel>
      <Drawer
        open={create}
        onOpenChange={(v) => {
          if (!op.pending) setCreate(v);
        }}
        title="Новая проектная задача"
        description="Задайте цель и ожидаемый результат. Следующим шагом MARS предложит вопросы по задаче."
        footer={
          <>
            <Button disabled={op.pending} onClick={() => setCreate(false)}>
              Отмена
            </Button>
            <Button
              variant="primary"
              loading={op.pending}
              disabled={!brief.trim()}
              onClick={() =>
                void op.run(
                  () => service.createMars(brief.trim()),
                  "",
                  (result) => {
                    setCreate(false);
                    nav(`/intelligence/mars/sessions/${result.session.id}`);
                  },
                )
              }
            >
              Начать постановку
              <ArrowRight size={15} />
            </Button>
          </>
        }
      >
        <div className="intel-form">
          {op.feedback}
          <Field label="Что нужно сделать?" htmlFor="mars-brief">
            <textarea
              id="mars-brief"
              rows={9}
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              placeholder="Опишите изменение, требования и критерии готовности…"
            />
          </Field>
          {op.pending && (
            <p className="muted" role="status">
              MARS изучает задачу и формирует вопросы. Это может занять
              некоторое время.
            </p>
          )}
        </div>
      </Drawer>
    </>
  );
}

function InterviewQuestion({
  question,
  value,
  onChange,
}: {
  question: MarsQuestion;
  value: string;
  onChange: (value: string) => void;
}) {
  const chosen = value.split("; ").filter(Boolean);
  return (
    <Field
      label={`${question.question}${question.required ? " *" : ""}`}
      htmlFor={`mars-question-${question.id}`}
    >
      <div className="intel-form">
        {question.options?.length > 0 && (
          <div className="intel-choice-list">
            {question.options.map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={
                  question.kind === "multi_choice_text"
                    ? chosen.includes(option)
                    : value === option
                }
                onClick={() =>
                  onChange(
                    question.kind === "multi_choice_text"
                      ? (chosen.includes(option)
                          ? chosen.filter((v) => v !== option)
                          : [...chosen, option]
                        ).join("; ")
                      : option,
                  )
                }
              >
                {option}
              </button>
            ))}
          </div>
        )}
        <textarea
          id={`mars-question-${question.id}`}
          rows={question.kind === "textarea" ? 4 : 2}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={question.placeholder || "Уточните свой вариант"}
          required={question.required}
        />
      </div>
    </Field>
  );
}

export function MarsSessionPage() {
  const { id } = useParams();
  const sessionId = Number(id);
  const nav = useNavigate();
  const op = useOperation();
  const q = useQuery({
    queryKey: ["intelligence", "mars-session", sessionId],
    queryFn: () => service.marsSession(sessionId),
  });
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [plan, setPlan] = useState("");
  const [step, setStep] = useState("questions");
  const [approve, setApprove] = useState(false);
  const [launch, setLaunch] = useState(false);
  const [allowDirty, setAllowDirty] = useState(false);
  const [testCommand, setTestCommand] = useState("");
  const hydrated = useRef<number | null>(null);
  useEffect(() => {
    if (q.data && hydrated.current !== q.data.session.id) {
      const session = q.data.session;
      hydrated.current = session.id;
      queueMicrotask(() => {
        setAnswers(session.answers);
        setPlan(session.generated_plan);
        setStep(session.status === "interview" ? "questions" : "plan");
      });
    }
  }, [q.data]);
  const session = q.data?.session;
  const complete = session?.interview_questions.every(
    (question) => !question.required || answers[question.id]?.trim(),
  );
  if (q.isPending) return <LoadingState />;
  if (q.error || !session) return <ErrorState error={q.error} />;
  return (
    <>
      <Link className="intel-back" to="/intelligence/mars">
        <ArrowLeft size={15} />
        Проектные задачи
      </Link>
      <PageHeader
        eyebrow={`MARS · Задача #${session.id}`}
        title="Подготовка к выполнению"
        description={session.task_brief}
        actions={<IntelStatus value={session.status} />}
      />
      {op.feedback}
      <Tabs
        value={step}
        onChange={setStep}
        items={[
          { value: "questions", label: "Условия задачи" },
          { value: "plan", label: "План выполнения" },
        ]}
      />
      <div className="intel-grid-main">
        <Panel
          title={
            step === "questions"
              ? "Уточните задачу"
              : "Проверьте и согласуйте план"
          }
        >
          <div className="intel-pad intel-form">
            {step === "questions" ? (
              <>
                {session.interview_questions.map((question) => (
                  <InterviewQuestion
                    key={question.id}
                    question={question}
                    value={answers[question.id] || ""}
                    onChange={(value) =>
                      setAnswers({ ...answers, [question.id]: value })
                    }
                  />
                ))}
                <Button
                  variant="primary"
                  loading={op.pending}
                  disabled={!complete}
                  onClick={() =>
                    void op.run(
                      () => service.marsAnswer(sessionId, answers),
                      "План подготовлен",
                      (result) => {
                        setPlan(result.session.generated_plan);
                        setStep("plan");
                      },
                    )
                  }
                >
                  Подготовить план
                  <ArrowRight size={16} />
                </Button>
              </>
            ) : (
              <>
                {plan ? (
                  <>
                    <Field
                      label="План выполнения"
                      htmlFor="mars-plan"
                      description="Вы можете изменить план перед согласованием."
                    >
                      <textarea
                        id="mars-plan"
                        rows={20}
                        value={plan}
                        onChange={(e) => setPlan(e.target.value)}
                      />
                    </Field>
                    <details>
                      <summary>Предварительный просмотр</summary>
                      <Markdown>{plan}</Markdown>
                    </details>
                    <div className="intel-row">
                      <Button
                        variant="primary"
                        loading={op.pending}
                        disabled={!plan.trim()}
                        onClick={() => setApprove(true)}
                      >
                        <Check size={16} />
                        Согласовать план
                      </Button>
                      {session.status === "approved" && (
                        <Button
                          disabled={plan !== session.generated_plan}
                          onClick={() => setLaunch(true)}
                        >
                          <Play size={16} />
                          Запустить
                        </Button>
                      )}
                    </div>
                    {session.status === "approved" &&
                      plan !== session.generated_plan && (
                        <p className="muted">
                          Согласуйте изменённый план перед запуском.
                        </p>
                      )}
                  </>
                ) : (
                  <EmptyState
                    title="Сначала заполните условия задачи"
                    action={
                      <Button onClick={() => setStep("questions")}>
                        Перейти к вопросам
                      </Button>
                    }
                  />
                )}
              </>
            )}
          </div>
        </Panel>
        <Panel title="Рабочая область">
          <DetailRows
            items={[
              { label: "Пространство", value: session.workspace.name },
              {
                label: "Рабочая папка",
                value: <code>{session.workspace.root_path}</code>,
              },
              {
                label: "Доступность",
                value: session.workspace.enabled ? "Включено" : "Отключено",
              },
              {
                label: "Согласование",
                value:
                  session.status === "approved"
                    ? "План согласован"
                    : "Ожидает вашего решения",
              },
            ]}
          />
          <div className="intel-pad">
            <p className="muted">
              Выполнение начинается только после согласования плана. Результаты
              и проверка сохранятся в журнале запуска.
            </p>
          </div>
        </Panel>
      </div>
      <ConfirmDialog
        open={approve}
        onOpenChange={setApprove}
        title="Согласовать план?"
        description="Текущая редакция плана будет сохранена для выполнения. Запуск выполняется отдельным действием."
        confirmLabel="Согласовать"
        pending={op.pending}
        onConfirm={() =>
          void op.run(
            () => service.marsApprove(sessionId, plan),
            "План согласован",
            () => {
              setApprove(false);
              setLaunch(true);
            },
          )
        }
      />
      <Drawer
        open={launch}
        onOpenChange={setLaunch}
        title="Запуск MARS"
        description="Проверьте условия запуска и проверки результата."
        footer={
          <>
            <Button disabled={op.pending} onClick={() => setLaunch(false)}>
              Отмена
            </Button>
            <Button
              variant="primary"
              loading={op.pending}
              onClick={() =>
                void op.run(
                  () =>
                    service.marsLaunch(sessionId, {
                      allow_dirty: allowDirty,
                      test_command: testCommand,
                    }),
                  "",
                  (result) => nav(`/intelligence/mars/runs/${result.run.id}`),
                )
              }
            >
              <Play size={16} />
              Запустить выполнение
            </Button>
          </>
        }
      >
        <div className="intel-form">
          {op.feedback}
          <p>{session.task_brief}</p>
          <Field
            label="Команда проверки результата"
            htmlFor="mars-test"
            description="Оставьте пустым, чтобы использовать настроенную проверку рабочего пространства."
          >
            <input
              id="mars-test"
              className="intel-mono"
              value={testCommand}
              onChange={(e) => setTestCommand(e.target.value)}
            />
          </Field>
          <label className="intel-check">
            <input
              type="checkbox"
              checked={allowDirty}
              onChange={(e) => setAllowDirty(e.target.checked)}
            />
            Разрешить работу при наличии несохранённых в Git изменений
          </label>
        </div>
      </Drawer>
    </>
  );
}

export function MarsRunPage() {
  const { id } = useParams();
  const runId = Number(id);
  const client = useQueryClient();
  const op = useOperation();
  const [tab, setTab] = useState("result");
  const [stop, setStop] = useState(false);
  const [events, setEvents] = useState<Details[]>([]);
  const q = useQuery({
    queryKey: ["intelligence", "mars-run", runId],
    queryFn: () => service.marsRun(runId),
    refetchInterval: (query) =>
      activeRun(query.state.data?.run.status) ? 5000 : false,
  });
  const r = q.data?.run;
  const eventQuery = useQuery({
    queryKey: ["intelligence", "mars-events", runId],
    queryFn: () => service.marsEvents(runId),
    refetchInterval: activeRun(r?.status) ? 10000 : false,
  });
  useEffect(() => {
    if (eventQuery.data) {
      const received = eventQuery.data.events;
      queueMicrotask(() =>
        setEvents((prev) => {
          const byId = new Map(
            [...prev, ...received].map((e) => [text(e.id), e]),
          );
          return [...byId.values()].sort((a, b) => Number(a.id) - Number(b.id));
        }),
      );
    }
  }, [eventQuery.data]);
  const live = useLive(
    activeRun(r?.status) ? `/ws/mars/runs/${runId}/live/` : null,
    (event) => {
      if (event.type === "mars_event") {
        const item = event.event as Details;
        setEvents((prev) =>
          prev.some((e) => e.id === item.id) ? prev : [...prev, item],
        );
        void client.invalidateQueries({
          queryKey: ["intelligence", "mars-run", runId],
        });
      }
    },
    () => void eventQuery.refetch(),
  );
  if (q.isPending) return <LoadingState />;
  if (q.error || !r) return <ErrorState error={q.error} />;
  return (
    <>
      <Link
        className="intel-back"
        to={`/intelligence/mars/sessions/${r.session_id}`}
      >
        <ArrowLeft size={15} />К задаче
      </Link>
      <PageHeader
        eyebrow="MARS · Выполнение"
        title={`Запуск #${r.id}`}
        description={
          <span className="intel-row">
            <IntelStatus value={r.status} />
            <span>{formatDate(r.created_at)}</span>
            {activeRun(r.status) && <IntelStatus value={live.state} />}
          </span>
        }
        actions={
          <>
            <Button
              onClick={() => {
                void q.refetch();
                void eventQuery.refetch();
              }}
            >
              <RefreshCw size={16} />
              Обновить
            </Button>
            {activeRun(r.status) && (
              <Button
                variant="danger"
                disabled={r.runtime_control.stop_requested === true}
                onClick={() => setStop(true)}
              >
                <Square size={14} />
                {r.runtime_control.stop_requested
                  ? "Остановка запрошена"
                  : "Остановить"}
              </Button>
            )}
          </>
        }
      />
      {op.feedback}
      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { value: "result", label: "Результат" },
          { value: "review", label: "Проверка" },
          { value: "events", label: "Журнал", count: events.length },
        ]}
      />
      {tab === "result" ? (
        <Panel title="Отчёт по задаче">
          <div className="intel-pad">
            {r.final_report || r.codex_summary ? (
              <Markdown>{r.final_report || r.codex_summary}</Markdown>
            ) : (
              <EmptyState
                title={
                  activeRun(r.status)
                    ? "MARS выполняет задачу"
                    : "Отчёт не сформирован"
                }
                description={
                  activeRun(r.status)
                    ? "События появляются в журнале. Здесь будет итоговый результат."
                    : "Проверьте события запуска, чтобы определить причину."
                }
              />
            )}
          </div>
        </Panel>
      ) : tab === "review" ? (
        <div className="intel-stack">
          <Panel title="Независимая проверка">
            <div className="intel-pad">
              {r.gemini_review ? (
                <Markdown>{r.gemini_review}</Markdown>
              ) : (
                <p className="muted">Результат проверки пока не получен.</p>
              )}
            </div>
          </Panel>
          <Panel title="Проверка выполнения">
            <div className="intel-pad">
              {r.test_output ? (
                <pre className="code-block">{r.test_output}</pre>
              ) : (
                <p className="muted">Вывод проверок пока отсутствует.</p>
              )}
            </div>
          </Panel>
        </div>
      ) : (
        <Panel title="События выполнения">
          {eventQuery.error ? (
            <ErrorState error={eventQuery.error} />
          ) : eventQuery.isPending ? (
            <LoadingState />
          ) : (
            <DetailCards items={events} />
          )}
        </Panel>
      )}
      <ConfirmDialog
        open={stop}
        onOpenChange={setStop}
        title="Остановить MARS?"
        description="Текущая задача получит запрос остановки. Уже созданные файлы и изменения сохранятся."
        pending={op.pending}
        confirmLabel="Остановить"
        onConfirm={() =>
          void op.run(
            () => service.marsStop(runId),
            "Запрос остановки отправлен",
            () => setStop(false),
          )
        }
      />
    </>
  );
}
