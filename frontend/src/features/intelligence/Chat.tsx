import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Bot,
  Check,
  FileText,
  MessageSquare,
  Plus,
  RefreshCw,
  Send,
  Square,
  Trash2,
  User,
  X,
} from "lucide-react";
import {
  intelligenceApi as service,
  type ChatAction,
  type ChatArtifact,
  type Details,
} from "@/api/intelligence";
import {
  Button,
  ConfirmDialog,
  Drawer,
  EmptyState,
  ErrorState,
  Field,
  JsonDetails,
  LoadingState,
  PageHeader,
} from "@/components/ui";
import { usePermission } from "@/app/session";
import { formatDate } from "@/lib/utils";
import { IntelStatus, Markdown, record, text, useOperation } from "./common";
import { useLive } from "./useLive";
import { DutyDrawer, RenameChatDrawer } from "./Operations";

export function ActionCard({
  action,
  disabled,
  onUpdate,
}: {
  action: ChatAction;
  disabled: boolean;
  onUpdate: () => void;
}) {
  const op = useOperation();
  const [typed, setTyped] = useState("");
  const [review, setReview] = useState(false);
  const token = text(action.blast_radius?.typed_confirm_token, "");
  const required = action.blast_radius?.typed_confirm_required === true;
  const pending = ["requires_confirmation", "proposed", "pending"].includes(
    action.status,
  );
  const execute = (choice: "confirm" | "cancel") =>
    void op.run(
      () => service.chatAction(action.id, choice, typed),
      "",
      () => {
        setReview(false);
        onUpdate();
      },
    );
  return (
    <article className="intel-action-card">
      <div className="intel-row">
        <span className="intel-avatar">
          <Check size={16} />
        </span>
        <strong>{action.title}</strong>
        <IntelStatus value={action.status} />
      </div>
      <p>{action.description}</p>
      {action.error && <p className="notice notice-danger">{action.error}</p>}
      <JsonDetails data={action.input} label="Параметры действия" />
      {Object.keys(action.blast_radius || {}).length > 0 && (
        <JsonDetails data={action.blast_radius} label="Область воздействия" />
      )}
      {Object.keys(action.result || {}).length > 0 && (
        <JsonDetails data={action.result} label="Результат действия" />
      )}
      {op.feedback}
      {pending && (
        <div className="intel-row">
          <Button
            variant="primary"
            disabled={disabled || op.pending}
            onClick={() => setReview(true)}
          >
            Рассмотреть действие
          </Button>
          <Button
            disabled={disabled}
            loading={op.pending}
            onClick={() => execute("cancel")}
          >
            Отклонить
          </Button>
        </div>
      )}
      <Drawer
        open={review}
        onOpenChange={setReview}
        title={action.title}
        description="Проверьте параметры и область воздействия перед выполнением."
        footer={
          <>
            <Button disabled={op.pending} onClick={() => setReview(false)}>
              Назад
            </Button>
            <Button
              variant={action.risk === "dangerous" ? "danger" : "primary"}
              loading={op.pending}
              disabled={disabled || (required && typed !== token)}
              onClick={() => execute("confirm")}
            >
              Подтвердить действие
            </Button>
          </>
        }
      >
        <div className="intel-form">
          <p>{action.description}</p>
          <div className="notice">
            Уровень риска:{" "}
            {action.risk === "dangerous"
              ? "опасное действие"
              : action.risk === "mutating"
                ? "изменение данных"
                : action.risk}
          </div>
          <pre className="code-block">
            {JSON.stringify(action.input, null, 2)}
          </pre>
          {Object.keys(action.dry_run_preview || {}).length > 0 && (
            <JsonDetails
              data={action.dry_run_preview}
              label="Предварительный результат"
            />
          )}
          {required && (
            <Field
              label={`Введите «${token}» для подтверждения`}
              htmlFor={`confirm-action-${action.id}`}
            >
              <input
                id={`confirm-action-${action.id}`}
                autoComplete="off"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
              />
            </Field>
          )}
          {op.feedback}
        </div>
      </Drawer>
    </article>
  );
}

function ArtifactDrawer({
  artifact,
  chatId,
  onClose,
}: {
  artifact: ChatArtifact;
  chatId: number;
  onClose: () => void;
}) {
  const [content, setContent] = useState(artifact.content);
  const [edit, setEdit] = useState(false);
  const op = useOperation();
  return (
    <Drawer
      open
      onOpenChange={(v) => {
        if (!v) onClose();
      }}
      title={artifact.title}
      description={`Версия ${artifact.version || 1}`}
      wide
      footer={
        <>
          <Button onClick={() => setEdit(!edit)}>
            {edit ? "Просмотр" : "Редактировать"}
          </Button>
          {edit && (
            <Button
              variant="primary"
              loading={op.pending}
              onClick={() =>
                void op.run(
                  () =>
                    service.updateArtifact(chatId, {
                      id: artifact.id,
                      content,
                      bump_version: true,
                    }),
                  "Сохранено",
                  () => setEdit(false),
                )
              }
            >
              Сохранить
            </Button>
          )}
        </>
      }
    >
      {op.feedback}
      {edit ? (
        <Field label="Содержимое материала" htmlFor="chat-artifact">
          <textarea
            id="chat-artifact"
            className="intel-mono intel-artifact-editor"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            maxLength={256000}
          />
        </Field>
      ) : (
        <Markdown>{content}</Markdown>
      )}
    </Drawer>
  );
}

export function ChatPage() {
  const { id } = useParams();
  const chatId = id ? Number(id) : null;
  const nav = useNavigate();
  const client = useQueryClient();
  const op = useOperation();
  const canServers = usePermission("servers");
  const [dutyOpen, setDutyOpen] = useState(false);
  const [rename, setRename] = useState(false);
  const [draft, setDraft] = useState("");
  const [streamBusy, setBusy] = useState<boolean | null>(null);
  const [stream, setStream] = useState("");
  const [assistantId, setAssistantId] = useState<number | null>(null);
  const [phase, setPhase] = useState("");
  const [liveError, setLiveError] = useState("");
  const [artifactsOpen, setArtifactsOpen] = useState(false);
  const [artifact, setArtifact] = useState<ChatArtifact | null>(null);
  const [remove, setRemove] = useState(false);
  const [selectedServer, setSelectedServer] = useState("");
  const [tools, setTools] = useState<
    { id: string; name: string; status: string }[]
  >([]);
  const scroll = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const listQuery = useQuery({
    queryKey: ["intelligence", "chats"],
    queryFn: service.chats,
  });
  const chat = useQuery({
    queryKey: ["intelligence", "chat", chatId],
    queryFn: () => service.chat(chatId!),
    enabled: !!chatId,
  });
  const servers = useQuery({
    queryKey: ["intelligence", "servers"],
    queryFn: service.servers,
    enabled: canServers,
  });
  const artifacts = useQuery({
    queryKey: ["intelligence", "chat-artifacts", chatId],
    queryFn: () => service.chatArtifacts(chatId!),
    enabled: !!chatId && artifactsOpen,
  });
  const busy = streamBusy ?? chat.data?.active_turn?.busy ?? false;
  const refresh = () => {
    void client.invalidateQueries({
      queryKey: ["intelligence", "chat", chatId],
    });
    void client.invalidateQueries({ queryKey: ["intelligence", "chats"] });
  };
  const live = useLive(
    chatId ? `/ws/operator/${chatId}/` : null,
    (event: Details) => {
      const type = text(event.type, "");
      if (type === "ready") {
        setBusy(event.busy === true);
        refresh();
      } else if (type === "turn_snapshot") {
        setBusy(event.busy === true);
        setStream(text(event.assistant_text, ""));
        setAssistantId(
          typeof event.assistant_message_id === "number"
            ? event.assistant_message_id
            : null,
        );
        setPhase(
          event.status === "awaiting_confirm"
            ? "Ожидает согласования"
            : "Выполняется",
        );
        refresh();
      } else if (type === "turn_started") {
        setBusy(true);
        setLiveError("");
        setPhase("Изучает задачу");
      } else if (type === "token") {
        setStream((prev) => prev + text(event.text, ""));
        setPhase("Формирует ответ");
      } else if (type === "thinking") {
        setPhase("Проверяет данные");
      } else if (type === "tool_started") {
        setPhase("Выполняет действие");
        const tool = record(event.tool_call);
        const name = text(
          event.name || event.tool_name || tool.name,
          "Инструмент",
        );
        const toolId = text(
          event.tool_call_id || tool.id,
          `${name}-${Date.now()}`,
        );
        setTools((prev) =>
          [
            ...prev.filter((t) => t.id !== toolId),
            { id: toolId, name, status: "running" },
          ].slice(-12),
        );
      } else if (
        type === "tool_completed" ||
        type === "tool_result" ||
        type === "tool_done"
      ) {
        const toolId = text(event.tool_call_id || event.id, "");
        setTools((prev) =>
          prev.map((t) =>
            !toolId || t.id === toolId
              ? { ...t, status: event.error ? "failed" : "completed" }
              : t,
          ),
        );
      } else if (type === "confirm_required") {
        setBusy(false);
        setPhase("Нужно подтверждение");
        refresh();
      } else if (type === "turn_complete" || type === "turn_done") {
        setBusy(false);
        setPhase("");
        setTools((prev) =>
          prev.map((t) => ({
            ...t,
            status: t.status === "running" ? "unknown" : t.status,
          })),
        );
        void service
          .chat(chatId!)
          .then((data) => {
            client.setQueryData(["intelligence", "chat", chatId], data);
            setStream("");
            setAssistantId(null);
          })
          .catch(() => refresh());
        void client.invalidateQueries({ queryKey: ["intelligence", "chats"] });
      } else if (type === "action_update") {
        refresh();
      } else if (type === "error") {
        setLiveError(text(event.message, "Ошибка выполнения"));
        setBusy(false);
        refresh();
      }
    },
  );

  useEffect(() => {
    if (follow.current && scroll.current)
      scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [stream, chat.data?.messages?.length, tools.length]);
  const send = async () => {
    if (!draft.trim() || busy || op.pending) return;
    const message = draft.trim();
    setLiveError("");
    setStream("");
    setAssistantId(null);
    setTools([]);
    follow.current = true;
    const target = chatId;
    if (!target) {
      setBusy(true);
      setPhase("Ожидание ответа");
      const created = await op.run(async () => {
        const created = await service.createChat(message.slice(0, 80));
        try {
          await service.message(created.id, message);
        } catch (error) {
          nav("/intelligence/chat/" + created.id);
          throw error;
        }
        return created;
      });
      setBusy(false);
      setPhase("");
      if (created) {
        setDraft("");
        nav("/intelligence/chat/" + created.id);
      }
      return;
    }
    if (
      live.state === "connected" &&
      live.send({ type: "chat.message", message })
    ) {
      setDraft("");
      setBusy(true);
      setPhase("Запрос принят");
      await client.invalidateQueries({
        queryKey: ["intelligence", "chat", target],
      });
    } else {
      setBusy(true);
      setPhase("Ожидание ответа");
      await op.run(
        () => service.message(target!, message),
        "",
        () => {
          setDraft("");
          refresh();
        },
      );
      setBusy(false);
      setPhase("");
    }
  };
  const current = chat.data;
  const messages = current?.messages || [];
  const actions = messages.flatMap((m) => m.metadata?.actions || []);
  const lastActionIds = new Set<number>();
  const uniqueActions = actions.filter((a) => {
    if (lastActionIds.has(a.id)) return false;
    lastActionIds.add(a.id);
    return true;
  });
  return (
    <>
      <PageHeader
        eyebrow="Интеллект"
        title="Оператор"
        description="Контекст инфраструктуры, проверяемые действия и история решений."
        actions={
          <>
            <Button onClick={() => setDutyOpen(true)}>Дежурный</Button>
            <Button variant="primary" onClick={() => nav("/intelligence/chat")}>
              <Plus size={15} />
              Новый диалог
            </Button>
          </>
        }
      />
      <div className="intel-chat-layout">
        <aside className="intel-chat-sidebar">
          <div className="intel-chat-sidebar-title">
            <MessageSquare size={16} />
            <strong>Диалоги</strong>
            <span>{listQuery.data?.chats.length || 0}</span>
          </div>
          {listQuery.isPending ? (
            <LoadingState />
          ) : listQuery.error ? (
            <ErrorState error={listQuery.error} />
          ) : listQuery.data?.chats.length ? (
            <nav aria-label="История диалогов">
              {listQuery.data.chats.map((c) => (
                <Link
                  key={c.id}
                  className={chatId === c.id ? "active" : ""}
                  to={`/intelligence/chat/${c.id}`}
                >
                  <span>{c.title || "Новый диалог"}</span>
                  <small>{formatDate(c.updated_at)}</small>
                </Link>
              ))}
            </nav>
          ) : (
            <p className="muted intel-pad">
              Здесь появится история ваших диалогов.
            </p>
          )}
        </aside>
        <section className="intel-chat-main" aria-label="Диалог с оператором">
          <div className="intel-chat-heading">
            <strong>{current?.title || "Новая задача"}</strong>
            {current && (
              <Button variant="ghost" size="sm" onClick={() => setRename(true)}>
                Переименовать
              </Button>
            )}
            <div className="intel-row">
              {chatId && (
                <>
                  <IntelStatus value={live.state} />
                  {live.state !== "connected" && (
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label="Переподключить диалог"
                      onClick={live.reconnect}
                    >
                      <RefreshCw size={15} />
                    </Button>
                  )}
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="Материалы диалога"
                    onClick={() => setArtifactsOpen(true)}
                  >
                    <FileText size={17} />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="Удалить диалог"
                    disabled={busy}
                    onClick={() => setRemove(true)}
                  >
                    <Trash2 size={16} />
                  </Button>
                </>
              )}
            </div>
          </div>
          <div
            className="intel-chat-scroll"
            ref={scroll}
            onScroll={() => {
              const el = scroll.current;
              if (el)
                follow.current =
                  el.scrollHeight - el.scrollTop - el.clientHeight < 100;
            }}
          >
            {chat.isPending && chatId ? (
              <LoadingState />
            ) : chat.error ? (
              <ErrorState
                error={chat.error}
                retry={() => void chat.refetch()}
              />
            ) : !messages.length && !stream ? (
              <EmptyState
                icon={<Bot size={30} />}
                title="Что нужно решить?"
                description="Опишите задачу. Оператор проверит доступный контекст и запросит согласование важных действий."
              />
            ) : (
              messages.map((m) => (
                <article
                  key={m.id}
                  className={`intel-message intel-message-${m.role}`}
                >
                  <span className="intel-message-icon">
                    {m.role === "user" ? <User size={16} /> : <Bot size={16} />}
                  </span>
                  <div>
                    <div className="intel-message-meta">
                      <strong>
                        {m.role === "user"
                          ? "Вы"
                          : m.role === "assistant"
                            ? "Оператор"
                            : "Система"}
                      </strong>
                      <time>{formatDate(m.created_at)}</time>
                    </div>
                    <Markdown>
                      {m.id === assistantId && stream ? stream : m.content}
                    </Markdown>
                  </div>
                </article>
              ))
            )}
            {stream && !messages.some((m) => m.id === assistantId) && (
              <article className="intel-message intel-message-assistant">
                <span className="intel-message-icon">
                  <Bot size={16} />
                </span>
                <div>
                  <div className="intel-message-meta">
                    <strong>Оператор</strong>
                  </div>
                  <Markdown>{stream}</Markdown>
                  {busy && <span className="intel-stream-dot" />}
                </div>
              </article>
            )}
            {tools.length > 0 && (
              <details className="intel-chat-tools">
                <summary>Действия оператора · {tools.length}</summary>
                {tools.map((t) => (
                  <div className="intel-row" key={t.id}>
                    <span>{t.name}</span>
                    <IntelStatus value={t.status} />
                  </div>
                ))}
              </details>
            )}
            {uniqueActions.map((a) => (
              <ActionCard
                key={a.id}
                action={a}
                disabled={busy}
                onUpdate={refresh}
              />
            ))}
            {busy && (
              <div className="intel-chat-progress" role="status">
                <span className="intel-stream-dot" />
                {phase || "Выполняет задачу"}
              </div>
            )}
          </div>
          <div className="intel-composer">
            {op.feedback}
            {liveError && (
              <div className="notice notice-danger" role="alert">
                {liveError}
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label="Закрыть сообщение"
                  onClick={() => setLiveError("")}
                >
                  <X size={14} />
                </Button>
              </div>
            )}
            {canServers && servers.data && (
              <div className="intel-composer-context">
                <label htmlFor="chat-server">Контекст @</label>
                <select
                  id="chat-server"
                  value={selectedServer}
                  onChange={(e) => {
                    const server = servers.data.servers.find(
                      (s) => s.id === Number(e.target.value),
                    );
                    if (server) {
                      setSelectedServer(e.target.value);
                      setDraft(
                        (prev) => `${prev}${prev ? " " : ""}@${server.name} `,
                      );
                    }
                  }}
                >
                  <option value="">Выбрать точный сервер</option>
                  {servers.data.servers.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} · {s.host}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void send();
              }}
            >
              <textarea
                aria-label="Сообщение оператору"
                placeholder="Опишите задачу или задайте вопрос…"
                rows={3}
                maxLength={12000}
                value={draft}
                disabled={op.pending}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    void send();
                  }
                }}
              />
              <div className="intel-composer-footer">
                <small>
                  {busy
                    ? "Работа продолжается при переходе в другой раздел."
                    : `${draft.length.toLocaleString("ru")} / 12 000 · Ctrl + Enter`}
                </small>
                {busy ? (
                  <Button
                    variant="danger"
                    disabled={live.state !== "connected"}
                    onClick={() => live.send({ type: "turn.stop" })}
                  >
                    <Square size={14} />
                    Остановить
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    variant="primary"
                    disabled={!draft.trim()}
                    loading={op.pending}
                  >
                    <Send size={16} />
                    Отправить
                  </Button>
                )}
              </div>
            </form>
          </div>
        </section>
      </div>
      <Drawer
        open={artifactsOpen}
        onOpenChange={setArtifactsOpen}
        title="Материалы диалога"
        description="Документы и результаты, сохранённые в этой задаче."
      >
        {artifacts.isPending ? (
          <LoadingState />
        ) : artifacts.error ? (
          <ErrorState error={artifacts.error} />
        ) : artifacts.data?.artifacts.length ? (
          <div className="intel-form">
            {artifacts.data.artifacts.map((a) => (
              <Button key={a.id} onClick={() => setArtifact(a)}>
                <FileText size={17} />
                {a.title}
              </Button>
            ))}
          </div>
        ) : (
          <EmptyState title="Материалов пока нет" />
        )}
      </Drawer>
      {artifact && chatId && (
        <ArtifactDrawer
          artifact={artifact}
          chatId={chatId}
          onClose={() => setArtifact(null)}
        />
      )}
      {dutyOpen && <DutyDrawer onClose={() => setDutyOpen(false)} />}{" "}
      {rename && current && (
        <RenameChatDrawer chat={current} onClose={() => setRename(false)} />
      )}
      <ConfirmDialog
        open={remove}
        onOpenChange={setRemove}
        title="Удалить диалог?"
        description="Переписка и материалы этого диалога будут удалены."
        confirmLabel="Удалить"
        pending={op.pending}
        onConfirm={() =>
          chatId &&
          void op.run(
            () => service.deleteChat(chatId),
            "",
            () => {
              setRemove(false);
              nav("/intelligence/chat");
            },
          )
        }
      />
    </>
  );
}
