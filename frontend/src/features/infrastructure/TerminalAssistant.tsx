import { useEffect, useReducer, useRef, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Check,
  Copy,
  Download,
  FileText,
  Send,
  Settings2,
  Sparkles,
  Square,
  Trash2,
  X,
} from "lucide-react";
import { infrastructureApi, type ServerDetail } from "@/api/infrastructure";
import {
  defaultTerminalAiOptions,
  terminalAiRequest,
  type TerminalAiEvent,
  type TerminalAiMode,
  type TerminalAiOptions,
  type TerminalAiQuestion,
  type TerminalAiCommand,
} from "@/api/terminal-ai";
import {
  Button,
  ConfirmDialog,
  Feedback,
  Field,
  StatusBadge,
} from "@/components/ui";
import {
  initialTerminalAiState,
  terminalAiReducer,
  type AiTool,
} from "./terminal-ai-state";
import "./terminal-assistant.css";

export interface TerminalAssistantProps {
  server: ServerDetail;
  connected: boolean;
  send: (event: Record<string, unknown>) => boolean;
  subscribe: (listener: (event: TerminalAiEvent) => void) => () => void;
  selection?: () => string;
  onInsert?: (command: string) => void;
}
const modes: { value: TerminalAiMode; label: string; description: string }[] = [
  {
    value: "confirm",
    label: "Предложить команды",
    description: "Каждая предложенная команда ожидает вашего подтверждения.",
  },
  {
    value: "step",
    label: "Выполнять по шагам",
    description:
      "После каждой команды ассистент анализирует результат и выбирает следующий шаг.",
  },
  {
    value: "fast",
    label: "Выполнить план",
    description:
      "Ассистент выполняет план; действия с риском запрашивают подтверждение.",
  },
  {
    value: "auto",
    label: "Выбрать режим автоматически",
    description: "Ассистент выбирает подходящий режим и выполняет задачу.",
  },
  {
    value: "agent",
    label: "Самостоятельная задача",
    description:
      "Агент использует инструменты и проверяет результат. Разрешения на команды запрашиваются по политике сервера.",
  },
];
const stateLabels: Record<string, string> = {
  idle: "Готов",
  sending: "Запрос отправлен",
  thinking: "Готовит ответ",
  running: "Выполняется",
  waiting_confirm: "Ожидает подтверждения",
  waiting_reply: "Нужен ваш ответ",
  explaining: "Объясняет вывод",
  generating_report: "Готовит отчёт",
  stopping: "Останавливается",
  disconnected: "Нет соединения",
  error: "Ошибка",
};
export function TerminalAssistant({
  server,
  connected,
  send,
  subscribe,
  selection,
  onInsert,
}: TerminalAssistantProps) {
  const [state, dispatch] = useReducer(
    terminalAiReducer,
    initialTerminalAiState,
  );
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState<TerminalAiMode>("confirm");
  const [options, setOptions] = useState<TerminalAiOptions>(
    defaultTerminalAiOptions,
  );
  const [settings, setSettings] = useState(false);
  const [clear, setClear] = useState(false);
  const [copyMessage, setCopyMessage] = useState("");
  const [selectedOutput, setSelectedOutput] = useState("");
  const feed = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  useEffect(
    () => subscribe((event) => dispatch({ type: "event", event })),
    [subscribe],
  );
  const busy = !["idle", "error", "disconnected"].includes(state.status);
  const hasResults = state.commands.some((command) =>
    ["done", "completed", "failed", "cancelled", "skipped"].includes(
      command.status,
    ),
  );
  useEffect(() => {
    if (follow.current && feed.current)
      feed.current.scrollTop = feed.current.scrollHeight;
  }, [
    state.messages,
    state.commands,
    state.tools,
    state.question,
    state.report,
  ]);
  function transmit(payload: Record<string, unknown>) {
    if (!connected || !send(payload)) {
      dispatch({
        type: "error",
        message: "Нет соединения. Запрос не отправлен.",
      });
      return false;
    }
    return true;
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!message.trim() || busy) return;
    const text = selectedOutput
      ? `${message.trim()}\n\nВыделенный вывод терминала:\n${selectedOutput}`
      : message.trim();
    if (transmit(terminalAiRequest(text, mode, options))) {
      dispatch({ type: "request", message: message.trim() });
      setMessage("");
      setSelectedOutput("");
    }
  }
  function explainSelection() {
    const output = selection?.().trim() ?? "";
    if (!output) {
      setCopyMessage("Сначала выделите строки в терминале.");
      return;
    }
    if (
      transmit({
        type: "ai_explain_output",
        id: "terminal-selection",
        cmd: "",
        output: output.slice(-20000),
      })
    )
      dispatch({
        type: "event",
        event: { type: "ai_status", status: "explaining" },
      });
  }
  function copy(text: string) {
    void navigator.clipboard.writeText(text).then(
      () => setCopyMessage("Скопировано"),
      () => setCopyMessage("Не удалось скопировать. Выделите текст вручную."),
    );
  }
  function downloadReport() {
    const blob = new Blob([state.report], {
      type: "text/markdown;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `terminal-${server.id}-${state.runId ?? "report"}.md`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const approve = (id: number, action: "confirm" | "cancel") => {
    if (id !== state.awaitingCommandId) return;
    if (
      transmit({ type: action === "confirm" ? "ai_confirm" : "ai_cancel", id })
    )
      dispatch({ type: "command-sent", id, action });
  };
  return (
    <section
      className="terminal-ai"
      aria-label={`Ассистент терминала ${server.name}`}
    >
      <header className="terminal-ai-header">
        <div>
          <h2>
            <Sparkles size={16} />
            Ассистент
          </h2>
          <span className="terminal-ai-target">
            {server.name} · {server.host}
          </span>
        </div>
        <div className="row">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Настройки ассистента"
            aria-expanded={settings}
            onClick={() => setSettings(!settings)}
          >
            <Settings2 size={15} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Очистить историю ассистента"
            disabled={busy || !connected}
            onClick={() => setClear(true)}
          >
            <Trash2 size={14} />
          </Button>
        </div>
      </header>
      <div className="terminal-ai-state" role="status">
        <StatusBadge
          status={
            !connected
              ? "disconnected"
              : state.status === "idle"
                ? "success"
                : state.status === "error"
                  ? "failed"
                  : "running"
          }
        >
          {!connected
            ? "SSH не подключён"
            : (stateLabels[state.status] ?? state.status)}
        </StatusBadge>
        {state.progress && <span>{state.progress}</span>}
        {busy && (
          <Button
            variant="danger"
            size="sm"
            disabled={!connected || state.status === "stopping"}
            onClick={() => {
              if (transmit({ type: "ai_stop" })) dispatch({ type: "stopping" });
            }}
          >
            <Square size={12} />
            Стоп
          </Button>
        )}
      </div>
      {settings && (
        <AssistantSettings
          server={server}
          mode={mode}
          options={options}
          onChange={setOptions}
          disabled={busy}
        />
      )}
      <Feedback error={state.error || undefined} />
      {copyMessage && (
        <p className="terminal-ai-feedback" role="status">
          {copyMessage}
        </p>
      )}
      <div
        className="terminal-ai-feed"
        ref={feed}
        onScroll={() => {
          const el = feed.current;
          if (el)
            follow.current =
              el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        aria-label="Диалог и результаты ассистента"
      >
        {state.messages.length === 0 && (
          <div className="terminal-ai-intro">
            <Sparkles size={23} />
            <h3>Задача в контексте сервера</h3>
            <p>
              Опишите, что проверить или изменить. Ассистент получает контекст
              текущего терминала.
            </p>
            {state.restoredCount > 0 && (
              <p>
                На сервере восстановлен контекст предыдущих сообщений:{" "}
                {state.restoredCount}.
              </p>
            )}
          </div>
        )}
        {state.messages.map((item) => (
          <article className={`terminal-ai-message ${item.role}`} key={item.id}>
            <div className="terminal-ai-message-label">
              {item.role === "user" ? "Вы" : "Ассистент"}
            </div>
            <div className="markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {item.text}
              </ReactMarkdown>
            </div>
          </article>
        ))}
        {state.todos.length > 0 && (
          <section className="terminal-ai-plan" aria-label="План агента">
            <h3>План работы</h3>
            {state.todos.map((todo) => (
              <div key={todo.id} className="terminal-ai-todo">
                <StatusBadge
                  status={
                    todo.status === "in_progress" ? "running" : todo.status
                  }
                />
                <span>{todo.content}</span>
              </div>
            ))}
          </section>
        )}
        {state.commands.map((command) => (
          <CommandCard
            key={`${state.runId}:${command.id}`}
            command={command}
            awaiting={state.awaitingCommandId === command.id}
            connected={connected}
            busy={busy}
            onApprove={() => approve(command.id, "confirm")}
            onSkip={() => approve(command.id, "cancel")}
            onCopy={() => copy(command.cmd)}
            onInsert={
              onInsert && !/[\r\n]/.test(command.cmd)
                ? () => onInsert(command.cmd)
                : undefined
            }
            onExplain={() => {
              if (
                transmit({
                  type: "ai_explain_output",
                  id: command.id,
                  cmd: command.cmd,
                  output: command.output ?? "",
                  exit_code: command.exit_code,
                })
              )
                dispatch({
                  type: "event",
                  event: { type: "ai_status", status: "explaining" },
                });
            }}
          />
        ))}
        {state.tools.length > 0 && (
          <section className="terminal-ai-tools" aria-label="Действия агента">
            <h3>Действия агента</h3>
            {state.tools.map((tool, index) => (
              <ToolCard key={`${tool.iteration}:${index}`} tool={tool} />
            ))}
          </section>
        )}
        {state.question && (
          <QuestionCard
            key={state.question.q_id}
            question={state.question}
            connected={connected}
            onReply={(text) => {
              if (
                transmit({ type: "ai_reply", q_id: state.question!.q_id, text })
              )
                dispatch({ type: "reply" });
            }}
          />
        )}
        {state.report && (
          <article className="terminal-ai-report">
            <div className="spread">
              <h3>Отчёт</h3>
              <div className="row">
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label="Скопировать отчёт"
                  onClick={() => copy(state.report)}
                >
                  <Copy size={13} />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label="Скачать отчёт"
                  onClick={downloadReport}
                >
                  <Download size={13} />
                </Button>
              </div>
            </div>
            <StatusBadge status={state.reportStatus} />
            <div className="markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {state.report}
              </ReactMarkdown>
            </div>
          </article>
        )}
      </div>
      <div className="terminal-ai-actions">
        {selection && (
          <Button
            size="sm"
            variant="ghost"
            disabled={busy || !connected}
            onClick={explainSelection}
          >
            Объяснить выделенное
          </Button>
        )}
        {hasResults && (
          <Button
            size="sm"
            variant="ghost"
            disabled={busy || !connected}
            onClick={() => {
              if (
                transmit({ type: "ai_generate_report", force: !!state.report })
              )
                dispatch({
                  type: "event",
                  event: { type: "ai_status", status: "generating_report" },
                });
            }}
          >
            <FileText size={13} />
            {state.report ? "Обновить отчёт" : "Сформировать отчёт"}
          </Button>
        )}
      </div>
      <form className="terminal-ai-composer" onSubmit={submit}>
        <Field label="Режим работы" htmlFor={`terminal-mode-${server.id}`}>
          <select
            id={`terminal-mode-${server.id}`}
            disabled={busy}
            value={mode}
            onChange={(event) => setMode(event.target.value as TerminalAiMode)}
          >
            {modes.map((item) => (
              <option value={item.value} key={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </Field>
        <p className="terminal-ai-mode-hint">
          {modes.find((item) => item.value === mode)?.description}
        </p>
        {selectedOutput && (
          <div className="terminal-ai-attachment">
            <span>Выделенный вывод · {selectedOutput.length} символов</span>
            <Button
              size="icon"
              variant="ghost"
              aria-label="Убрать выделенный вывод"
              onClick={() => setSelectedOutput("")}
            >
              <X size={12} />
            </Button>
            <pre>{selectedOutput.slice(0, 800)}</pre>
          </div>
        )}
        <label className="sr-only" htmlFor={`terminal-ai-message-${server.id}`}>
          Задача для ассистента
        </label>
        <textarea
          id={`terminal-ai-message-${server.id}`}
          rows={3}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          maxLength={10000}
          placeholder={
            connected
              ? "Что нужно сделать на этом сервере?"
              : "Сначала подключитесь к SSH"
          }
          disabled={!connected}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <div className="spread">
          {selection && (
            <Button
              variant="ghost"
              size="sm"
              disabled={!connected || busy}
              onClick={() => {
                const output = selection().trim();
                if (output) setSelectedOutput(output.slice(-20000));
                else setCopyMessage("Выделите нужные строки в терминале.");
              }}
            >
              Добавить выделение
            </Button>
          )}
          <Button
            type="submit"
            variant="primary"
            disabled={!connected || busy || !message.trim()}
          >
            <Send size={14} />
            {mode === "confirm" ? "Спросить" : "Начать задачу"}
          </Button>
        </div>
      </form>
      <ConfirmDialog
        open={clear}
        onOpenChange={setClear}
        title="Очистить историю ассистента?"
        description={`Сохранённый контекст AI-диалога для ${server.name} будет удалён. Это действие выполняется на сервере.`}
        confirmLabel="Очистить историю"
        onConfirm={() => {
          if (transmit({ type: "ai_clear_memory" })) {
            dispatch({ type: "clear-memory" });
            setClear(false);
          }
        }}
      />
    </section>
  );
}

function CommandCard({
  command,
  awaiting,
  connected,
  busy,
  onApprove,
  onSkip,
  onCopy,
  onExplain,
  onInsert,
}: {
  command: TerminalAiCommand;
  awaiting: boolean;
  connected: boolean;
  busy: boolean;
  onApprove: () => void;
  onSkip: () => void;
  onCopy: () => void;
  onExplain: () => void;
  onInsert?: () => void;
}) {
  const result =
    command.status === "done"
      ? command.exit_code === 0
        ? "completed"
        : "failed"
      : command.status;
  return (
    <article className={`terminal-ai-command ${awaiting ? "awaiting" : ""}`}>
      <div className="spread">
        <strong>Команда {command.id}</strong>
        <StatusBadge status={result} />
      </div>
      <pre>{command.cmd}</pre>
      {command.why && <p>{command.why}</p>}
      {(command.risk_reasons ?? []).map((reason, index) => (
        <p className="terminal-ai-risk" key={index}>
          {reason}
        </p>
      ))}
      {command.blocked && (
        <p className="terminal-ai-risk">
          Выполнение запрещено политикой: {command.reason}
        </p>
      )}
      {command.dry_run && <p>Проверка без исполнения.</p>}
      {command.exit_code != null && (
        <small>Код завершения: {command.exit_code}</small>
      )}
      {command.output && (
        <details>
          <summary>Вывод команды</summary>
          <pre>{command.output}</pre>
        </details>
      )}
      {command.explanation && (
        <div className="markdown terminal-ai-explanation">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {command.explanation}
          </ReactMarkdown>
        </div>
      )}
      <div className="terminal-ai-actions">
        {awaiting && !command.blocked ? (
          <>
            <Button
              size="sm"
              variant="primary"
              disabled={!connected}
              onClick={onApprove}
            >
              <Check size={13} />
              Выполнить один раз
            </Button>
            <Button size="sm" disabled={!connected} onClick={onSkip}>
              Пропустить
            </Button>
          </>
        ) : null}
        <Button size="sm" variant="ghost" onClick={onCopy}>
          <Copy size={12} />
          Копия
        </Button>
        {onInsert && (
          <Button
            size="sm"
            variant="ghost"
            disabled={!connected || busy || command.blocked}
            onClick={onInsert}
          >
            Вставить
          </Button>
        )}
        {command.output && (
          <Button
            size="sm"
            variant="ghost"
            disabled={!connected || busy}
            onClick={onExplain}
          >
            Объяснить
          </Button>
        )}
      </div>
    </article>
  );
}
function ToolCard({ tool }: { tool: AiTool }) {
  const known = ["cmd", "command", "path", "target", "query", "url", "pattern"];
  const args = known.flatMap((key) =>
    typeof tool.args[key] === "string"
      ? [{ key, value: String(tool.args[key]) }]
      : [],
  );
  return (
    <details className="terminal-ai-tool" open={tool.status === "running"}>
      <summary>
        <span>
          {tool.iteration}.{" "}
          {(
            {
              shell: "Команда",
              read_file: "Чтение файла",
              write_file: "Запись файла",
              search: "Поиск",
              ask_user: "Вопрос оператору",
              todo_write: "Обновление плана",
              list_targets: "Целевые серверы",
            } as Record<string, string>
          )[tool.tool] ?? tool.tool}
        </span>
        <StatusBadge status={tool.status} />
      </summary>
      {args.length > 0 && (
        <dl>
          {args.map((arg) => (
            <div key={arg.key}>
              <dt>
                {
                  (
                    {
                      cmd: "Команда",
                      command: "Команда",
                      path: "Путь",
                      target: "Сервер",
                      query: "Запрос",
                      url: "Адрес",
                      pattern: "Шаблон",
                    } as Record<string, string>
                  )[arg.key]
                }
              </dt>
              <dd>{arg.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {tool.output && <pre>{tool.output}</pre>}
      {tool.error && <p className="terminal-ai-risk">{tool.error}</p>}
      {typeof tool.data?.exit_code === "number" && (
        <small>Код завершения: {tool.data.exit_code}</small>
      )}
    </details>
  );
}
function QuestionCard({
  question,
  connected,
  onReply,
}: {
  question: TerminalAiQuestion;
  connected: boolean;
  onReply: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const [values, setValues] = useState<string[]>([]);
  const freeText = question.free_text_allowed !== false;
  const choices = question.options ?? [];
  const answer = [...values, text.trim()].filter(Boolean).join(", ");
  return (
    <section className="terminal-ai-question" aria-label="Вопрос ассистента">
      <h3>Нужен ваш ответ</h3>
      <div className="markdown">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {question.question}
        </ReactMarkdown>
      </div>
      {question.cmd && <pre>{question.cmd}</pre>}
      <div className="terminal-ai-choice-list">
        {choices.map((choice) =>
          question.allow_multiple ? (
            <label key={choice.value} className="terminal-ai-checkbox">
              <input
                type="checkbox"
                checked={values.includes(choice.value)}
                disabled={!connected}
                onChange={(event) =>
                  setValues(
                    event.target.checked
                      ? [...values, choice.value]
                      : values.filter((value) => value !== choice.value),
                  )
                }
              />
              <span>
                {choice.label}
                <small>{choice.description}</small>
              </span>
            </label>
          ) : (
            <Button
              key={choice.value}
              disabled={!connected}
              onClick={() => onReply(choice.value)}
              title={choice.description}
            >
              {choice.label}
            </Button>
          ),
        )}
      </div>
      {freeText && (
        <>
          <label className="sr-only" htmlFor={`reply-${question.q_id}`}>
            Ответ ассистенту
          </label>
          <textarea
            id={`reply-${question.q_id}`}
            value={text}
            rows={2}
            maxLength={4000}
            disabled={!connected}
            placeholder={question.placeholder || "Ваш ответ"}
            onChange={(event) => setText(event.target.value)}
          />
        </>
      )}
      {(freeText || question.allow_multiple) && (
        <Button
          variant="primary"
          size="sm"
          disabled={!connected || !answer}
          onClick={() => onReply(answer)}
        >
          Отправить ответ
        </Button>
      )}
    </section>
  );
}
function AssistantSettings({
  server,
  mode,
  options,
  onChange,
  disabled,
}: {
  server: ServerDetail;
  mode: TerminalAiMode;
  options: TerminalAiOptions;
  onChange: (options: TerminalAiOptions) => void;
  disabled: boolean;
}) {
  const query = useQuery({
    queryKey: ["terminal-ai", "targets"],
    queryFn: ({ signal }) => infrastructureApi.bootstrap(signal),
    enabled: mode === "agent",
  });
  return (
    <fieldset className="terminal-ai-settings" disabled={disabled}>
      <legend>Параметры задачи</legend>
      <label className="terminal-ai-checkbox">
        <input
          type="checkbox"
          checked={options.dryRun}
          onChange={(event) =>
            onChange({ ...options, dryRun: event.target.checked })
          }
        />
        <span>Проверка без исполнения</span>
      </label>
      <Field
        label="Отчёт после завершения"
        htmlFor={`ai-report-mode-${server.id}`}
      >
        <select
          id={`ai-report-mode-${server.id}`}
          value={options.autoReport}
          onChange={(event) =>
            onChange({
              ...options,
              autoReport: event.target.value as TerminalAiOptions["autoReport"],
            })
          }
        >
          <option value="auto">Автоматически</option>
          <option value="on">Всегда</option>
          <option value="off">По запросу</option>
        </select>
      </Field>
      {mode === "agent" && (
        <>
          <Field label="Повышение привилегий" htmlFor={`ai-sudo-${server.id}`}>
            <select
              id={`ai-sudo-${server.id}`}
              value={options.sudoPolicy}
              onChange={(event) =>
                onChange({
                  ...options,
                  sudoPolicy: event.target
                    .value as TerminalAiOptions["sudoPolicy"],
                })
              }
            >
              <option value="disabled">Sudo запрещён</option>
              <option value="ask">Запрашивать каждый раз</option>
              <option value="approved">Разрешить для этой задачи</option>
            </select>
          </Field>
          <fieldset className="terminal-ai-targets">
            <legend>Дополнительные серверы · до 5</legend>
            {(query.data?.servers ?? [])
              .filter((target) => target.id !== server.id)
              .map((target) => (
                <label className="terminal-ai-checkbox" key={target.id}>
                  <input
                    type="checkbox"
                    disabled={
                      disabled ||
                      (!options.extraTargetIds.includes(target.id) &&
                        options.extraTargetIds.length >= 5)
                    }
                    checked={options.extraTargetIds.includes(target.id)}
                    onChange={(event) =>
                      onChange({
                        ...options,
                        extraTargetIds: event.target.checked
                          ? [...options.extraTargetIds, target.id]
                          : options.extraTargetIds.filter(
                              (id) => id !== target.id,
                            ),
                      })
                    }
                  />
                  <span>
                    {target.name}
                    <small>{target.host}</small>
                  </span>
                </label>
              ))}
            <Feedback error={query.error} />
          </fieldset>
        </>
      )}
      <Field
        label="Запрещённые шаблоны команд"
        htmlFor={`ai-blocklist-${server.id}`}
        description="По одному шаблону на строку. Ограничения сервера применяются дополнительно."
      >
        <textarea
          id={`ai-blocklist-${server.id}`}
          rows={2}
          value={options.blockedCommands}
          onChange={(event) =>
            onChange({ ...options, blockedCommands: event.target.value })
          }
        />
      </Field>
    </fieldset>
  );
}
