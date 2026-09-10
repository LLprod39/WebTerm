import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  Download,
  Package,
  Plus,
  RefreshCw,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { api } from "@/api/client";
import {
  governanceApi,
  type MarketplaceItem,
  type MarketplaceSource,
  type PluginInstallation,
  type PluginPackage,
  type PluginPermission,
  type PluginSettings,
} from "@/api/governance";
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

const base = "/api/plugins/";
function InstallDrawer({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState("upload");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [hash, setHash] = useState("");
  const [path, setPath] = useState("");
  const [validation, setValidation] = useState<unknown>(null);
  const install = useGovernanceMutation(async () => {
    if (tab === "upload") {
      if (!file) throw new Error("Выберите пакет");
      const body = new FormData();
      body.append("package", file);
      return api.upload(`${base}packages/install-local-upload/`, body);
    }
    return api.post(`${base}packages/install-remote/`, {
      url,
      expected_sha256: hash,
    });
  }, onClose);
  const validate = useGovernanceMutation(async () => {
    const result = await api.post(`${base}packages/validate-path/`, { path });
    setValidation(result);
    return result;
  });
  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open && !install.isPending) onClose();
      }}
      title="Установить пакет"
      description="Пакет проходит серверную проверку. Включение расширения выполняется отдельно."
      footer={
        tab !== "validate" && (
          <>
            <Button onClick={onClose}>Отмена</Button>
            <Button
              variant="primary"
              loading={install.isPending}
              disabled={
                tab === "upload"
                  ? !file
                  : !url.trim() || !/^[a-fA-F0-9]{64}$/.test(hash)
              }
              onClick={() => install.mutate()}
            >
              Установить пакет
            </Button>
          </>
        )
      }
    >
      <Feedback error={install.error ?? validate.error} />
      <Tabs
        items={[
          { value: "upload", label: "Файл" },
          { value: "remote", label: "По ссылке" },
          { value: "validate", label: "Проверить на сервере" },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "upload" ? (
        <FormField label="Пакет расширения .wtp">
          {(id) => (
            <input
              id={id}
              type="file"
              accept=".wtp,.zip"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          )}
        </FormField>
      ) : tab === "remote" ? (
        <div className="gov-form">
          <FormField label="HTTPS-ссылка на пакет">
            {(id) => (
              <input
                id={id}
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                required
              />
            )}
          </FormField>
          <FormField
            label="Ожидаемый SHA-256"
            description="Контрольная сумма от издателя, 64 шестнадцатеричных символа."
          >
            {(id) => (
              <input
                id={id}
                className="mono"
                value={hash}
                onChange={(e) => setHash(e.target.value.trim())}
                maxLength={64}
                required
              />
            )}
          </FormField>
        </div>
      ) : (
        <div className="gov-form">
          <FormField label="Путь к пакету на сервере">
            {(id) => (
              <input
                id={id}
                value={path}
                onChange={(e) => setPath(e.target.value)}
              />
            )}
          </FormField>
          <Button
            loading={validate.isPending}
            disabled={!path}
            onClick={() => validate.mutate()}
          >
            Проверить пакет
          </Button>
          {validation != null && (
            <JsonDetails data={validation} label="Результат проверки пакета" />
          )}
        </div>
      )}
    </Drawer>
  );
}

function PluginConfiguration({
  installation,
}: {
  installation: PluginInstallation;
}) {
  const query = useQuery({
    queryKey: ["governance", "plugin-settings", installation.id],
    queryFn: ({ signal }) =>
      api.get<PluginSettings>(
        `${base}installed/${installation.id}/settings/`,
        signal,
      ),
  });
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);
  const [refs, setRefs] = useState<Record<string, string>>({});
  const [jsonErrors, setJsonErrors] = useState<Record<string, string>>({});
  const save = useGovernanceMutation(
    () =>
      api.post(`${base}installed/${installation.id}/settings/update/`, {
        settings: draft ?? query.data?.settings ?? {},
      }),
    () => setDraft(null),
  );
  const bind = useGovernanceMutation(
    (key: string) =>
      api.post(`${base}installed/${installation.id}/secrets/bind/`, {
        key,
        secret_ref: refs[key],
      }),
    () => setRefs({}),
  );
  if (query.isPending) return <LoadingState />;
  if (query.error)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  const schema = query.data.schema;
  const properties =
    typeof schema.properties === "object" && schema.properties
      ? (schema.properties as Record<string, Record<string, unknown>>)
      : {};
  const values = draft ?? query.data.settings;
  const update = (key: string, value: unknown) =>
    setDraft((current) => ({
      ...(current ?? query.data.settings),
      [key]: value,
    }));
  return (
    <>
      <Feedback
        error={save.error ?? bind.error}
        success={save.message || bind.message}
      />
      <div className="gov-form">
        {Object.entries(properties).map(([key, field]) => {
          const label = String(field.title ?? key);
          if (field.type === "boolean")
            return (
              <CheckField
                key={key}
                label={label}
                description={
                  typeof field.description === "string"
                    ? field.description
                    : undefined
                }
                checked={!!values[key]}
                onChange={(value) => update(key, value)}
              />
            );
          return (
            <FormField
              key={key}
              label={label}
              description={
                typeof field.description === "string"
                  ? field.description
                  : undefined
              }
              error={jsonErrors[key]}
            >
              {(id) =>
                Array.isArray(field.enum) ? (
                  <select
                    id={id}
                    value={String(values[key] ?? "")}
                    onChange={(e) => update(key, e.target.value)}
                  >
                    <option value="">Не задано</option>
                    {field.enum.map((value) => (
                      <option key={String(value)} value={String(value)}>
                        {String(value)}
                      </option>
                    ))}
                  </select>
                ) : field.type === "object" || field.type === "array" ? (
                  <textarea
                    id={id}
                    className="mono"
                    rows={5}
                    defaultValue={JSON.stringify(
                      values[key] ?? (field.type === "array" ? [] : {}),
                      null,
                      2,
                    )}
                    onChange={(e) => {
                      try {
                        update(key, JSON.parse(e.target.value));
                        setJsonErrors((current) => ({ ...current, [key]: "" }));
                      } catch {
                        setJsonErrors((current) => ({
                          ...current,
                          [key]: "Проверьте формат JSON",
                        }));
                      }
                    }}
                  />
                ) : (
                  <input
                    id={id}
                    type={
                      field.type === "number" || field.type === "integer"
                        ? "number"
                        : "text"
                    }
                    min={
                      typeof field.minimum === "number"
                        ? field.minimum
                        : undefined
                    }
                    max={
                      typeof field.maximum === "number"
                        ? field.maximum
                        : undefined
                    }
                    value={String(values[key] ?? "")}
                    onChange={(e) =>
                      update(
                        key,
                        field.type === "number" || field.type === "integer"
                          ? Number(e.target.value)
                          : e.target.value,
                      )
                    }
                  />
                )
              }
            </FormField>
          );
        })}
        {!Object.keys(properties).length && (
          <p className="muted">У пакета нет настраиваемых параметров.</p>
        )}
        {Object.keys(properties).length > 0 && (
          <Button
            variant="primary"
            loading={save.isPending}
            disabled={!draft || Object.values(jsonErrors).some(Boolean)}
            onClick={() => save.mutate()}
          >
            Сохранить параметры
          </Button>
        )}
      </div>
      {query.data.secrets.length > 0 && (
        <Panel
          title="Секреты"
          description="Используйте ссылку на секрет из защищённого хранилища. Значения секретов здесь не раскрываются."
        >
          {query.data.secrets.map((secret) => (
            <div className="gov-secret-binding" key={secret.key}>
              <div>
                <strong>
                  {secret.label}
                  {secret.required ? " *" : ""}
                </strong>
                <StatusBadge status={secret.bound ? "ready" : "warning"}>
                  {secret.bound ? "Привязан" : "Не привязан"}
                </StatusBadge>
              </div>
              <FormField label="Ссылка на секрет">
                {(id) => (
                  <input
                    id={id}
                    type="password"
                    autoComplete="new-password"
                    value={refs[secret.key] ?? ""}
                    onChange={(e) =>
                      setRefs((current) => ({
                        ...current,
                        [secret.key]: e.target.value,
                      }))
                    }
                  />
                )}
              </FormField>
              <Button
                size="sm"
                loading={bind.isPending && bind.variables === secret.key}
                disabled={!refs[secret.key]}
                onClick={() => bind.mutate(secret.key)}
              >
                Привязать
              </Button>
            </div>
          ))}
        </Panel>
      )}
    </>
  );
}
function PluginAccess({ installation }: { installation: PluginInstallation }) {
  const permissions = useQuery({
    queryKey: ["governance", "plugin-permissions", installation.id],
    queryFn: ({ signal }) =>
      api.get<{ permissions: PluginPermission[] }>(
        `${base}installed/${installation.id}/permissions/`,
        signal,
      ),
  });
  const scope = useQuery({
    queryKey: ["governance", "plugin-scope", installation.id],
    queryFn: ({ signal }) =>
      api.get<{
        scope: { mode: string; group_ids: number[] };
        available_groups: { id: number; name: string }[];
      }>(`${base}installed/${installation.id}/scope/`, signal),
  });
  const [groupIds, setGroupIds] = useState<number[] | null>(null);
  const mutation = useGovernanceMutation(
    ({ scope: permission, grant }: { scope: string; grant: boolean }) =>
      api.post(
        `${base}installed/${installation.id}/permissions/${grant ? "grant" : "revoke"}/`,
        { scope: permission },
      ),
  );
  const saveScope = useGovernanceMutation(
    () =>
      api.post(`${base}installed/${installation.id}/scope/update/`, {
        group_ids: groupIds ?? scope.data?.scope.group_ids ?? [],
      }),
    () => setGroupIds(null),
  );
  return (
    <>
      <Feedback
        error={mutation.error ?? saveScope.error}
        success={mutation.message || saveScope.message}
      />
      {permissions.isPending ? (
        <LoadingState />
      ) : permissions.error ? (
        <ErrorState error={permissions.error} />
      ) : (
        <DataTable
          rows={permissions.data.permissions}
          rowKey={(row) => row.scope}
          emptyTitle="Пакет не запрашивает разрешений"
          columns={[
            {
              key: "scope",
              label: "Разрешение",
              render: (row) => (
                <span>
                  <strong>{row.scope}</strong>
                  <small className="gov-subline">{row.reason}</small>
                </span>
              ),
            },
            {
              key: "risk",
              label: "Риск",
              render: (row) => <StatusBadge status={row.risk_tier} />,
            },
            {
              key: "grant",
              label: "Доступ",
              render: (row) => (
                <CheckField
                  label={row.granted ? "Предоставлен" : "Не предоставлен"}
                  checked={row.granted}
                  disabled={mutation.isPending}
                  onChange={(checked) =>
                    mutation.mutate({ scope: row.scope, grant: checked })
                  }
                />
              ),
            },
          ]}
        />
      )}
      <Panel
        title="Доступ для групп"
        description="Если группы не выбраны, расширение доступно всем пользователям с необходимыми разрешениями."
      >
        {scope.isPending ? (
          <LoadingState />
        ) : scope.error ? (
          <ErrorState error={scope.error} />
        ) : (
          <>
            <div className="gov-check-list">
              {scope.data.available_groups.map((group) => (
                <CheckField
                  label={group.name}
                  key={group.id}
                  checked={(groupIds ?? scope.data.scope.group_ids).includes(
                    group.id,
                  )}
                  onChange={(checked) =>
                    setGroupIds((current) => {
                      const items = current ?? scope.data.scope.group_ids;
                      return checked
                        ? [...items, group.id]
                        : items.filter((id) => id !== group.id);
                    })
                  }
                />
              ))}
            </div>
            <Button
              variant="primary"
              disabled={groupIds === null}
              loading={saveScope.isPending}
              onClick={() => saveScope.mutate()}
            >
              Сохранить область доступа
            </Button>
          </>
        )}
      </Panel>
    </>
  );
}
function PluginLifecycle({
  installation,
  onClose,
}: {
  installation: PluginInstallation;
  onClose: () => void;
}) {
  const [operation, setOperation] = useState("");
  const [packageId, setPackageId] = useState("");
  const [reason, setReason] = useState("");
  const [revokePermissions, setRevokePermissions] = useState(false);
  const [removeSecrets, setRemoveSecrets] = useState(false);
  const [preview, setPreview] = useState<unknown>(null);
  const impact = useQuery({
    queryKey: ["governance", "plugin-impact", installation.id],
    queryFn: ({ signal }) =>
      api.get<{ impact: Record<string, unknown> }>(
        `${base}installed/${installation.id}/impact/`,
        signal,
      ),
  });
  const packages = useQuery({
    queryKey: ["governance", "plugin-packages"],
    queryFn: ({ signal }) =>
      api.get<{ packages: PluginPackage[] }>(`${base}review/packages/`, signal),
  });
  const previewMutation = useGovernanceMutation(async () => {
    const result = await api.post<{ impact: unknown }>(
      `${base}installed/${installation.id}/update-preview/`,
      { package_id: Number(packageId) },
    );
    setPreview(result.impact);
    return result;
  });
  const action = useGovernanceMutation(
    () =>
      operation === "quarantine"
        ? api.post(`${base}quarantine/`, {
            plugin_id: installation.plugin_id,
            reason,
          })
        : api.post(
            `${base}installed/${installation.id}/${operation}/`,
            operation === "soft-uninstall"
              ? {
                  revoke_permissions: revokePermissions,
                  remove_secret_bindings: removeSecrets,
                }
              : packageId
                ? { package_id: Number(packageId) }
                : {},
          ),
    () => {
      setOperation("");
      onClose();
    },
  );
  const candidates =
    packages.data?.packages.filter(
      (item) =>
        item.plugin_id === installation.plugin_id &&
        item.id !== installation.package.id,
    ) ?? [];
  return (
    <>
      <Feedback error={action.error ?? previewMutation.error} />
      {impact.isPending ? (
        <LoadingState />
      ) : impact.error ? (
        <ErrorState error={impact.error} />
      ) : (
        <JsonDetails
          data={impact.data.impact}
          label="Влияние на функции, разрешения и секреты"
        />
      )}
      <Panel title="Версии пакета">
        <FormField label="Доступная версия">
          {(id) => (
            <select
              id={id}
              value={packageId}
              onChange={(e) => {
                setPackageId(e.target.value);
                setPreview(null);
              }}
            >
              <option value="">Выберите версию</option>
              {candidates.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.version} · {item.review_status}
                </option>
              ))}
            </select>
          )}
        </FormField>
        <div className="gov-row-actions">
          <Button
            disabled={!packageId}
            loading={previewMutation.isPending}
            onClick={() => previewMutation.mutate()}
          >
            Проверить изменения
          </Button>
          <Button
            variant="primary"
            disabled={!packageId || preview === null}
            onClick={() => setOperation("update-package")}
          >
            Применить обновление
          </Button>
          <Button
            disabled={!packageId}
            onClick={() => setOperation("rollback")}
          >
            Откатить к версии
          </Button>
        </div>
        {preview !== null && (
          <JsonDetails data={preview} label="Проверка обновления" />
        )}
        {!candidates.length && (
          <p className="muted">
            Других сохранённых версий пока нет. Загрузите пакет нужной версии.
          </p>
        )}
        {packages.error && <ErrorState error={packages.error} />}
      </Panel>
      <Panel title="Отключение и удаление">
        <div className="gov-form">
          <FormField label="Причина карантина">
            {(id) => (
              <input
                id={id}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            )}
          </FormField>
          <Button
            variant="danger"
            disabled={!reason.trim()}
            onClick={() => setOperation("quarantine")}
          >
            Поместить в карантин
          </Button>
          <CheckField
            label="Отозвать разрешения при удалении"
            checked={revokePermissions}
            onChange={setRevokePermissions}
          />
          <CheckField
            label="Удалить привязки секретов"
            checked={removeSecrets}
            onChange={setRemoveSecrets}
          />
          <Button
            variant="danger"
            onClick={() => setOperation("soft-uninstall")}
          >
            Удалить установку
          </Button>
        </div>
      </Panel>
      <ConfirmDialog
        open={!!operation}
        onOpenChange={(open) => {
          if (!open) setOperation("");
        }}
        title={
          operation === "soft-uninstall"
            ? "Удалить установку?"
            : operation === "quarantine"
              ? "Поместить в карантин?"
              : operation === "rollback"
                ? "Откатить версию?"
                : "Обновить пакет?"
        }
        description={`Будет изменено расширение «${installation.package.name}». Проверьте влияние на действующие функции и доступ команды.`}
        typedText={installation.package.name}
        pending={action.isPending}
        confirmLabel="Подтвердить изменение"
        onConfirm={() => action.mutate()}
      />
    </>
  );
}
function PluginDrawer({
  installation,
  onClose,
}: {
  installation: PluginInstallation;
  onClose: () => void;
}) {
  const [tab, setTab] = useState("overview");
  const toggle = useGovernanceMutation(() =>
    api.post(
      `${base}installed/${installation.id}/${installation.status === "enabled" ? "disable" : "enable"}/`,
    ),
  );
  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={installation.package.name}
      description={`${installation.plugin_id} · версия ${installation.package.version}`}
      wide
    >
      <Feedback error={toggle.error} success={toggle.message} />
      <div className="gov-row-actions">
        <StatusBadge
          status={
            installation.status === "enabled" ? "active" : installation.status
          }
        />
        <StatusBadge status={installation.health_status || "unknown"} />
        <Button
          variant={installation.status === "enabled" ? "secondary" : "primary"}
          loading={toggle.isPending}
          onClick={() => toggle.mutate()}
        >
          {installation.status === "enabled" ? "Отключить" : "Включить"}
        </Button>
      </div>
      <Tabs
        items={[
          { value: "overview", label: "Обзор" },
          { value: "settings", label: "Параметры" },
          { value: "access", label: "Доступ" },
          { value: "lifecycle", label: "Жизненный цикл" },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "overview" ? (
        <>
          <p>
            {String(
              installation.package.manifest.description ??
                installation.package.manifest.summary ??
                "",
            )}
          </p>
          <dl className="gov-details">
            {[
              ["Издатель", installation.package.publisher.name],
              ["Проверка пакета", installation.package.review_status],
              ["Подпись", installation.package.signature_status],
              ["Уровень риска", installation.package.risk_tier],
              ["Установлен", dateTime(installation.installed_at)],
            ].map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          {installation.last_error && (
            <div className="notice notice-danger">
              {installation.last_error}
            </div>
          )}
          <JsonDetails
            data={installation.package.manifest}
            label="Манифест пакета"
          />
        </>
      ) : tab === "settings" ? (
        <PluginConfiguration installation={installation} />
      ) : tab === "access" ? (
        <PluginAccess installation={installation} />
      ) : (
        <PluginLifecycle installation={installation} onClose={onClose} />
      )}
    </Drawer>
  );
}

function InstalledPlugins() {
  const query = useQuery({
    queryKey: ["governance", "plugin-installations"],
    queryFn: ({ signal }) => governanceApi.installations(signal),
  });
  const [selected, setSelected] = useState<PluginInstallation | null>(null);
  const [install, setInstall] = useState(false);
  return (
    <>
      <div className="gov-section-heading">
        <div>
          <h2>Установленные расширения</h2>
          <p className="muted">Состояние пакетов, доступ и обновления.</p>
        </div>
        <Button variant="primary" onClick={() => setInstall(true)}>
          <Upload size={15} />
          Установить пакет
        </Button>
      </div>
      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <Panel>
          <DataTable
            rows={query.data.installations}
            rowKey={(row) => row.id}
            searchValue={(row) =>
              `${row.plugin_id} ${row.package.name} ${row.package.publisher.name}`
            }
            emptyTitle="Расширения ещё не установлены"
            emptyDescription="Добавьте проверенный пакет из каталога вашей организации или загрузите файл."
            emptyAction={
              <Button onClick={() => setInstall(true)}>Установить пакет</Button>
            }
            columns={[
              {
                key: "name",
                label: "Расширение",
                sortValue: (row) => row.package.name,
                render: (row) => (
                  <button
                    className="gov-identity"
                    onClick={() => setSelected(row)}
                  >
                    <span className="gov-avatar">
                      <Package size={18} />
                    </span>
                    <span>
                      <strong>{row.package.name}</strong>
                      <small>{row.package.publisher.name}</small>
                    </span>
                  </button>
                ),
              },
              {
                key: "version",
                label: "Версия",
                render: (row) => row.package.version,
              },
              {
                key: "status",
                label: "Состояние",
                render: (row) => (
                  <StatusBadge
                    status={row.status === "enabled" ? "active" : row.status}
                  />
                ),
              },
              {
                key: "review",
                label: "Проверка",
                render: (row) => (
                  <StatusBadge
                    status={
                      row.package.review_status === "verified"
                        ? "ready"
                        : row.package.review_status
                    }
                  >
                    {row.package.review_status === "verified"
                      ? "Проверен"
                      : row.package.review_status}
                  </StatusBadge>
                ),
              },
              {
                key: "actions",
                label: "Действия",
                render: (row) => (
                  <Button size="sm" onClick={() => setSelected(row)}>
                    Управлять
                  </Button>
                ),
              },
            ]}
          />
        </Panel>
      )}
      {selected && (
        <PluginDrawer
          key={selected.id}
          installation={
            query.data?.installations.find((item) => item.id === selected.id) ??
            selected
          }
          onClose={() => setSelected(null)}
        />
      )}{" "}
      {install && <InstallDrawer onClose={() => setInstall(false)} />}
    </>
  );
}

function Marketplace() {
  const query = useQuery({
    queryKey: ["governance", "plugin-marketplace"],
    queryFn: ({ signal }) =>
      api.get<{ items: MarketplaceItem[] }>(
        `${base}marketplace/catalog/`,
        signal,
      ),
  });
  const [selected, setSelected] = useState<MarketplaceItem | null>(null);
  const install = useGovernanceMutation(
    (id: number) => api.post(`${base}marketplace/catalog/${id}/install/`),
    () => setSelected(null),
  );
  const compatibility = useGovernanceMutation((id: number) =>
    api.post(`${base}marketplace/compatibility-jobs/`, { catalog_item_id: id }),
  );
  return (
    <>
      <Feedback
        error={install.error ?? compatibility.error}
        success={compatibility.message}
      />
      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <Panel title="Каталог организации">
          <DataTable
            rows={query.data.items}
            rowKey={(row) => row.id}
            searchValue={(row) => `${row.plugin_id} ${row.manifest.name ?? ""}`}
            emptyTitle="Каталог пуст"
            emptyDescription="Добавьте источник и выполните синхронизацию во вкладке «Источники»."
            columns={[
              {
                key: "name",
                label: "Расширение",
                render: (row) => (
                  <button
                    className="gov-cell-button"
                    onClick={() => setSelected(row)}
                  >
                    <strong>
                      {String(row.manifest.name ?? row.plugin_id)}
                    </strong>
                    <small>{row.source.name}</small>
                  </button>
                ),
              },
              { key: "version", label: "Версия", render: (row) => row.version },
              {
                key: "compatibility",
                label: "Совместимость",
                render: (row) => <StatusBadge status={row.compatibility} />,
              },
              {
                key: "status",
                label: "Проверка",
                render: (row) => row.review_status,
              },
              {
                key: "action",
                label: "Действие",
                render: (row) => (
                  <Button size="sm" onClick={() => setSelected(row)}>
                    {row.installed ? "Подробнее" : "Рассмотреть установку"}
                  </Button>
                ),
              },
            ]}
          />
        </Panel>
      )}
      <Drawer
        open={!!selected}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
        title={String(
          selected?.manifest.name ?? selected?.plugin_id ?? "Пакет",
        )}
        description={
          selected
            ? `Версия ${selected.version} · ${selected.source.name}`
            : undefined
        }
        wide
        footer={
          selected && (
            <>
              <Button
                onClick={() => compatibility.mutate(selected.id)}
                loading={compatibility.isPending}
              >
                Проверить совместимость
              </Button>
              <Button
                variant="primary"
                disabled={selected.installed}
                loading={install.isPending}
                onClick={() => install.mutate(selected.id)}
              >
                {selected.installed ? "Уже установлен" : "Установить"}
              </Button>
            </>
          )
        }
      >
        {selected && (
          <>
            <p>
              {String(
                selected.manifest.description ??
                  selected.manifest.summary ??
                  "",
              )}
            </p>
            <div className="gov-row-actions">
              <StatusBadge status={selected.review_status} />
              <StatusBadge status={selected.signature_status} />
            </div>
            <JsonDetails
              data={selected.compatibility_report}
              label="Отчёт совместимости"
            />
            <JsonDetails
              data={selected.manifest}
              label="Запрашиваемые функции и разрешения"
            />
            <Feedback
              error={install.error ?? compatibility.error}
              success={compatibility.message}
            />
          </>
        )}
      </Drawer>
    </>
  );
}

function SourceEditor({
  source,
  onClose,
}: {
  source: MarketplaceSource | null;
  onClose: () => void;
}) {
  const [name, setName] = useState(source?.name ?? "");
  const [url, setUrl] = useState(source?.source_url ?? "");
  const [enabled, setEnabled] = useState(source?.is_enabled ?? true);
  const save = useGovernanceMutation(
    () =>
      source
        ? api.patch(`${base}marketplace/sources/${source.id}/`, {
            name,
            ...(url !== source.source_url ? { source_url: url } : {}),
            is_enabled: enabled,
          })
        : api.post(`${base}marketplace/sources/`, {
            name,
            source_url: url,
            is_enabled: enabled,
          }),
    onClose,
  );
  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={source ? "Источник каталога" : "Новый источник"}
      description="Добавьте частный каталог пакетов вашей организации."
      footer={
        <>
          <Button onClick={onClose}>Отмена</Button>
          <Button
            variant="primary"
            disabled={!name.trim() || !url.trim()}
            loading={save.isPending}
            onClick={() => save.mutate()}
          >
            Сохранить источник
          </Button>
        </>
      }
    >
      <Feedback error={save.error} />
      <div className="gov-form">
        <FormField label="Название">
          {(id) => (
            <input
              id={id}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          )}
        </FormField>
        <FormField
          label="Адрес источника"
          description="HTTPS-источники поддерживают удалённую синхронизацию."
        >
          {(id) => (
            <input
              id={id}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              autoComplete="off"
            />
          )}
        </FormField>
        <CheckField
          label="Источник включён"
          checked={enabled}
          onChange={setEnabled}
        />
      </div>
    </Drawer>
  );
}
function Sources() {
  const query = useQuery({
    queryKey: ["governance", "plugin-sources"],
    queryFn: ({ signal }) =>
      api.get<{ sources: MarketplaceSource[] }>(
        `${base}marketplace/sources/`,
        signal,
      ),
  });
  const [editing, setEditing] = useState<
    MarketplaceSource | null | undefined
  >();
  const [manual, setManual] = useState<MarketplaceSource | null>(null);
  const [catalogText, setCatalogText] = useState("");
  const sync = useGovernanceMutation((id: number) =>
    api.post(`${base}marketplace/sources/${id}/sync-remote/`),
  );
  const manualSync = useGovernanceMutation(
    () => {
      let payload: unknown;
      try {
        payload = JSON.parse(catalogText);
      } catch {
        throw new Error("Выберите корректный JSON-файл каталога.");
      }
      return api.post(
        `${base}marketplace/sources/${manual!.id}/sync/`,
        payload,
      );
    },
    () => {
      setManual(null);
      setCatalogText("");
    },
  );
  return (
    <>
      <div className="gov-section-heading">
        <div>
          <h2>Источники каталога</h2>
          <p className="muted">
            Проверенные каталоги пакетов вашей организации.
          </p>
        </div>
        <Button variant="primary" onClick={() => setEditing(null)}>
          <Plus size={15} />
          Добавить источник
        </Button>
      </div>
      <Feedback error={sync.error} success={sync.message} />
      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} />
      ) : (
        <Panel>
          <DataTable
            rows={query.data.sources}
            rowKey={(row) => row.id}
            searchValue={(row) => row.name}
            emptyTitle="Источники не настроены"
            columns={[
              {
                key: "name",
                label: "Источник",
                render: (row) => (
                  <span>
                    <strong>{row.name}</strong>
                    <small className="gov-subline">{row.source_url}</small>
                    {row.last_error && (
                      <small className="field-error">{row.last_error}</small>
                    )}
                  </span>
                ),
              },
              {
                key: "state",
                label: "Состояние",
                render: (row) => (
                  <StatusBadge
                    status={row.is_enabled ? "active" : "disabled"}
                  />
                ),
              },
              {
                key: "last",
                label: "Последняя синхронизация",
                render: (row) => dateTime(row.last_sync_at),
              },
              {
                key: "actions",
                label: "Действия",
                render: (row) => (
                  <div className="gov-row-actions">
                    <Button
                      size="sm"
                      loading={sync.isPending && sync.variables === row.id}
                      onClick={() =>
                        row.sync_mode === "remote"
                          ? sync.mutate(row.id)
                          : setManual(row)
                      }
                    >
                      Синхронизировать
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setEditing(row)}
                    >
                      Настроить
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        </Panel>
      )}
      {editing !== undefined && (
        <SourceEditor source={editing} onClose={() => setEditing(undefined)} />
      )}
      <Drawer
        open={!!manual}
        onOpenChange={(open) => {
          if (!open) setManual(null);
        }}
        title="Синхронизировать каталог"
        description={manual?.name}
        footer={
          <Button
            variant="primary"
            disabled={!catalogText}
            loading={manualSync.isPending}
            onClick={() => manualSync.mutate()}
          >
            Импортировать каталог
          </Button>
        }
      >
        <Feedback error={manualSync.error} />
        <FormField label="JSON-файл каталога">
          {(id) => (
            <input
              id={id}
              type="file"
              accept="application/json,.json"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void file.text().then(setCatalogText);
              }}
            />
          )}
        </FormField>
      </Drawer>
    </>
  );
}

function PackageReview({
  item,
  onClose,
}: {
  item: PluginPackage;
  onClose: () => void;
}) {
  const [status, setStatus] = useState(item.review_status);
  const [notes, setNotes] = useState("");
  const [reason, setReason] = useState("");
  const [sign, setSign] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const save = useGovernanceMutation(
    () =>
      api.post(`${base}review/packages/${item.id}/review/`, {
        status,
        notes,
        rejection_reason: reason,
        sign_when_verified: sign,
      }),
    () => {
      setConfirm(false);
      onClose();
    },
  );
  const action = useGovernanceMutation((operation: string) =>
    api.post(`${base}review/packages/${item.id}/${operation}/`),
  );
  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={`Проверка: ${item.name}`}
      description={`${item.plugin_id} · ${item.version}`}
      wide
      footer={
        <>
          <Button onClick={onClose}>Закрыть</Button>
          <Button
            variant="primary"
            onClick={() => setConfirm(true)}
            disabled={status === "rejected" && !reason.trim()}
          >
            Сохранить решение
          </Button>
        </>
      }
    >
      <Feedback error={save.error ?? action.error} success={action.message} />
      <div className="gov-row-actions">
        <StatusBadge status={item.review_status} />
        <StatusBadge status={item.signature_status} />
        <StatusBadge status={item.risk_tier} />
      </div>
      <div className="gov-review-actions">
        {[
          { key: "security-scan", label: "Сканирование безопасности" },
          { key: "verify-signature", label: "Проверить подпись" },
          { key: "sign", label: "Подписать пакет" },
          { key: "attest", label: "Подтвердить аттестацию" },
          { key: "replay-provenance", label: "Проверить происхождение" },
        ].map((operation) => (
          <Button
            key={operation.key}
            size="sm"
            loading={action.isPending && action.variables === operation.key}
            disabled={action.isPending}
            onClick={() => action.mutate(operation.key)}
          >
            {operation.label}
          </Button>
        ))}
        <a
          className="btn btn-secondary btn-sm"
          href={`${base}review/packages/${item.id}/sbom/`}
          download
        >
          <Download size={14} />
          SBOM
        </a>
      </div>
      <JsonDetails
        data={{
          manifest: item.manifest,
          dependency_scan: item.dependency_scan,
          provenance: item.provenance,
          attestations: item.attestations,
          package_hash: item.package_hash,
        }}
        label="Пакет и результаты проверок"
      />
      <div className="gov-form">
        <FormField label="Решение">
          {(id) => (
            <select
              id={id}
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="pending">Ожидает проверки</option>
              <option value="verified">Проверен</option>
              <option value="rejected">Отклонён</option>
              <option value="suspended">Приостановлен</option>
            </select>
          )}
        </FormField>
        <FormField label="Комментарий проверки">
          {(id) => (
            <textarea
              id={id}
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          )}
        </FormField>
        {status === "rejected" && (
          <FormField label="Причина отклонения">
            {(id) => (
              <textarea
                id={id}
                required
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            )}
          </FormField>
        )}
        {status === "verified" && (
          <CheckField
            label="Подписать пакет после проверки"
            checked={sign}
            onChange={setSign}
          />
        )}
      </div>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Сохранить решение проверки?"
        description={`Статус пакета «${item.name}» ${item.version} изменится на «${status}». Решение влияет на возможность включения расширения.`}
        pending={save.isPending}
        confirmLabel="Сохранить решение"
        onConfirm={() => save.mutate()}
      />
    </Drawer>
  );
}
function Reviews() {
  const query = useQuery({
    queryKey: ["governance", "plugin-packages"],
    queryFn: ({ signal }) =>
      api.get<{
        packages: PluginPackage[];
        summary: { pending: number; total: number };
      }>(`${base}review/packages/`, signal),
  });
  const [selected, setSelected] = useState<PluginPackage | null>(null);
  return (
    <>
      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <Panel
          title="Проверка и доверие"
          description={`${query.data.summary.pending} пакетов ожидают проверки.`}
        >
          <DataTable
            rows={query.data.packages}
            rowKey={(row) => row.id}
            searchValue={(row) => `${row.plugin_id} ${row.name}`}
            emptyTitle="Нет пакетов для проверки"
            columns={[
              {
                key: "name",
                label: "Пакет",
                render: (row) => <strong>{row.name}</strong>,
              },
              { key: "version", label: "Версия", render: (row) => row.version },
              {
                key: "risk",
                label: "Риск",
                render: (row) => <StatusBadge status={row.risk_tier} />,
              },
              {
                key: "status",
                label: "Проверка",
                render: (row) => <StatusBadge status={row.review_status} />,
              },
              {
                key: "signature",
                label: "Подпись",
                render: (row) => row.signature_status,
              },
              {
                key: "action",
                label: "Действие",
                render: (row) => (
                  <Button size="sm" onClick={() => setSelected(row)}>
                    <ShieldCheck size={14} />
                    Рассмотреть
                  </Button>
                ),
              },
            ]}
          />
        </Panel>
      )}
      {selected && (
        <PackageReview
          item={
            query.data?.packages.find((item) => item.id === selected.id) ??
            selected
          }
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
function PluginMaintenance() {
  const [days, setDays] = useState(90);
  const [preview, setPreview] = useState<unknown>(null);
  const [confirm, setConfirm] = useState(false);
  const retention = useQuery({
    queryKey: ["governance", "plugin-retention"],
    queryFn: ({ signal }) =>
      api.get<{ retention: unknown }>(`${base}packages/retention/`, signal),
  });
  const matrix = useQuery({
    queryKey: ["governance", "plugin-compatibility"],
    queryFn: ({ signal }) =>
      api.get<{
        items: Record<string, unknown>[];
        summary: { total: number; compatible: number };
      }>(`${base}marketplace/compatibility-matrix/`, signal),
  });
  const jobs = useQuery({
    queryKey: ["governance", "plugin-jobs"],
    queryFn: ({ signal }) =>
      api.get<{ jobs: Record<string, unknown>[] }>(
        `${base}marketplace/compatibility-jobs/`,
        signal,
      ),
  });
  const check = useGovernanceMutation(() =>
    api.post(`${base}marketplace/compatibility-matrix/`),
  );
  const cleanup = useGovernanceMutation(async (dryRun: boolean) => {
    const result = await api.post<{ result: unknown }>(
      `${base}packages/retention/`,
      { max_age_days: days, dry_run: dryRun },
    );
    setPreview(result.result);
    if (!dryRun) setConfirm(false);
    return result;
  });
  return (
    <>
      <Feedback error={check.error ?? cleanup.error} success={check.message} />
      <Panel
        title="Совместимость пакетов"
        description={
          matrix.data
            ? `${matrix.data.summary.compatible} из ${matrix.data.summary.total} совместимы.`
            : undefined
        }
        actions={
          <Button loading={check.isPending} onClick={() => check.mutate()}>
            <RefreshCw size={15} />
            Перепроверить
          </Button>
        }
      >
        {matrix.isPending ? (
          <LoadingState />
        ) : matrix.error ? (
          <ErrorState error={matrix.error} />
        ) : (
          <JsonDetails data={matrix.data.items} label="Матрица совместимости" />
        )}
        {jobs.data && (
          <JsonDetails
            data={jobs.data.jobs}
            label="История проверок совместимости"
          />
        )}
        {jobs.error && <ErrorState error={jobs.error} />}
      </Panel>
      <Panel
        title="Хранение пакетов"
        description="Сначала проверьте состав очистки. Удаление сохранённых версий ограничит возможности отката."
      >
        {retention.isPending ? (
          <LoadingState />
        ) : retention.error ? (
          <ErrorState error={retention.error} />
        ) : (
          <JsonDetails
            data={retention.data.retention}
            label="Инвентаризация сохранённых пакетов"
          />
        )}
        <FormField label="Возраст пакетов, дней">
          {(id) => (
            <input
              id={id}
              type="number"
              min={1}
              max={3650}
              value={days}
              onChange={(e) => {
                setDays(Math.max(1, Number(e.target.value)));
                setPreview(null);
              }}
            />
          )}
        </FormField>
        <div className="gov-row-actions">
          <Button
            loading={cleanup.isPending}
            onClick={() => cleanup.mutate(true)}
          >
            Предварительная проверка
          </Button>
          <Button
            variant="danger"
            disabled={preview === null}
            onClick={() => setConfirm(true)}
          >
            Очистить пакеты
          </Button>
        </div>
        {preview !== null && (
          <JsonDetails data={preview} label="Результат проверки / очистки" />
        )}
      </Panel>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Удалить сохранённые пакеты?"
        description={`Будут очищены подходящие неиспользуемые пакеты старше ${days} дней согласно результатам проверки.`}
        typedText="ОЧИСТИТЬ"
        pending={cleanup.isPending}
        confirmLabel="Очистить"
        onConfirm={() => cleanup.mutate(false)}
      />
    </>
  );
}
function PluginsContent() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "installed";
  return (
    <>
      <PageHeader
        eyebrow="Управление"
        title="Расширения"
        description="Проверенные интеграции, управляемые пакеты и контроль доступа команды."
      />
      <Tabs
        items={[
          { value: "installed", label: "Установлены" },
          { value: "catalog", label: "Каталог" },
          { value: "sources", label: "Источники" },
          { value: "review", label: "Проверка и доверие" },
          { value: "maintenance", label: "Обслуживание" },
        ]}
        value={tab}
        onChange={(value) => setParams({ tab: value })}
      />
      {tab === "installed" ? (
        <InstalledPlugins />
      ) : tab === "catalog" ? (
        <Marketplace />
      ) : tab === "sources" ? (
        <Sources />
      ) : tab === "review" ? (
        <Reviews />
      ) : tab === "maintenance" ? (
        <PluginMaintenance />
      ) : (
        <EmptyState title="Раздел не найден" />
      )}
    </>
  );
}
export function PluginsPage() {
  return (
    <GovernanceGuard staff>
      <GovernanceGuard feature="plugins">
        <PluginsContent />
      </GovernanceGuard>
    </GovernanceGuard>
  );
}
