import { useState } from "react";
import { MemoryBulkDrawer } from "./Operations";
import { SharedUsers } from "./SharedUsers";
import { useQuery } from "@tanstack/react-query";
import {
  Cable,
  Database,
  FlaskConical,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import {
  intelligenceApi as service,
  type Details,
  type MCP,
  type MemorySnapshot,
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
  PageHeader,
  Panel,
  Tabs,
} from "@/components/ui";
import { usePermission, useSession } from "@/app/session";
import { formatDate } from "@/lib/utils";
import {
  DetailCards,
  DetailRows,
  IntelStatus,
  Markdown,
  list,
  record,
  text,
  useOperation,
} from "./common";

function McpEditor({
  mcp,
  template,
  onClose,
}: {
  mcp: MCP | null;
  template?: Details;
  onClose: () => void;
}) {
  const op = useOperation();
  const [name, setName] = useState(mcp?.name || text(template?.name, ""));
  const [description, setDescription] = useState(
    mcp?.description || text(template?.description, ""),
  );
  const [transport, setTransport] = useState(
    mcp?.transport || text(template?.transport, "stdio"),
  );
  const [command, setCommand] = useState(
    mcp?.command || text(template?.command, ""),
  );
  const [url, setUrl] = useState(mcp?.url || text(template?.url, ""));
  const [args, setArgs] = useState(
    (
      mcp?.args ||
      (Array.isArray(template?.args) ? template.args.map(String) : [])
    ).join("\n"),
  );
  const [env, setEnv] = useState(
    JSON.stringify(mcp?.env || template?.env || {}, null, 2),
  );
  const [headers, setHeaders] = useState(
    JSON.stringify(mcp?.headers || {}, null, 2),
  );
  const [sharedUsers, setSharedUsers] = useState(mcp?.shared_user_ids || []);
  const [shared, setShared] = useState("unchanged");
  const parse = (value: string) => {
    const result: unknown = JSON.parse(value);
    if (!result || typeof result !== "object" || Array.isArray(result))
      throw new Error("Ожидается объект с именами и значениями.");
    return result;
  };
  return (
    <Drawer
      open
      onOpenChange={(v) => {
        if (!v && !op.pending) onClose();
      }}
      title={mcp ? "Подключение MCP" : "Новое подключение MCP"}
      description="Укажите способ подключения и проверьте доступность сервера."
      footer={
        <>
          <Button onClick={onClose} disabled={op.pending}>
            Отмена
          </Button>
          <Button
            variant="primary"
            loading={op.pending}
            disabled={
              !name.trim() ||
              (transport === "sse" ? !url.trim() : !command.trim())
            }
            onClick={() =>
              void op.run(
                () =>
                  service.saveMcp(mcp?.id, {
                    name: name.trim(),
                    description,
                    transport,
                    command,
                    args: args.split("\n").filter(Boolean),
                    url,
                    env: parse(env),
                    headers: parse(headers),
                    ...(mcp?.can_share ? { shared_user_ids: sharedUsers } : {}),
                    ...(mcp?.can_share && shared !== "unchanged"
                      ? { is_shared: shared === "enable" }
                      : {}),
                  }),
                "",
                onClose,
              )
            }
          >
            Сохранить
          </Button>
        </>
      }
    >
      <div className="intel-form">
        {op.feedback}
        {mcp?.secret_env_keys?.length ? (
          <p className="muted">
            Секреты из защищённого хранилища: {mcp.secret_env_keys.join(", ")}.
            Значения не выводятся.
          </p>
        ) : null}
        <Field label="Название" htmlFor="mcp-name">
          <input
            id="mcp-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
          />
        </Field>
        {mcp?.can_share && (
          <SharedUsers ids={sharedUsers} onChange={setSharedUsers} />
        )}
        <Field label="Описание" htmlFor="mcp-description">
          <textarea
            id="mcp-description"
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <Field label="Способ подключения" htmlFor="mcp-transport">
          <select
            id="mcp-transport"
            value={transport}
            onChange={(e) => setTransport(e.target.value)}
          >
            <option value="stdio">Локальный процесс (stdio)</option>
            <option value="sse">Сетевой сервер (SSE)</option>
          </select>
        </Field>
        {transport === "stdio" ? (
          <>
            <Field label="Команда запуска" htmlFor="mcp-command">
              <input
                id="mcp-command"
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                className="intel-mono"
              />
            </Field>
            <Field label="Аргументы — по одному в строке" htmlFor="mcp-args">
              <textarea
                id="mcp-args"
                rows={4}
                value={args}
                onChange={(e) => setArgs(e.target.value)}
                className="intel-mono"
              />
            </Field>
            <Field label="Переменные окружения (JSON)" htmlFor="mcp-env">
              <textarea
                id="mcp-env"
                rows={5}
                value={env}
                onChange={(e) => setEnv(e.target.value)}
                className="intel-mono"
                autoComplete="off"
                spellCheck={false}
              />
            </Field>
          </>
        ) : (
          <>
            <Field label="Адрес сервера" htmlFor="mcp-url">
              <input
                id="mcp-url"
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </Field>
            <Field label="Заголовки авторизации (JSON)" htmlFor="mcp-headers">
              <textarea
                id="mcp-headers"
                rows={5}
                value={headers}
                onChange={(e) => setHeaders(e.target.value)}
                className="intel-mono"
                autoComplete="off"
                spellCheck={false}
              />
            </Field>
          </>
        )}
        {mcp?.can_share && (
          <Field
            label="Общий доступ"
            htmlFor="mcp-sharing"
            description="Персональные разрешения сохраняются отдельно. Общий доступ открывает подключение всем пользователям с правом MCP."
          >
            <select
              id="mcp-sharing"
              value={shared}
              onChange={(e) => setShared(e.target.value)}
            >
              <option value="unchanged">Оставить без изменений</option>
              <option value="enable">Включить общий доступ</option>
              <option value="disable">Отключить общий доступ</option>
            </select>
          </Field>
        )}
      </div>
    </Drawer>
  );
}

export function McpPage() {
  const op = useOperation();
  const [editor, setEditor] = useState<{
    mcp: MCP | null;
    template?: Details;
  } | null>(null);
  const [selected, setSelected] = useState<MCP | null>(null);
  const [remove, setRemove] = useState<MCP | null>(null);
  const [catalog, setCatalog] = useState(false);
  const [inspection, setInspection] = useState<Details | null>(null);
  const q = useQuery({
    queryKey: ["intelligence", "mcp"],
    queryFn: service.mcps,
  });
  const templates = useQuery({
    queryKey: ["intelligence", "mcp-templates"],
    queryFn: service.mcpTemplates,
    enabled: catalog,
  });
  const inspect = (mcp: MCP) => {
    setSelected(mcp);
    setInspection(null);
    void op.run(() => service.mcpTools(mcp.id), "", setInspection);
  };
  return (
    <>
      <PageHeader
        eyebrow="Интеллект"
        title="Подключения MCP"
        description="Управляемый доступ агентов к инструментам и внешним системам."
        actions={
          <>
            <Button onClick={() => setCatalog(true)}>Каталог шаблонов</Button>
            <Button variant="primary" onClick={() => setEditor({ mcp: null })}>
              <Plus size={16} />
              Подключить MCP
            </Button>
          </>
        }
      />
      {op.feedback}
      <Panel>
        {q.isPending ? (
          <LoadingState />
        ) : q.error ? (
          <ErrorState error={q.error} retry={() => void q.refetch()} />
        ) : (
          <DataTable
            rows={q.data || []}
            rowKey={(m) => m.id}
            searchValue={(m) => `${m.name} ${m.description}`}
            emptyTitle="Подключите инструменты команды"
            emptyDescription="Добавьте сервер MCP, чтобы агенты могли работать с разрешёнными источниками и сервисами."
            emptyAction={
              <Button
                variant="primary"
                onClick={() => setEditor({ mcp: null })}
              >
                Подключить MCP
              </Button>
            }
            columns={[
              {
                key: "name",
                label: "Подключение",
                sortValue: (m) => m.name,
                render: (m) => (
                  <div className="intel-entity-link">
                    <span className="intel-avatar">
                      <Cable size={18} />
                    </span>
                    <span>
                      <strong>{m.name}</strong>
                      <small>{m.description}</small>
                    </span>
                  </div>
                ),
              },
              {
                key: "transport",
                label: "Тип",
                render: (m) =>
                  m.transport === "stdio"
                    ? "Локальный процесс"
                    : "Сетевой сервер",
              },
              {
                key: "status",
                label: "Проверка",
                render: (m) => (
                  <IntelStatus
                    value={
                      m.last_test_ok === null
                        ? "untested"
                        : m.last_test_ok
                          ? "connected"
                          : "failed"
                    }
                  />
                ),
              },
              {
                key: "owner",
                label: "Доступ",
                render: (m) => (
                  <span>
                    {m.owner_username}
                    <small className="intel-block muted">
                      {m.can_edit ? "Управление" : "Только чтение"}
                    </small>
                  </span>
                ),
              },
              {
                key: "date",
                label: "Проверено",
                render: (m) => formatDate(m.last_test_at),
              },
              {
                key: "actions",
                label: "Действия",
                render: (m) => (
                  <div className="intel-row">
                    {m.can_edit && (
                      <>
                        <Button
                          size="sm"
                          loading={op.pending}
                          onClick={() =>
                            void op.run(async () => {
                              const result = await service.testMcp(m.id);
                              if (!result.ok)
                                throw new Error(
                                  result.error || "Подключение не установлено",
                                );
                              return result;
                            }, "Подключение проверено")
                          }
                        >
                          <FlaskConical size={14} />
                          Проверить
                        </Button>
                        <Button size="sm" onClick={() => setEditor({ mcp: m })}>
                          Настроить
                        </Button>
                      </>
                    )}
                    <Button size="sm" onClick={() => inspect(m)}>
                      Инструменты
                    </Button>
                    {m.can_edit && (
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={`Удалить ${m.name}`}
                        onClick={() => setRemove(m)}
                      >
                        <Trash2 size={15} />
                      </Button>
                    )}
                  </div>
                ),
              },
            ]}
          />
        )}
      </Panel>
      {editor && <McpEditor {...editor} onClose={() => setEditor(null)} />}
      <Drawer
        open={catalog}
        onOpenChange={setCatalog}
        title="Шаблоны подключений"
        description="Шаблон заполняет параметры. Фактический доступ проверяется после сохранения."
      >
        {templates.isPending ? (
          <LoadingState />
        ) : templates.error ? (
          <ErrorState error={templates.error} />
        ) : (
          <div className="intel-form">
            {templates.data?.map((t, i) => (
              <article className="intel-evidence" key={text(t.id, String(i))}>
                <strong>{text(t.name)}</strong>
                <p>{text(t.description, "")}</p>
                <Button
                  onClick={() => {
                    setCatalog(false);
                    setEditor({ mcp: null, template: t });
                  }}
                >
                  Использовать шаблон
                </Button>
              </article>
            ))}
          </div>
        )}
      </Drawer>
      <Drawer
        open={!!selected}
        onOpenChange={(v) => {
          if (!v) setSelected(null);
        }}
        title={selected ? `Инструменты · ${selected.name}` : "Инструменты"}
        description="Результат последней проверки возможностей сервера."
      >
        {op.pending ? (
          <LoadingState label="Проверка возможностей…" />
        ) : op.error ? (
          <ErrorState error={op.error} />
        ) : inspection ? (
          <>
            <DetailCards
              items={list(inspection.tools)}
              empty="Сервер не вернул инструменты"
            />
            {list(inspection.resources).length > 0 && (
              <DetailCards items={list(inspection.resources)} />
            )}
            <JsonDetails
              data={inspection}
              label="Полный контракт возможностей"
            />
          </>
        ) : null}
      </Drawer>
      <ConfirmDialog
        open={!!remove}
        onOpenChange={(v) => {
          if (!v) setRemove(null);
        }}
        title="Удалить подключение?"
        description={`Агенты потеряют доступ к «${remove?.name}». Сам внешний сервис останется доступен.`}
        pending={op.pending}
        confirmLabel="Удалить"
        onConfirm={() =>
          remove &&
          void op.run(
            () => service.deleteMcp(remove.id),
            "Подключение удалено",
            () => setRemove(null),
          )
        }
      />
    </>
  );
}

function MemoryEditor({
  snapshot,
  serverId,
  onClose,
}: {
  snapshot: MemorySnapshot;
  serverId: number;
  onClose: () => void;
}) {
  const op = useOperation();
  const [title, setTitle] = useState(snapshot.title);
  const [content, setContent] = useState(snapshot.content);
  return (
    <Drawer
      open
      onOpenChange={(v) => {
        if (!v) onClose();
      }}
      title="Редактировать сведения"
      wide
      footer={
        <>
          <Button onClick={onClose}>Отмена</Button>
          <Button
            variant="primary"
            loading={op.pending}
            disabled={!title.trim()}
            onClick={() =>
              void op.run(
                () =>
                  service.memoryAction(
                    serverId,
                    `snapshots/${snapshot.id}/update`,
                    { title, content },
                  ),
                "",
                onClose,
              )
            }
          >
            Сохранить
          </Button>
        </>
      }
    >
      <div className="intel-form">
        {op.feedback}
        <Field label="Название" htmlFor="memory-title">
          <input
            id="memory-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
          />
        </Field>
        <Field label="Содержание" htmlFor="memory-content">
          <textarea
            id="memory-content"
            rows={16}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            maxLength={8000}
          />
        </Field>
        <small className="muted">{content.length} / 8 000</small>
      </div>
    </Drawer>
  );
}

function MemoryPolicy({
  serverId,
  policy,
  onClose,
}: {
  serverId: number;
  policy: Details;
  onClose: () => void;
}) {
  const op = useOperation();
  const [draft, setDraft] = useState(policy);
  const change = (key: string, value: unknown) =>
    setDraft({ ...draft, [key]: value });
  return (
    <Drawer
      open
      onOpenChange={(v) => {
        if (!v) onClose();
      }}
      title="Политика памяти"
      description="Эти параметры применяются к памяти всех ваших серверов."
      footer={
        <Button
          variant="primary"
          loading={op.pending}
          onClick={() =>
            void op.run(
              () => service.memoryAction(serverId, "policy", draft),
              "",
              onClose,
            )
          }
        >
          Сохранить политику
        </Button>
      }
    >
      <div className="intel-form">
        {op.feedback}
        <Field label="Обработка памяти" htmlFor="memory-mode">
          <select
            id="memory-mode"
            value={text(draft.dream_mode, "hybrid")}
            onChange={(e) => change("dream_mode", e.target.value)}
          >
            <option value="heuristic">Правила</option>
            <option value="nightly_llm">Ночной анализ AI</option>
            <option value="hybrid">Правила и AI</option>
          </select>
        </Field>
        {[
          {
            key: "nearline_event_threshold",
            label: "Событий до обработки",
            min: 2,
            max: 50,
          },
          {
            key: "sleep_start_hour",
            label: "Начало ночного окна",
            min: 0,
            max: 23,
          },
          {
            key: "sleep_end_hour",
            label: "Конец ночного окна",
            min: 0,
            max: 23,
          },
          {
            key: "raw_event_retention_days",
            label: "Хранить исходные события, дней",
            min: 7,
            max: 365,
          },
          {
            key: "episode_retention_days",
            label: "Хранить эпизоды, дней",
            min: 14,
            max: 365,
          },
        ].map((f) => (
          <Field key={f.key} label={f.label} htmlFor={`policy-${f.key}`}>
            <input
              id={`policy-${f.key}`}
              type="number"
              min={f.min}
              max={f.max}
              value={Number(draft[f.key] || f.min)}
              onChange={(e) => change(f.key, Number(e.target.value))}
            />
          </Field>
        ))}
        <label className="intel-check">
          <input
            type="checkbox"
            checked={draft.is_enabled === true}
            onChange={(e) => change("is_enabled", e.target.checked)}
          />
          Память включена
        </label>
        <label className="intel-check">
          <input
            type="checkbox"
            checked={draft.human_habits_capture_enabled === true}
            onChange={(e) =>
              change("human_habits_capture_enabled", e.target.checked)
            }
          />
          Сохранять рабочие привычки
        </label>
      </div>
    </Drawer>
  );
}

export function MemoryPage() {
  const [bulk, setBulk] = useState(false);
  const { user } = useSession();
  const skills = usePermission("studio_skills");
  const op = useOperation();
  const [serverId, setServerId] = useState(0);
  const [tab, setTab] = useState("knowledge");
  const [query, setQuery] = useState("");
  const [searchResult, setSearchResult] = useState<Details[] | null>(null);
  const [selected, setSelected] = useState<MemorySnapshot | null>(null);
  const [editor, setEditor] = useState<MemorySnapshot | null>(null);
  const [policy, setPolicy] = useState(false);
  const [confirmation, setConfirmation] = useState<{
    action: string;
    title: string;
    description: string;
  } | null>(null);
  const servers = useQuery({
    queryKey: ["intelligence", "servers"],
    queryFn: service.servers,
  });
  const owned = servers.data?.servers.filter((s) => s.can_edit) || [];
  const effective = serverId || owned[0]?.id || 0;
  const q = useQuery({
    queryKey: ["intelligence", "memory", effective],
    queryFn: () => service.memory(effective),
    enabled: !!effective,
  });
  const overview = useQuery({
    queryKey: ["intelligence", "memory-overview", effective],
    queryFn: () => service.memoryOverview(effective),
    enabled: !!effective && !!user?.is_staff && tab === "management",
  });
  return (
    <>
      <PageHeader
        eyebrow="Интеллект"
        title="Память инфраструктуры"
        description="Сведения о серверах, выводы прошлых задач и проверяемые источники."
        actions={
          <Button
            disabled={!q.data?.items.length}
            onClick={() => setBulk(true)}
          >
            Удалить несколько сведений
          </Button>
        }
      />
      <div className="intel-scope-bar">
        <Database size={19} />
        <label htmlFor="memory-server">Сервер</label>
        <select
          id="memory-server"
          value={effective}
          onChange={(e) => {
            setServerId(Number(e.target.value));
            setSearchResult(null);
            setSelected(null);
            setBulk(false);
            setEditor(null);
            setPolicy(false);
            setConfirmation(null);
          }}
        >
          {owned.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} · {s.host}
            </option>
          ))}
        </select>
      </div>
      {op.feedback}
      {servers.isPending ? (
        <LoadingState />
      ) : servers.error ? (
        <ErrorState error={servers.error} />
      ) : !owned.length ? (
        <EmptyState
          title="Нет серверов для управления памятью"
          description="Сведения доступны владельцу сервера. Добавьте сервер в разделе инфраструктуры."
          icon={<Database size={26} />}
        />
      ) : (
        <>
          <Tabs
            value={tab}
            onChange={setTab}
            items={[
              { value: "knowledge", label: "Сведения" },
              { value: "search", label: "Поиск по памяти" },
              ...(user?.is_staff
                ? [{ value: "management", label: "Обработка и политика" }]
                : []),
            ]}
          />
          {tab === "knowledge" ? (
            <Panel>
              {q.isPending ? (
                <LoadingState />
              ) : q.error ? (
                <ErrorState error={q.error} />
              ) : (
                <DataTable
                  rows={q.data?.items || []}
                  rowKey={(s) => s.id}
                  searchValue={(s) => `${s.title} ${s.content}`}
                  emptyTitle="Память этого сервера пока пуста"
                  emptyDescription="Проверенные сведения появятся после работы с сервером и выполнения задач."
                  columns={[
                    {
                      key: "title",
                      label: "Сведение",
                      render: (s) => (
                        <button
                          className="intel-link-button"
                          onClick={() => setSelected(s)}
                        >
                          <strong>{s.title}</strong>
                        </button>
                      ),
                    },
                    {
                      key: "kind",
                      label: "Источник",
                      render: (s) => <IntelStatus value={s.kind} />,
                    },
                    {
                      key: "confidence",
                      label: "Уверенность",
                      sortValue: (s) => s.confidence,
                      render: (s) => `${Math.round(s.confidence * 100)}%`,
                    },
                    {
                      key: "freshness",
                      label: "Актуальность",
                      sortValue: (s) => s.freshness,
                      render: (s) => `${Math.round(s.freshness * 100)}%`,
                    },
                    {
                      key: "updated",
                      label: "Обновлено",
                      render: (s) => formatDate(s.updated_at),
                    },
                    {
                      key: "edit",
                      label: "",
                      render: (s) => (
                        <Button size="sm" onClick={() => setEditor(s)}>
                          Изменить
                        </Button>
                      ),
                    },
                  ]}
                />
              )}
            </Panel>
          ) : tab === "search" ? (
            <Panel title="Найти сведения">
              <div className="intel-pad intel-form">
                <form
                  className="intel-row"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void op.run(
                      () =>
                        service.memoryAction(effective, "search", {
                          query,
                          top_k: 10,
                          char_budget: 8000,
                        }),
                      "",
                      (result) => setSearchResult(list(result.items)),
                    );
                  }}
                >
                  <input
                    className="intel-grow"
                    aria-label="Поисковый запрос"
                    placeholder="Например, как настроено резервное копирование"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    maxLength={1000}
                  />
                  <Button
                    type="submit"
                    variant="primary"
                    disabled={!query.trim()}
                    loading={op.pending}
                  >
                    <Search size={16} />
                    Найти
                  </Button>
                </form>
                {searchResult !== null && (
                  <DetailCards
                    items={searchResult}
                    empty="Подходящих сведений не найдено"
                  />
                )}
              </div>
            </Panel>
          ) : overview.isPending ? (
            <LoadingState />
          ) : overview.error ? (
            <ErrorState error={overview.error} />
          ) : (
            overview.data && (
              <>
                <Panel
                  title="Обработка памяти"
                  actions={
                    <Button onClick={() => setPolicy(true)}>
                      Настроить политику
                    </Button>
                  }
                >
                  <div className="intel-pad intel-form">
                    <DetailRows
                      items={[
                        {
                          label: "Режим",
                          value: text(record(overview.data.policy).dream_mode),
                        },
                        {
                          label: "Рабочий процесс",
                          value: (
                            <IntelStatus
                              value={text(
                                record(overview.data.daemon_state).status,
                                "unknown",
                              )}
                            />
                          ),
                        },
                        {
                          label: "Включена",
                          value: record(overview.data.policy).is_enabled
                            ? "Да"
                            : "Нет",
                        },
                      ]}
                    />
                    <div className="intel-row">
                      <Button
                        loading={op.pending}
                        onClick={() =>
                          setConfirmation({
                            action: "run-dreams",
                            title: "Обработать накопленную память?",
                            description:
                              "Запустится объединение сведений и анализ накопленных событий.",
                          })
                        }
                      >
                        Обработать сейчас
                      </Button>
                      <Button
                        variant="danger"
                        onClick={() =>
                          setConfirmation({
                            action: "purge",
                            title: "Очистить память сервера?",
                            description:
                              "Будут удалены накопленные сведения и связанные производные данные.",
                          })
                        }
                      >
                        Очистить память
                      </Button>
                    </div>
                  </div>
                </Panel>
                <Panel title="Кандидаты и повторяющиеся сценарии">
                  <DetailCards
                    items={[
                      ...list(overview.data.patterns),
                      ...list(overview.data.automation_candidates),
                      ...list(overview.data.skill_drafts),
                    ]}
                  />
                </Panel>
                <Panel title="Рабочие процессы">
                  <JsonDetails
                    data={overview.data.worker_states}
                    label="Состояние обработки"
                  />
                </Panel>
              </>
            )
          )}
        </>
      )}
      <Drawer
        open={!!selected}
        onOpenChange={(v) => {
          if (!v) setSelected(null);
        }}
        title={selected?.title || "Сведение"}
        wide
        footer={
          selected && (
            <>
              <Button
                onClick={() => {
                  setEditor(selected);
                  setSelected(null);
                }}
              >
                Изменить
              </Button>
              <Button
                variant="danger"
                onClick={() =>
                  setConfirmation({
                    action: `snapshots/${selected.id}/delete`,
                    title: "Удалить сведение?",
                    description:
                      "Сведение будет удалено. Удаление профиля сервера также очищает связанную AI-память.",
                  })
                }
              >
                Удалить
              </Button>
              {user?.is_staff && (
                <>
                  <Button
                    onClick={() =>
                      void op.run(
                        () =>
                          service.memoryAction(
                            effective,
                            `snapshots/${selected.id}/archive`,
                          ),
                        "Сведение архивировано",
                        () => setSelected(null),
                      )
                    }
                  >
                    В архив
                  </Button>
                  <Button
                    onClick={() =>
                      void op.run(
                        () =>
                          service.memoryAction(
                            effective,
                            `snapshots/${selected.id}/promote-note`,
                          ),
                        "Заметка создана",
                      )
                    }
                  >
                    В заметку
                  </Button>
                  {skills && selected.kind === "skill_draft" && (
                    <Button
                      onClick={() =>
                        void op.run(
                          () =>
                            service.memoryAction(
                              effective,
                              `snapshots/${selected.id}/promote-skill`,
                            ),
                          "Навык создан",
                        )
                      }
                    >
                      Создать навык
                    </Button>
                  )}
                </>
              )}
            </>
          )
        }
      >
        {selected && (
          <>
            <div className="intel-row">
              <IntelStatus value={selected.kind} />
              <span className="muted">
                Версия {selected.version} · {formatDate(selected.updated_at)}
              </span>
            </div>
            <Markdown>{selected.content}</Markdown>
          </>
        )}
      </Drawer>
      {editor && (
        <MemoryEditor
          snapshot={editor}
          serverId={effective}
          onClose={() => setEditor(null)}
        />
      )}{" "}
      {policy && overview.data && (
        <MemoryPolicy
          serverId={effective}
          policy={record(overview.data.policy)}
          onClose={() => setPolicy(false)}
        />
      )}
      {bulk && (
        <MemoryBulkDrawer
          serverId={effective}
          serverName={
            owned.find((s) => s.id === effective)?.name || String(effective)
          }
          items={q.data?.items || []}
          onClose={() => {
            setBulk(false);
            setSelected(null);
            setSearchResult(null);
          }}
        />
      )}
      <ConfirmDialog
        open={!!confirmation}
        onOpenChange={(v) => {
          if (!v) setConfirmation(null);
        }}
        title={confirmation?.title || ""}
        description={confirmation?.description}
        pending={op.pending}
        confirmLabel="Продолжить"
        typedText={
          confirmation?.action === "purge"
            ? owned.find((s) => s.id === effective)?.name
            : undefined
        }
        onConfirm={() =>
          confirmation &&
          void op.run(
            () =>
              service.memoryAction(
                effective,
                confirmation.action,
                confirmation.action === "run-dreams"
                  ? { job_kind: "hybrid" }
                  : {},
              ),
            "Операция выполнена",
            () => {
              setConfirmation(null);
              setSelected(null);
            },
          )
        }
      />
    </>
  );
}
