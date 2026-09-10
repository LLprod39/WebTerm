import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Clipboard, ExternalLink, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { api } from "@/api/client";
import {
  governanceApi,
  type AiBinding,
  type AiCatalog,
  type AiConnection,
  type AiPool,
  type AiPreference,
  type AuthFlow,
} from "@/api/governance";
import { useSession } from "@/app/session";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
  EmptyState,
  ErrorState,
  Feedback,
  JsonDetails,
  LoadingState,
  PageHeader,
  Panel,
  StatusBadge,
  Tabs,
} from "@/components/ui";
import {
  CheckField,
  FormField,
  GovernanceGuard,
  dateTime,
  useGovernanceMutation,
} from "./shared";
import { PlatformAiSettings } from "./SettingsPages";

const purposeLabels: Record<string, string> = {
  assistant: "Ассистент",
  agents: "Агенты",
  terminal: "Терминал",
  internal: "Внутренние операции",
};
const connectionStatus: Record<string, string> = {
  pending_auth: "Ожидает входа",
  auth_required: "Требуется вход",
  limited: "Лимит исчерпан",
  degraded: "Нестабильно",
  revoked: "Отозвано",
};
function DeviceFlow({
  flowId,
  onFinished,
}: {
  flowId: string;
  onFinished: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<Error | null>(null);
  const query = useQuery({
    queryKey: ["governance", "auth-flow", flowId],
    queryFn: ({ signal }) =>
      api.get<{ auth_flow: AuthFlow }>(
        `/api/ai/providers/auth-flows/${flowId}/`,
        signal,
      ),
    refetchInterval: (query) =>
      query.state.data?.auth_flow.status === "pending" ? 2500 : false,
  });
  const flow = query.data?.auth_flow;
  const safeUrl =
    flow?.verification_uri && /^https:\/\//i.test(flow.verification_uri)
      ? flow.verification_uri
      : null;
  return (
    <Panel
      title="Подключение аккаунта"
      description="Подтвердите вход в браузере с вашим аккаунтом провайдера."
    >
      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        flow && (
          <>
            <StatusBadge status={flow.status} />
            {flow.user_code && (
              <div className="gov-device-code">
                <code>{flow.user_code}</code>
                <Button
                  size="sm"
                  onClick={() => {
                    setCopyError(null);
                    void navigator.clipboard
                      .writeText(flow.user_code)
                      .then(() => setCopied(true))
                      .catch(() =>
                        setCopyError(
                          new Error(
                            "Не удалось скопировать код. Выделите и скопируйте его вручную.",
                          ),
                        ),
                      );
                  }}
                >
                  <Clipboard size={14} />
                  {copied ? "Скопировано" : "Копировать"}
                </Button>
              </div>
            )}
            <Feedback error={copyError} />
            {safeUrl && flow.status === "pending" && (
              <a
                className="btn btn-primary btn-md"
                href={safeUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                Открыть страницу входа
                <ExternalLink size={15} />
              </a>
            )}
            {flow.status === "pending" && !safeUrl && (
              <p className="muted">
                Подготавливаем страницу авторизации. Ожидаем ответ обработчика.
              </p>
            )}
            {flow.expires_at && (
              <p className="muted text-sm">
                Код действует до {dateTime(flow.expires_at)}.
              </p>
            )}
            {flow.error_code && (
              <p className="notice notice-danger">{flow.error_code}</p>
            )}
            {flow.status !== "pending" && (
              <Button onClick={onFinished}>Обновить подключение</Button>
            )}
          </>
        )
      )}
    </Panel>
  );
}
function ConnectionDrawer({
  connection,
  catalog,
  onClose,
}: {
  connection: AiConnection | null;
  catalog: AiCatalog;
  onClose: () => void;
}) {
  const { user } = useSession();
  const [name, setName] = useState(connection?.name ?? "");
  const [target, setTarget] = useState(
    connection?.target_id ??
      catalog.targets.find((item) => item.kind === "subscription_cli")?.id ??
      "",
  );
  const [scope, setScope] = useState(connection?.scope ?? "personal");
  const [concurrency, setConcurrency] = useState(
    connection?.concurrency_limit ?? 1,
  );
  const [enabled, setEnabled] = useState(connection?.enabled ?? true);
  const [flowId, setFlowId] = useState("");
  const [revoke, setRevoke] = useState(false);
  const [revokeMessage, setRevokeMessage] = useState("");
  const canManage = connection?.manageable ?? true;
  const save = useGovernanceMutation(
    () =>
      connection
        ? api.patch(`/api/ai/providers/connections/${connection.id}/`, {
            name,
            concurrency_limit: concurrency,
            enabled,
          })
        : api.post("/api/ai/providers/connections/", {
            name,
            target_id: target,
            scope,
            concurrency_limit: concurrency,
          }),
    onClose,
  );
  const auth = useGovernanceMutation(async () => {
    const result = await api.post<{ auth_flow: AuthFlow }>(
      `/api/ai/providers/connections/${connection!.id}/auth/`,
    );
    setFlowId(result.auth_flow.id);
    return result;
  });
  const verify = useGovernanceMutation(async () => {
    const result = await api.post<{ auth_flow: AuthFlow }>(
      `/api/ai/providers/connections/${connection!.id}/verify/`,
    );
    setFlowId(result.auth_flow.id);
    return result;
  });
  const remove = useGovernanceMutation(async () => {
    const result = await api.delete<{
      revoked: boolean;
      cleanup_pending?: boolean;
    }>(`/api/ai/providers/connections/${connection!.id}/`);
    setRevoke(false);
    if (result.cleanup_pending)
      setRevokeMessage(
        "Подключение отключено. Очистка учётных данных ещё выполняется; повторите отзыв позже.",
      );
    else onClose();
    return result;
  });
  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open && !save.isPending) onClose();
      }}
      title={connection ? connection.name : "Новое CLI-подключение"}
      description="Изолированный доступ к подписке провайдера с собственным состоянием и лимитами."
      wide
      footer={
        <>
          <Button onClick={onClose}>Закрыть</Button>
          <Button
            variant="primary"
            loading={save.isPending}
            disabled={!name.trim() || !target || !canManage}
            onClick={() => save.mutate()}
          >
            Сохранить
          </Button>
        </>
      }
    >
      <Feedback
        error={save.error ?? auth.error ?? verify.error ?? remove.error}
        success={revokeMessage}
      />
      {connection && (
        <div className="gov-connection-state">
          <StatusBadge status={connection.status}>
            {connectionStatus[connection.status]}
          </StatusBadge>
          <span className="muted">
            Проверено {dateTime(connection.last_verified_at)}
          </span>
        </div>
      )}
      <fieldset disabled={!canManage} className="gov-form">
        <FormField label="Название">
          {(id) => (
            <input
              id={id}
              value={name}
              maxLength={120}
              onChange={(e) => setName(e.target.value)}
              required
            />
          )}
        </FormField>
        {!connection && (
          <div className="gov-form-grid">
            <FormField label="Провайдер">
              {(id) => (
                <select
                  id={id}
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                >
                  {catalog.targets
                    .filter((item) => item.kind === "subscription_cli")
                    .map((item) => (
                      <option value={item.id} key={item.id}>
                        {item.label}
                      </option>
                    ))}
                </select>
              )}
            </FormField>
            <FormField label="Доступ">
              {(id) => (
                <select
                  id={id}
                  value={scope}
                  onChange={(e) => setScope(e.target.value)}
                >
                  <option value="personal">Личное подключение</option>
                  {user?.features.ai_connections_admin && (
                    <option value="workspace">
                      Подключение рабочего пространства
                    </option>
                  )}
                </select>
              )}
            </FormField>
          </div>
        )}
        <FormField
          label="Одновременные операции"
          description="От 1 до 8 операций для этого подключения."
        >
          {(id) => (
            <input
              id={id}
              type="number"
              min={1}
              max={8}
              value={concurrency}
              onChange={(e) =>
                setConcurrency(Math.max(1, Math.min(8, Number(e.target.value))))
              }
            />
          )}
        </FormField>
        {connection && (
          <CheckField
            label="Подключение включено"
            checked={enabled}
            onChange={setEnabled}
          />
        )}
      </fieldset>
      {connection && (
        <>
          <div className="gov-row-actions">
            <Button
              variant="primary"
              disabled={!canManage}
              loading={auth.isPending}
              onClick={() => auth.mutate()}
            >
              Войти в аккаунт
            </Button>
            <Button
              disabled={!canManage || connection.status === "pending_auth"}
              loading={verify.isPending}
              onClick={() => verify.mutate()}
            >
              <RefreshCw size={15} />
              Проверить
            </Button>
            <Button
              variant="danger"
              disabled={!canManage}
              onClick={() => setRevoke(true)}
            >
              Отозвать доступ
            </Button>
          </div>
          {flowId && (
            <DeviceFlow
              flowId={flowId}
              onFinished={() => {
                setFlowId("");
                onClose();
              }}
            />
          )}
          {connection.last_error_code && (
            <div className="notice notice-warning">
              Последняя ошибка: {connection.last_error_code}
            </div>
          )}
          <JsonDetails
            data={{
              health: connection.health,
              limits: connection.limits,
              runtime_version: connection.runtime_version,
              access: connection.access,
            }}
            label="Состояние и лимиты провайдера"
          />
          {connection.scope === "workspace" &&
            user?.features.ai_connections_admin && (
              <ConnectionGrants connection={connection} />
            )}
        </>
      )}
      <ConfirmDialog
        open={revoke}
        onOpenChange={setRevoke}
        title="Отозвать доступ к подписке?"
        description={`Подключение «${name}» будет отключено, активные операции потеряют право продолжать запись результатов. Сохранённые учётные данные будут удалены.`}
        typedText={name}
        pending={remove.isPending}
        onConfirm={() => remove.mutate()}
        confirmLabel="Отозвать доступ"
      />
    </Drawer>
  );
}
function ConnectionGrants({ connection }: { connection: AiConnection }) {
  const { user } = useSession();
  const [principalType, setPrincipalType] = useState("user_id");
  const [principal, setPrincipal] = useState("");
  const [projectRole, setProjectRole] = useState("");
  const [interactive, setInteractive] = useState(true);
  const [unattended, setUnattended] = useState(false);
  const users = useQuery({
    queryKey: ["governance", "users"],
    queryFn: ({ signal }) => governanceApi.users(signal),
    enabled: !!user?.is_staff,
  });
  const groups = useQuery({
    queryKey: ["governance", "groups"],
    queryFn: ({ signal }) => governanceApi.groups(signal),
    enabled: !!user?.is_staff,
  });
  const grant = useGovernanceMutation(
    () =>
      api.post("/api/ai/providers/grants/", {
        connection_id: connection.id,
        [principalType]: Number(principal),
        project_role: projectRole,
        allow_interactive: interactive,
        allow_unattended: unattended,
      }),
    () => setPrincipal(""),
  );
  const revoke = useGovernanceMutation((id: number) =>
    api.delete(`/api/ai/providers/grants/${id}/`),
  );
  const connectionQuery = useQuery({
    queryKey: ["governance", "connection", connection.id],
    queryFn: ({ signal }) =>
      api.get<{ connection: AiConnection }>(
        `/api/ai/providers/connections/${connection.id}/`,
        signal,
      ),
  });
  const grants =
    connectionQuery.data?.connection.grants ?? connection.grants ?? [];
  return (
    <Panel
      title="Кому разрешено использовать"
      description="Фоновое выполнение разрешается отдельно от интерактивных запросов."
    >
      <Feedback
        error={grant.error ?? revoke.error}
        success={grant.message || revoke.message}
      />
      <div className="gov-form-grid">
        <FormField label="Тип получателя">
          {(id) => (
            <select
              id={id}
              value={principalType}
              onChange={(e) => {
                setPrincipalType(e.target.value);
                setPrincipal("");
              }}
            >
              <option value="user_id">Пользователь</option>
              <option value="group_id">Группа</option>
              <option value="project_id">Проект</option>
            </select>
          )}
        </FormField>
        <FormField
          label={
            principalType === "project_id"
              ? "Числовой идентификатор проекта"
              : "Получатель"
          }
        >
          {(id) =>
            principalType === "project_id" || !user?.is_staff ? (
              <input
                id={id}
                type="number"
                min={1}
                value={principal}
                onChange={(e) => setPrincipal(e.target.value)}
              />
            ) : (
              <select
                id={id}
                value={principal}
                onChange={(e) => setPrincipal(e.target.value)}
              >
                <option value="">Выберите получателя</option>
                {principalType === "user_id"
                  ? users.data?.users.map((item) => (
                      <option value={item.id} key={item.id}>
                        {item.username}
                      </option>
                    ))
                  : groups.data?.groups.map((item) => (
                      <option value={item.id} key={item.id}>
                        {item.name}
                      </option>
                    ))}
              </select>
            )
          }
        </FormField>
        {principalType === "project_id" && (
          <FormField label="Роль внутри проекта">
            {(id) => (
              <select
                id={id}
                value={projectRole}
                onChange={(e) => setProjectRole(e.target.value)}
              >
                <option value="">Все роли</option>
                {["owner", "admin", "operator", "viewer"].map((role) => (
                  <option value={role} key={role}>
                    {role}
                  </option>
                ))}
              </select>
            )}
          </FormField>
        )}
      </div>
      <div className="gov-row-actions">
        <CheckField
          label="Интерактивные запросы"
          checked={interactive}
          onChange={setInteractive}
        />
        <CheckField
          label="Фоновое выполнение"
          checked={unattended}
          onChange={setUnattended}
        />
        <Button
          disabled={!principal}
          loading={grant.isPending}
          onClick={() => grant.mutate()}
        >
          Выдать доступ
        </Button>
      </div>
      <DataTable
        rows={grants}
        rowKey={(row) => row.id}
        emptyTitle="Назначений пока нет"
        columns={[
          {
            key: "who",
            label: "Получатель",
            render: (row) =>
              row.user?.username ?? row.group?.name ?? row.project?.name ?? "—",
          },
          {
            key: "mode",
            label: "Режимы",
            render: (row) =>
              [
                row.allow_interactive ? "Интерактивно" : "",
                row.allow_unattended ? "В фоне" : "",
              ]
                .filter(Boolean)
                .join(", ") || "Нет доступа",
          },
          {
            key: "revoke",
            label: "Действие",
            render: (row) => (
              <Button
                size="sm"
                variant="ghost"
                disabled={revoke.isPending}
                onClick={() => revoke.mutate(row.id)}
              >
                Отозвать
              </Button>
            ),
          },
        ]}
      />
      {(users.error || groups.error) && (
        <ErrorState error={users.error ?? groups.error} />
      )}
    </Panel>
  );
}
function ConnectionsContent() {
  const connections = useQuery({
    queryKey: ["governance", "connections"],
    queryFn: ({ signal }) => governanceApi.connections(signal),
    refetchInterval: 15000,
  });
  const catalog = useQuery({
    queryKey: ["governance", "ai-catalog"],
    queryFn: ({ signal }) => governanceApi.aiCatalog(signal),
    staleTime: 300000,
  });
  const [editing, setEditing] = useState<AiConnection | null | undefined>();
  return (
    <>
      <div className="gov-section-heading">
        <div>
          <h2>Подключения к подпискам</h2>
          <p className="muted">
            Управляйте входом, состоянием и правами использования CLI.
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => setEditing(null)}
          disabled={!catalog.data}
        >
          <Plus size={16} />
          Добавить подключение
        </Button>
      </div>
      {connections.isPending || catalog.isPending ? (
        <LoadingState />
      ) : connections.error || catalog.error ? (
        <ErrorState
          error={connections.error ?? catalog.error}
          retry={() => {
            void connections.refetch();
            void catalog.refetch();
          }}
        />
      ) : (
        <Panel>
          <DataTable
            rows={connections.data.connections}
            rowKey={(row) => row.id}
            searchValue={(row) => `${row.name} ${row.target_id}`}
            emptyTitle="CLI-подключений пока нет"
            emptyDescription="Добавьте подключение и завершите вход в аккаунт провайдера."
            emptyAction={
              <Button onClick={() => setEditing(null)}>
                Добавить подключение
              </Button>
            }
            columns={[
              {
                key: "name",
                label: "Подключение",
                render: (row) => (
                  <button
                    className="gov-cell-button"
                    onClick={() => setEditing(row)}
                  >
                    <strong>{row.name}</strong>
                    <small>{row.target_id}</small>
                  </button>
                ),
              },
              {
                key: "scope",
                label: "Область",
                render: (row) =>
                  row.scope === "workspace" ? "Рабочее пространство" : "Личное",
              },
              {
                key: "state",
                label: "Состояние",
                render: (row) => (
                  <StatusBadge status={row.status}>
                    {connectionStatus[row.status]}
                  </StatusBadge>
                ),
              },
              {
                key: "checked",
                label: "Последняя проверка",
                render: (row) => dateTime(row.last_verified_at),
              },
              {
                key: "actions",
                label: "Действия",
                render: (row) => (
                  <Button size="sm" onClick={() => setEditing(row)}>
                    Настроить
                  </Button>
                ),
              },
            ]}
          />
        </Panel>
      )}
      {editing !== undefined && catalog.data && (
        <ConnectionDrawer
          key={editing?.id ?? "new"}
          connection={
            editing
              ? (connections.data?.connections.find(
                  (item) => item.id === editing.id,
                ) ?? editing)
              : null
          }
          catalog={catalog.data}
          onClose={() => setEditing(undefined)}
        />
      )}
    </>
  );
}
function PoolDrawer({
  pool,
  connections,
  onClose,
}: {
  pool: AiPool | null;
  connections: AiConnection[];
  onClose: () => void;
}) {
  const [name, setName] = useState(pool?.name ?? "");
  const [target, setTarget] = useState(pool?.target_id ?? "codex_subscription");
  const [enabled, setEnabled] = useState(pool?.enabled ?? true);
  const [members, setMembers] = useState(
    pool?.members.map((item) => ({
      connection_id: item.connection_id,
      weight: item.weight,
      enabled: item.enabled,
    })) ?? [],
  );
  const save = useGovernanceMutation(
    () =>
      pool
        ? api.patch(`/api/ai/providers/pools/${pool.id}/`, {
            name,
            enabled,
            members,
          })
        : api.post("/api/ai/providers/pools/", {
            name,
            target_id: target,
            members,
          }),
    onClose,
  );
  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={pool ? pool.name : "Новый пул подключений"}
      description="Пул распределяет выполнение между подключениями одного провайдера."
      wide
      footer={
        <>
          <Button onClick={onClose}>Отмена</Button>
          <Button
            variant="primary"
            loading={save.isPending}
            disabled={!name.trim()}
            onClick={() => save.mutate()}
          >
            Сохранить пул
          </Button>
        </>
      }
    >
      <Feedback error={save.error} />
      <div className="gov-form">
        <FormField label="Название пула">
          {(id) => (
            <input
              id={id}
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={120}
              required
            />
          )}
        </FormField>
        <FormField label="Провайдер">
          {(id) => (
            <select
              id={id}
              disabled={!!pool}
              value={target}
              onChange={(e) => {
                setTarget(e.target.value);
                setMembers([]);
              }}
            >
              <option value="codex_subscription">Codex CLI</option>
              <option value="grok_subscription">Grok CLI</option>
            </select>
          )}
        </FormField>
        <CheckField
          label="Пул включён"
          checked={enabled}
          onChange={setEnabled}
        />
        <h3>Подключения рабочего пространства</h3>
        {connections.filter(
          (item) => item.scope === "workspace" && item.target_id === target,
        ).length === 0 && (
          <EmptyState
            title="Нет подходящих подключений"
            description="Сначала создайте подключение рабочего пространства для выбранного провайдера."
          />
        )}
        {connections
          .filter(
            (item) => item.scope === "workspace" && item.target_id === target,
          )
          .map((item) => {
            const member = members.find((m) => m.connection_id === item.id);
            return (
              <div className="gov-pool-member" key={item.id}>
                <CheckField
                  label={item.name}
                  checked={!!member}
                  onChange={(checked) =>
                    setMembers((current) =>
                      checked
                        ? [
                            ...current,
                            {
                              connection_id: item.id,
                              weight: 1,
                              enabled: true,
                            },
                          ]
                        : current.filter((m) => m.connection_id !== item.id),
                    )
                  }
                />
                <StatusBadge status={item.status} />
                {member && (
                  <>
                    <FormField label="Вес">
                      {(id) => (
                        <input
                          id={id}
                          type="number"
                          min={1}
                          max={100}
                          value={member.weight}
                          onChange={(e) =>
                            setMembers((current) =>
                              current.map((m) =>
                                m.connection_id === item.id
                                  ? {
                                      ...m,
                                      weight: Math.max(
                                        1,
                                        Math.min(100, Number(e.target.value)),
                                      ),
                                    }
                                  : m,
                              ),
                            )
                          }
                        />
                      )}
                    </FormField>
                    <CheckField
                      label="В работе"
                      checked={member.enabled}
                      onChange={(next) =>
                        setMembers((current) =>
                          current.map((m) =>
                            m.connection_id === item.id
                              ? { ...m, enabled: next }
                              : m,
                          ),
                        )
                      }
                    />
                  </>
                )}
              </div>
            );
          })}
      </div>
    </Drawer>
  );
}
function PoolsContent() {
  const pools = useQuery({
    queryKey: ["governance", "pools"],
    queryFn: ({ signal }) => governanceApi.pools(signal),
  });
  const connections = useQuery({
    queryKey: ["governance", "connections"],
    queryFn: ({ signal }) => governanceApi.connections(signal),
  });
  const [editing, setEditing] = useState<AiPool | null | undefined>();
  const [deleting, setDeleting] = useState<AiPool | null>(null);
  const remove = useGovernanceMutation(
    (id: number) => api.delete(`/api/ai/providers/pools/${id}/`),
    () => setDeleting(null),
  );
  return (
    <>
      <div className="gov-section-heading">
        <div>
          <h2>Пулы подключений</h2>
          <p className="muted">
            Общие ресурсы провайдеров для стабильного выполнения.
          </p>
        </div>
        <Button variant="primary" onClick={() => setEditing(null)}>
          <Plus size={15} />
          Создать пул
        </Button>
      </div>
      <Feedback error={remove.error} success={remove.message} />
      {pools.isPending || connections.isPending ? (
        <LoadingState />
      ) : pools.error || connections.error ? (
        <ErrorState error={pools.error ?? connections.error} />
      ) : (
        <Panel>
          <DataTable
            rows={pools.data.pools}
            rowKey={(row) => row.id}
            searchValue={(row) => row.name}
            emptyTitle="Пулы пока не созданы"
            columns={[
              {
                key: "name",
                label: "Пул",
                render: (row) => <strong>{row.name}</strong>,
              },
              {
                key: "target",
                label: "Провайдер",
                render: (row) => row.target_id,
              },
              {
                key: "members",
                label: "Подключения",
                render: (row) => row.members.length,
              },
              {
                key: "status",
                label: "Состояние",
                render: (row) => (
                  <StatusBadge status={row.enabled ? "active" : "disabled"} />
                ),
              },
              {
                key: "actions",
                label: "Действия",
                render: (row) => (
                  <div className="gov-row-actions">
                    <Button size="sm" onClick={() => setEditing(row)}>
                      Настроить
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={`Удалить пул ${row.name}`}
                      onClick={() => setDeleting(row)}
                    >
                      <Trash2 size={15} />
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        </Panel>
      )}
      {editing !== undefined && connections.data && (
        <PoolDrawer
          pool={editing}
          connections={connections.data.connections}
          onClose={() => setEditing(undefined)}
        />
      )}
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title="Удалить пул?"
        description={`Пул «${deleting?.name}» перестанет использоваться для маршрутизации. Сами подключения сохранятся.`}
        pending={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        confirmLabel="Удалить пул"
      />
    </>
  );
}
function PreferenceRow({
  purpose,
  catalog,
  connections,
  pools,
  preference,
  workspace,
}: {
  purpose: string;
  catalog: AiCatalog;
  connections: AiConnection[];
  pools: AiPool[];
  preference?: AiPreference;
  workspace: boolean;
}) {
  const [binding, setBinding] = useState<AiBinding>(
    preference?.binding ?? { target_id: catalog.targets[0]?.id ?? "" },
  );
  const [scope, setScope] = useState(
    preference ? preference.project_id !== null : true,
  );
  const save = useGovernanceMutation(() =>
    api.put("/api/ai/providers/preferences/", {
      purpose,
      workspace_default: workspace,
      project_scoped: scope,
      binding,
    }),
  );
  const reset = useGovernanceMutation(() =>
    api.delete("/api/ai/providers/preferences/", {
      purpose,
      workspace_default: workspace,
      project_scoped: scope,
    }),
  );
  const models = catalog.models_by_target[binding.target_id] ?? [];
  const efforts =
    models.find((model) => model.id === binding.model_id)?.reasoning_efforts ??
    models[0]?.reasoning_efforts ??
    [];
  const subscription =
    catalog.targets.find((item) => item.id === binding.target_id)?.kind ===
    "subscription_cli";
  return (
    <Panel
      title={purposeLabels[purpose] ?? purpose}
      description={
        preference
          ? "Назначение сохранено."
          : "Используются унаследованные настройки."
      }
    >
      <Feedback
        error={save.error ?? reset.error}
        success={save.message || reset.message}
      />
      <div className="gov-form-grid">
        <FormField label="Провайдер">
          {(id) => (
            <select
              id={id}
              value={binding.target_id}
              onChange={(e) => setBinding({ target_id: e.target.value })}
            >
              {catalog.targets.map((target) => (
                <option key={target.id} value={target.id}>
                  {target.label}
                </option>
              ))}
            </select>
          )}
        </FormField>
        {subscription && (
          <FormField label="Источник подключения">
            {(id) => (
              <select
                id={id}
                value={
                  binding.pool_id
                    ? `pool:${binding.pool_id}`
                    : binding.connection_id
                      ? `connection:${binding.connection_id}`
                      : ""
                }
                onChange={(e) => {
                  const [kind, value] = e.target.value.split(":");
                  setBinding((current) => ({
                    ...current,
                    connection_id: kind === "connection" ? Number(value) : null,
                    pool_id: kind === "pool" ? Number(value) : null,
                  }));
                }}
              >
                <option value="">Автоматически</option>
                {connections
                  .filter(
                    (item) =>
                      item.target_id === binding.target_id &&
                      (!workspace || item.scope === "workspace"),
                  )
                  .map((item) => (
                    <option key={`c${item.id}`} value={`connection:${item.id}`}>
                      {item.name}
                    </option>
                  ))}
                {pools
                  .filter(
                    (item) =>
                      item.target_id === binding.target_id && item.enabled,
                  )
                  .map((item) => (
                    <option key={`p${item.id}`} value={`pool:${item.id}`}>
                      Пул: {item.name}
                    </option>
                  ))}
              </select>
            )}
          </FormField>
        )}
        <FormField label="Модель">
          {(id) =>
            models.length ? (
              <select
                id={id}
                value={binding.model_id ?? ""}
                onChange={(e) =>
                  setBinding((current) => ({
                    ...current,
                    model_id: e.target.value || null,
                    reasoning_effort: null,
                  }))
                }
              >
                <option value="">По умолчанию</option>
                {models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.label ?? model.id}
                  </option>
                ))}
              </select>
            ) : (
              <input
                id={id}
                value={binding.model_id ?? ""}
                onChange={(e) =>
                  setBinding((current) => ({
                    ...current,
                    model_id: e.target.value || null,
                  }))
                }
                placeholder="По умолчанию"
              />
            )
          }
        </FormField>
        {efforts.length > 0 && (
          <FormField label="Глубина рассуждений">
            {(id) => (
              <select
                id={id}
                value={binding.reasoning_effort ?? ""}
                onChange={(e) =>
                  setBinding((current) => ({
                    ...current,
                    reasoning_effort: e.target.value || null,
                  }))
                }
              >
                <option value="">По умолчанию</option>
                {efforts.map((effort) => (
                  <option key={effort} value={effort}>
                    {effort}
                  </option>
                ))}
              </select>
            )}
          </FormField>
        )}
      </div>
      <div className="gov-row-actions">
        {!workspace && (
          <CheckField
            label="Только текущий проект"
            checked={scope}
            onChange={setScope}
          />
        )}
        <Button
          variant="primary"
          loading={save.isPending}
          onClick={() => save.mutate()}
        >
          Сохранить назначение
        </Button>
        {preference && (
          <Button loading={reset.isPending} onClick={() => reset.mutate()}>
            Восстановить наследование
          </Button>
        )}
      </div>
    </Panel>
  );
}
function PreferencesContent() {
  const { user } = useSession();
  const admin = !!user?.features.ai_connections_admin;
  const [workspace, setWorkspace] = useState(false);
  const catalog = useQuery({
    queryKey: ["governance", "ai-catalog"],
    queryFn: ({ signal }) => governanceApi.aiCatalog(signal),
  });
  const connections = useQuery({
    queryKey: ["governance", "connections"],
    queryFn: ({ signal }) => governanceApi.connections(signal),
  });
  const pools = useQuery({
    queryKey: ["governance", "pools"],
    queryFn: ({ signal }) => governanceApi.pools(signal),
    enabled: admin,
  });
  const preferences = useQuery({
    queryKey: ["governance", "preferences"],
    queryFn: ({ signal }) => governanceApi.preferences(signal),
  });
  return (
    <>
      <div className="gov-section-heading">
        <div>
          <h2>Модель и режим по назначению</h2>
          <p className="muted">
            Отдельные правила для ассистента, агентов, терминала и внутренних
            операций.
          </p>
        </div>
        {admin && (
          <select
            aria-label="Область назначения"
            value={workspace ? "workspace" : "personal"}
            onChange={(e) => setWorkspace(e.target.value === "workspace")}
          >
            <option value="personal">Мои назначения</option>
            <option value="workspace">По умолчанию для проекта</option>
          </select>
        )}
      </div>
      {catalog.isPending || connections.isPending || preferences.isPending ? (
        <LoadingState />
      ) : catalog.error || connections.error || preferences.error ? (
        <ErrorState
          error={catalog.error ?? connections.error ?? preferences.error}
        />
      ) : (
        catalog.data.purposes.map((purpose) => (
          <PreferenceRow
            key={`${purpose}-${workspace}-${preferences.data.preferences.map((p) => p.id).join(",")}-${preferences.data.workspace_defaults.map((p) => p.id).join(",")}`}
            purpose={purpose}
            catalog={catalog.data}
            connections={connections.data.connections}
            pools={pools.data?.pools ?? []}
            preference={(workspace
              ? preferences.data.workspace_defaults
              : preferences.data.preferences
            ).find((item) => item.purpose === purpose)}
            workspace={workspace}
          />
        ))
      )}
      {pools.error && <ErrorState error={pools.error} />}
    </>
  );
}
function AiContent() {
  const { user } = useSession();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "platform";
  const available =
    !!user?.ai_cli_runtime_enabled && !!user.features.ai_connections_personal;
  const tabs = [
    { value: "platform", label: "Провайдеры и модели" },
    { value: "connections", label: "CLI-подписки" },
    { value: "preferences", label: "Назначение моделей" },
    ...(user?.features.ai_connections_admin
      ? [{ value: "pools", label: "Пулы" }]
      : []),
  ];
  return (
    <>
      <PageHeader
        eyebrow="Настройки платформы"
        title="AI и подключения"
        description="Подключения провайдеров, модели и доступ к подпискам команды."
      />
      <Tabs
        items={tabs}
        value={tab}
        onChange={(value) => setParams({ tab: value })}
      />
      {tab === "platform" ? (
        <PlatformAiSettings />
      ) : !available ? (
        <EmptyState
          title="CLI-подписки недоступны"
          description={
            !user?.ai_cli_runtime_enabled
              ? "Возможность отключена в текущем развёртывании платформы."
              : "Для управления CLI-подписками требуется назначение доступа."
          }
        />
      ) : tab === "connections" ? (
        <ConnectionsContent />
      ) : tab === "preferences" ? (
        <PreferencesContent />
      ) : tab === "pools" && user?.features.ai_connections_admin ? (
        <PoolsContent />
      ) : (
        <EmptyState
          title="Раздел недоступен"
          description="Проверьте предоставленные права доступа."
        />
      )}
    </>
  );
}
export function AiSettingsPage() {
  return (
    <GovernanceGuard ai>
      <AiContent />
    </GovernanceGuard>
  );
}
