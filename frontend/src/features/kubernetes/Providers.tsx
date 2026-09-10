import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, RefreshCw } from "lucide-react";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
  ErrorState,
  Field,
  JsonDetails,
  LoadingState,
  PageHeader,
  Panel,
} from "@/components/ui";
import { formatDate } from "@/lib/utils";
import {
  kubernetesApi,
  type KubeData,
  type KubeProvider,
} from "@/api/kubernetes";
import { KubeNav, KubeStatus, str, useKubeOperation } from "./common";

function ProviderEditor({
  provider,
  onClose,
}: {
  provider?: KubeProvider;
  onClose: () => void;
}) {
  const [name, setName] = useState(provider?.name || "");
  const [kind, setKind] = useState(provider?.kind || "rancher");
  const [url, setUrl] = useState(provider?.base_url || "");
  const [auth, setAuth] = useState(provider?.auth_mode || "secret_ref");
  const [token, setToken] = useState("");
  const [ref, setRef] = useState("");
  const [credential, setCredential] = useState("token");
  const [enabled, setEnabled] = useState(provider?.enabled ?? true);
  const [labels, setLabels] = useState(
    JSON.stringify(provider?.labels || {}, null, 2),
  );
  const op = useKubeOperation();
  async function save(e: FormEvent) {
    e.preventDefault();
    await op.run(async () => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(labels);
      } catch {
        throw new Error("Метки должны быть JSON-объектом.");
      }
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
        throw new Error("Метки должны быть JSON-объектом.");
      const data: KubeData = {
        name,
        kind,
        base_url: url,
        enabled,
        auth_mode: auth,
        labels: parsed,
      };
      if (auth === "secret_ref") {
        if (credential === "token" && token) data.secret_value = token;
        if (credential === "ref" && ref) data.secret_ref = ref;
      }
      await kubernetesApi.saveProvider(provider?.id, data);
      onClose();
    });
  }
  return (
    <Drawer
      open
      onOpenChange={(o) => !o && onClose()}
      title={provider ? "Настройка провайдера" : "Подключить провайдер"}
      description="Подключение используется для синхронизации и согласованных операций в кластерах."
    >
      <form className="stack" onSubmit={save}>
        {op.feedback}
        <Field label="Название" htmlFor="kp-name">
          <input
            id="kp-name"
            required
            maxLength={160}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field label="Платформа" htmlFor="kp-kind">
          <select
            id="kp-kind"
            value={kind}
            onChange={(e) => setKind(e.target.value as "rancher" | "devtron")}
          >
            <option value="rancher">Rancher</option>
            <option value="devtron">Devtron</option>
          </select>
        </Field>
        <Field label="Адрес API" htmlFor="kp-url">
          <input
            id="kp-url"
            type="url"
            required
            placeholder="https://rancher.company.ru"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </Field>
        <Field label="Авторизация" htmlFor="kp-auth">
          <select
            id="kp-auth"
            value={auth}
            onChange={(e) => setAuth(e.target.value)}
          >
            <option value="secret_ref">Секрет</option>
            <option value="oidc">OIDC</option>
            <option value="none">Без авторизации</option>
          </select>
        </Field>
        {auth === "secret_ref" && (
          <>
            <Field label="Источник секрета" htmlFor="kp-source">
              <select
                id="kp-source"
                value={credential}
                onChange={(e) => setCredential(e.target.value)}
              >
                <option value="token">
                  Сохранить токен в защищённом хранилище
                </option>
                <option value="ref">Ссылка на секрет</option>
              </select>
            </Field>
            {credential === "token" ? (
              <Field
                label={provider?.has_secret_ref ? "Новый токен" : "Токен"}
                htmlFor="kp-token"
                description={
                  provider?.has_secret_ref
                    ? "Оставьте поле пустым, чтобы сохранить текущий секрет."
                    : "Токен сохранится в управляемом хранилище backend."
                }
              >
                <input
                  id="kp-token"
                  type="password"
                  autoComplete="new-password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                />
              </Field>
            ) : (
              <Field
                label="Ссылка на секрет"
                htmlFor="kp-ref"
                description="env:, vault://, secret:// или другой поддерживаемый backend источник."
              >
                <input
                  id="kp-ref"
                  value={ref}
                  onChange={(e) => setRef(e.target.value)}
                  placeholder="env:RANCHER_TOKEN"
                />
              </Field>
            )}
          </>
        )}
        <label className="row">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />{" "}
          Провайдер включён
        </label>
        <details>
          <summary>Дополнительные метки и параметры</summary>
          <Field label="Метки JSON" htmlFor="kp-labels">
            <textarea
              id="kp-labels"
              className="kube-code"
              value={labels}
              onChange={(e) => setLabels(e.target.value)}
            />
          </Field>
        </details>
        <div className="kube-form-actions">
          <Button onClick={onClose}>Отмена</Button>
          <Button type="submit" variant="primary" loading={op.pending}>
            Сохранить
          </Button>
        </div>
      </form>
    </Drawer>
  );
}
export function ProvidersPage() {
  const q = useQuery({
    queryKey: ["kubernetes", "providers"],
    queryFn: kubernetesApi.providers,
  });
  const [edit, setEdit] = useState<KubeProvider | null | undefined>();
  const [remove, setRemove] = useState<KubeProvider>();
  const [result, setResult] = useState<{ title: string; data: KubeData }>();
  const op = useKubeOperation();
  return (
    <>
      <PageHeader
        eyebrow="Kubernetes"
        title="Провайдеры"
        description="Подключения Rancher и Devtron. Секреты хранятся на стороне backend."
        actions={
          <Button variant="primary" onClick={() => setEdit(null)}>
            <Plus size={16} /> Подключить
          </Button>
        }
      />
      <KubeNav />
      {op.feedback}
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} retry={() => q.refetch()} />
      ) : (
        <Panel title="Подключения">
          <DataTable
            rows={q.data?.providers || []}
            rowKey={(r) => r.id}
            searchValue={(r) => `${r.name} ${r.kind}`}
            emptyTitle="Провайдеры не настроены"
            emptyDescription="Добавьте Rancher или Devtron, затем проверьте соединение и запустите синхронизацию."
            emptyAction={
              <Button onClick={() => setEdit(null)}>
                Подключить провайдер
              </Button>
            }
            columns={[
              {
                key: "name",
                label: "Провайдер",
                render: (r) => (
                  <>
                    <strong>{r.name}</strong>
                    <p className="muted">{r.kind}</p>
                  </>
                ),
              },
              {
                key: "status",
                label: "Статус",
                render: (r) => (
                  <KubeStatus value={r.enabled ? r.sync_status : "disabled"} />
                ),
              },
              {
                key: "secret",
                label: "Авторизация",
                render: (r) =>
                  r.has_secret_ref ? "Секрет настроен" : r.auth_mode,
              },
              {
                key: "sync",
                label: "Синхронизация",
                render: (r) => (
                  <>
                    {formatDate(r.last_sync_at)}
                    {r.last_error && (
                      <p className="text-danger">{r.last_error}</p>
                    )}
                  </>
                ),
              },
              {
                key: "actions",
                label: "Действия",
                render: (r) => (
                  <div className="table-actions">
                    <Button size="sm" onClick={() => setEdit(r)}>
                      Настроить
                    </Button>
                    <Button
                      size="sm"
                      disabled={op.pending}
                      onClick={() =>
                        void op.run(async () => {
                          const data = await kubernetesApi.probeProvider(r.id);
                          setResult({ title: `Проверка · ${r.name}`, data });
                        }, "Проверка завершена")
                      }
                    >
                      Проверить
                    </Button>
                    <Button
                      size="sm"
                      disabled={op.pending || !r.enabled}
                      onClick={() =>
                        void op.run(async () => {
                          const data = await kubernetesApi.syncProvider(r.id);
                          setResult({
                            title: `Синхронизация · ${r.name}`,
                            data,
                          });
                        }, "Синхронизация завершена")
                      }
                    >
                      <RefreshCw size={14} /> Синхронизировать
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setRemove(r)}
                    >
                      Удалить
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        </Panel>
      )}
      {edit !== undefined && (
        <ProviderEditor
          provider={edit || undefined}
          onClose={() => setEdit(undefined)}
        />
      )}
      <ConfirmDialog
        open={!!remove}
        onOpenChange={(o) => !o && setRemove(undefined)}
        title="Удалить подключение?"
        description="Подключение и его управляемый секрет будут удалены. Дальнейшая синхронизация через него прекратится."
        typedText={remove?.name}
        pending={op.pending}
        onConfirm={() =>
          void op.run(async () => {
            await kubernetesApi.deleteProvider(remove!.id);
            setRemove(undefined);
          }, "Провайдер удалён")
        }
      />
      <Drawer
        open={!!result}
        onOpenChange={(o) => !o && setResult(undefined)}
        title={result?.title || "Результат"}
      >
        {result && (
          <div className="stack">
            <p>
              {str(
                result.data.message,
                result.data.status
                  ? str(result.data.status)
                  : "Операция завершена.",
              )}
            </p>
            <JsonDetails data={result.data} label="Результат проверки" />
          </div>
        )}
      </Drawer>
    </>
  );
}
