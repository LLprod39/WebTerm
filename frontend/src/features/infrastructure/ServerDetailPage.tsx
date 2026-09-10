import { useState, type FormEvent } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  useIsMutating,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import * as Dropdown from "@radix-ui/react-dropdown-menu";
import {
  ArrowLeft,
  Check,
  Copy,
  Pencil,
  Play,
  Terminal,
  Trash2,
  ChevronDown,
} from "lucide-react";
import { infrastructureApi, type ServerDetail } from "@/api/infrastructure";
import { serverWorkspaceApi } from "@/api/server-workspace";
import {
  Button,
  ConfirmDialog,
  ErrorState,
  Feedback,
  Field,
  LoadingState,
  PageHeader,
  Panel,
  Tabs,
} from "@/components/ui";
import { ServerForm } from "./ServerForm";
import { ServerFiles } from "./ServerFiles";
import { ServerSecurity } from "./ServerSecurity";
import { ServerAccess } from "./ServerAccess";
import { ServerOperations } from "./ServerOperations";
import { ServerKnowledge } from "./ServerKnowledge";
import { ServerSnapshots } from "./ServerSnapshots";
import { useSession } from "@/app/session";
function ServerCommand({ server }: { server: ServerDetail }) {
  const [command, setCommand] = useState("");
  const [confirm, setConfirm] = useState(false);
  const run = useMutation({
    mutationKey: ["server-workspace", server.id],
    mutationFn: (submitted: string) =>
      serverWorkspaceApi.execute(server.id, submitted),
    onSuccess: () => setConfirm(false),
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    if (
      server.capabilities.execute_command &&
      command.trim() &&
      !run.isPending
    ) {
      run.reset();
      setConfirm(true);
    }
  }
  return (
    <Panel
      title="Выполнить команду"
      description="Команда выполнится по SSH на этом сервере."
    >
      <form className="section-body stack" onSubmit={submit}>
        <Field label="Команда" htmlFor="server-command">
          <textarea
            id="server-command"
            className="mono"
            required
            disabled={run.isPending}
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            placeholder="Введите команду для выполнения"
          />
        </Field>
        <Button
          type="submit"
          disabled={!server.capabilities.execute_command || !command.trim()}
          loading={run.isPending}
          variant="primary"
        >
          <Play size={14} />
          Проверить и выполнить
        </Button>
        <Feedback error={run.error} />
        {run.data && (
          <>
            <p className="muted text-sm">
              Результат команды <code>{run.variables}</code>
            </p>
            <span className="muted text-sm">
              Код завершения: {run.data.output.exit_code ?? "—"}
            </span>
            <pre className="code-block">
              {run.data.output.stdout}
              {run.data.output.stderr}
            </pre>
          </>
        )}
      </form>
      <ConfirmDialog
        open={confirm}
        onOpenChange={(open) => {
          if (!run.isPending) setConfirm(open);
        }}
        title={`Выполнить на ${server.name}?`}
        description={
          <>
            <p className="mono text-sm">
              {server.username}@{server.host}:{server.port}
            </p>
            <pre className="code-block">{command}</pre>
            <Feedback error={run.error} />
          </>
        }
        onConfirm={() => {
          if (!run.isPending) run.mutate(command);
        }}
        pending={run.isPending}
        confirmLabel="Выполнить команду"
      />
    </Panel>
  );
}
export default function ServerDetailPage() {
  const { user } = useSession();
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const pending = useIsMutating({ mutationKey: ["server-workspace", id] }) > 0;
  const [edit, setEdit] = useState(false);
  const [removeOpen, setRemoveOpen] = useState(false);
  const [copied, setCopied] = useState("");
  const [copyError, setCopyError] = useState<Error | null>(null);
  const query = useQuery({
    queryKey: ["server", id],
    queryFn: ({ signal }) => infrastructureApi.server(id, signal),
    enabled: Number.isInteger(id) && id > 0,
  });
  const bootstrap = useQuery({
    queryKey: ["servers"],
    queryFn: ({ signal }) => infrastructureApi.bootstrap(signal),
  });
  const remove = useMutation({
    mutationFn: () => infrastructureApi.remove(id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["servers"] });
      navigate("/infrastructure/servers");
    },
  });
  if (query.isPending) return <LoadingState />;
  if (query.error)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  const server = query.data;
  const sshCommand = `ssh -p ${server.port} ${server.username}@${server.host}`;
  const primaryTabs = [
    { value: "overview", label: "Подключение" },
    ...(server.capabilities.read_files
      ? [{ value: "files", label: "Файлы" }]
      : []),
    ...(server.can_edit ? [{ value: "knowledge", label: "Знания AI" }] : []),
    ...(server.capabilities.admin_share
      ? [{ value: "access", label: "Доступ" }]
      : []),
  ];
  const moreTabs = [
    ...(server.capabilities.execute_command
      ? [{ value: "command", label: "Выполнить команду" }]
      : []),
    ...(user?.is_staff && server.capabilities.connect_terminal
      ? [{ value: "operations", label: "Система" }]
      : []),
    { value: "snapshots", label: "Снимки файлов" },
  ];
  const requested = params.get("tab") ?? "overview";
  const tab = [...primaryTabs, ...moreTabs].some(
    (item) => item.value === requested,
  )
    ? requested
    : "overview";
  const setTab = (value: string) => {
    if (pending) return;
    const next = new URLSearchParams(params);
    if (value === "overview") next.delete("tab");
    else next.set("tab", value);
    setParams(next, { replace: true });
  };
  return (
    <>
      <Link className="row text-sm" to="/infrastructure/servers">
        <ArrowLeft size={14} />
        Серверы
      </Link>
      <PageHeader
        title={server.name}
        description={
          <span className="mono">
            {server.username}@{server.host}:{server.port}
          </span>
        }
        actions={
          <>
            {server.can_edit && (
              <Button onClick={() => setEdit(true)}>
                <Pencil size={14} />
                Настроить
              </Button>
            )}
            {server.capabilities.connect_terminal && (
              <Link
                className="btn btn-primary"
                to={`/infrastructure/terminal/${id}`}
              >
                <Terminal size={15} />
                Открыть терминал
              </Link>
            )}
          </>
        }
      />
      <div className="row spread">
        <Tabs
          value={tab}
          onChange={setTab}
          disabled={pending}
          items={primaryTabs}
        />
        <Dropdown.Root>
          <Dropdown.Trigger asChild>
            <Button
              variant="ghost"
              disabled={pending}
              aria-label="Ещё для сервера"
            >
              {moreTabs.find((item) => item.value === tab)?.label ?? "Ещё"}
              <ChevronDown size={14} />
            </Button>
          </Dropdown.Trigger>
          <Dropdown.Portal>
            <Dropdown.Content className="menu-content" align="end">
              {moreTabs.map((item) => (
                <Dropdown.Item
                  key={item.value}
                  className="menu-item"
                  onSelect={() => setTab(item.value)}
                >
                  {item.label}
                </Dropdown.Item>
              ))}
              {server.capabilities.view_context && (
                <Dropdown.Item asChild className="menu-item">
                  <Link to={`/intelligence/memory?server=${id}`}>
                    Память AI
                  </Link>
                </Dropdown.Item>
              )}
              {server.can_edit && (
                <>
                  <Dropdown.Separator className="menu-separator" />
                  <Dropdown.Item
                    className="menu-item danger"
                    onSelect={() => {
                      remove.reset();
                      setRemoveOpen(true);
                    }}
                  >
                    <Trash2 size={14} />
                    Удалить сервер
                  </Dropdown.Item>
                </>
              )}
            </Dropdown.Content>
          </Dropdown.Portal>
        </Dropdown.Root>
      </div>
      {tab === "overview" && (
        <div
          className="split-layout"
          style={{
            gridTemplateColumns:
              server.can_edit || server.capabilities.connect_terminal
                ? "minmax(0, 1fr) minmax(360px, 1fr)"
                : "minmax(0, 1fr)",
          }}
        >
          <div className="stack">
            <Panel title="Параметры SSH">
              <div className="section-body">
                <dl className="detail-list">
                  <dt>Адрес</dt>
                  <dd className="mono">{server.host}</dd>
                  <dt>Порт</dt>
                  <dd className="mono">{server.port}</dd>
                  <dt>Пользователь</dt>
                  <dd className="mono">{server.username}</dd>
                  <dt>Аутентификация</dt>
                  <dd>
                    {server.auth_method === "password"
                      ? "Пароль"
                      : server.auth_method === "key_password"
                        ? "SSH-ключ с парольной фразой"
                        : "SSH-ключ"}
                  </dd>
                  <dt>Теги</dt>
                  <dd>{server.tags || "Не указаны"}</dd>
                </dl>
                <Button
                  size="sm"
                  className="copy-ssh"
                  onClick={() => {
                    setCopyError(null);
                    void navigator.clipboard
                      .writeText(sshCommand)
                      .then(() => setCopied(sshCommand))
                      .catch(() => {
                        setCopied("");
                        setCopyError(
                          new Error(
                            "Не удалось скопировать. Скопируйте SSH-адрес вручную.",
                          ),
                        );
                      });
                  }}
                >
                  {copied === sshCommand ? (
                    <Check size={14} />
                  ) : (
                    <Copy size={14} />
                  )}
                  {copied === sshCommand
                    ? "Скопировано"
                    : "Скопировать SSH-команду"}
                </Button>
                <Feedback error={copyError} />
              </div>
            </Panel>
            {(server.notes || server.corporate_context) && (
              <Panel title="Рабочий контекст">
                <div className="section-body stack">
                  {server.notes && (
                    <p className="muted" style={{ whiteSpace: "pre-wrap" }}>
                      {server.notes}
                    </p>
                  )}
                  {server.corporate_context && (
                    <div>
                      <h3>Контекст для команды</h3>
                      <p
                        className="muted"
                        style={{ whiteSpace: "pre-wrap", marginTop: 8 }}
                      >
                        {server.corporate_context}
                      </p>
                    </div>
                  )}
                </div>
              </Panel>
            )}
          </div>
          {(server.can_edit || server.capabilities.connect_terminal) && (
            <div className="stack">
              <ServerSecurity server={server} />
            </div>
          )}
        </div>
      )}
      {tab === "files" && <ServerFiles server={server} />}{" "}
      {tab === "command" && <ServerCommand server={server} />}{" "}
      {tab === "access" && <ServerAccess server={server} />}
      {tab === "operations" && <ServerOperations server={server} />}
      {tab === "knowledge" && <ServerKnowledge server={server} />}
      {tab === "snapshots" && <ServerSnapshots server={server} />}
      <ServerForm
        key={`${id}-${edit}`}
        open={edit}
        onOpenChange={setEdit}
        server={server}
        groups={bootstrap.data?.groups ?? []}
      />
      <ConfirmDialog
        open={removeOpen}
        onOpenChange={(open) => {
          if (!remove.isPending) setRemoveOpen(open);
        }}
        title="Удалить сервер?"
        description={
          <div className="stack">
            <p>
              Запись «{server.name}», её настройки и общий доступ будут удалены
              из WebTerm. Сам сервер продолжит работать.
            </p>
            <Feedback error={remove.error} />
          </div>
        }
        typedText={server.name}
        confirmLabel="Удалить сервер"
        pending={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </>
  );
}
