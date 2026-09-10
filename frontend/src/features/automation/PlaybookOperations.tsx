import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { api } from "@/api/client";
import {
  automationApi,
  playbookBase,
  type Binding,
  type Playbook,
  type ServerOption,
  type Values,
} from "@/api/automation";
import { usePermission } from "@/app/session";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
  ErrorState,
  Feedback,
  Field,
  Panel,
  Skeleton,
  StatusBadge,
} from "@/components/ui";
import { formatDate } from "@/lib/utils";
import { KeyValues, TargetPicker, ValidationResult } from "./shared";

export function PlaybookLaunch({
  playbook,
  open,
  onOpenChange,
}: {
  playbook: Playbook;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title={`Запуск: ${playbook.name}`}
      description="Выберите опубликованную версию и цели. Проверка не выполняет команды."
      wide
    >
      {open && <LaunchForm playbook={playbook} />}
    </Drawer>
  );
}
function LaunchForm({ playbook }: { playbook: Playbook }) {
  const navigate = useNavigate();
  const hasServers = usePermission("servers");
  const servers = useQuery({
    queryKey: ["automation", "servers"],
    queryFn: ({ signal }) => automationApi.servers(signal),
    enabled: hasServers,
  });
  const profiles = useQuery({
    queryKey: ["automation", "bindings", playbook.id],
    queryFn: ({ signal }) => automationApi.bindings(playbook.id, signal),
  });
  const revisions = useQuery({
    queryKey: ["automation", "revisions", playbook.id],
    queryFn: ({ signal }) => automationApi.revisions(playbook.id, signal),
  });
  const [revision, setRevision] = useState(playbook.published_revision_id ?? 0);
  const [profile, setProfile] = useState(0);
  const [targets, setTargets] = useState<number[]>([]);
  const [bindings, setBindings] = useState<Values>({});
  const [vars, setVars] = useState<Values>({});
  const [password, setPassword] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [become, setBecome] = useState(false);
  const [concurrency, setConcurrency] = useState(4);
  const [tags, setTags] = useState("");
  const [skipTags, setSkipTags] = useState("");
  const [limit, setLimit] = useState("");
  const [confirm, setConfirm] = useState(false);
  const payload = {
    revision_id: revision,
    binding_profile_id: profile || undefined,
    ...(targets.length ? { server_ids: targets } : {}),
    ...(Object.keys(bindings).length ? { inventory_bindings: bindings } : {}),
    extra_vars: vars,
    engine: playbook.kind === "runbook" ? "shell" : "ansible",
    dry_run: dryRun,
    become,
    concurrency,
    tags,
    skip_tags: skipTags,
    limit,
  };
  const validate = useMutation({
    mutationFn: () =>
      automationApi.validateRevision(playbook.id, revision, {
        ...payload,
        extra_vars: undefined,
        variable_names: Object.keys(vars),
      }),
  });
  const run = useMutation({
    mutationFn: () =>
      automationApi.runPlaybook(playbook.id, {
        ...payload,
        master_password: password || undefined,
      }),
    onSuccess: (data) => {
      setPassword("");
      navigate(`/automation/runs/playbook/${data.run.id}`);
    },
  });
  const validated = validate.data?.validation.status === "ready";
  const change = (fn: () => void) => {
    fn();
    validate.reset();
  };
  return (
    <div className="auto-form">
      <div className="auto-form-grid">
        <Field label="Версия для запуска" htmlFor="launch-revision">
          <select
            id="launch-revision"
            value={revision}
            onChange={(e) => change(() => setRevision(Number(e.target.value)))}
          >
            <option value={0}>Выберите версию</option>
            {(revisions.data?.revisions ?? []).map((r) => (
              <option key={r.id} value={r.id}>
                v{r.revision_number}
                {r.id === playbook.published_revision_id
                  ? " · опубликована"
                  : ""}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Профиль запуска" htmlFor="launch-profile">
          <select
            id="launch-profile"
            value={profile}
            onChange={(e) => change(() => setProfile(Number(e.target.value)))}
          >
            <option value={0}>Указать вручную</option>
            {(profiles.data?.bindings ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
      </div>
      {servers.error && <ErrorState error={servers.error} />}
      <TargetPicker
        servers={servers.data?.servers ?? []}
        value={targets}
        onChange={(v) => change(() => setTargets(v))}
      />
      <details>
        <summary>Привязка групп Ansible</summary>
        <InventoryBindings
          value={bindings}
          servers={servers.data?.servers ?? []}
          onChange={(v) => change(() => setBindings(v))}
        />
      </details>
      <KeyValues
        label="Переменные запуска"
        value={vars}
        onChange={(v) => change(() => setVars(v))}
      />
      <div className="auto-form-grid">
        <Field label="Параллельных хостов" htmlFor="launch-concurrency">
          <input
            id="launch-concurrency"
            type="number"
            min={1}
            max={20}
            value={concurrency}
            onChange={(e) =>
              change(() => setConcurrency(Number(e.target.value)))
            }
          />
        </Field>
        <Field label="Мастер-пароль (если требуется)" htmlFor="launch-password">
          <input
            id="launch-password"
            type="password"
            autoComplete="off"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
      </div>
      <label className="auto-check-row">
        <input
          type="checkbox"
          checked={dryRun}
          onChange={(e) => change(() => setDryRun(e.target.checked))}
        />
        <span>
          Проверочный запуск
          <small>
            Ansible check mode: показать планируемые изменения, если модуль
            поддерживает этот режим.
          </small>
        </span>
      </label>
      <label className="auto-check-row">
        <input
          type="checkbox"
          checked={become}
          onChange={(e) => change(() => setBecome(e.target.checked))}
        />
        Разрешить повышение привилегий (become)
      </label>
      <details>
        <summary>Фильтры задач</summary>
        <div className="auto-form">
          <Field label="Теги" htmlFor="launch-tags">
            <input
              id="launch-tags"
              value={tags}
              onChange={(e) => change(() => setTags(e.target.value))}
            />
          </Field>
          <Field label="Исключить теги" htmlFor="launch-skip-tags">
            <input
              id="launch-skip-tags"
              value={skipTags}
              onChange={(e) => change(() => setSkipTags(e.target.value))}
            />
          </Field>
          <Field label="Ограничение Ansible limit" htmlFor="launch-limit">
            <input
              id="launch-limit"
              value={limit}
              onChange={(e) => change(() => setLimit(e.target.value))}
            />
          </Field>
        </div>
      </details>
      <Feedback
        error={validate.error || run.error || profiles.error || revisions.error}
      />
      {validate.data && <ValidationResult value={validate.data.validation} />}
      <div className="auto-toolbar">
        <Button
          loading={validate.isPending}
          disabled={
            !revision ||
            (!targets.length && !profile && !Object.keys(bindings).length)
          }
          onClick={() => validate.mutate()}
        >
          <ShieldCheck size={15} />
          Проверить готовность
        </Button>
        <Button
          variant="primary"
          disabled={!validated || !playbook.capabilities.can_run}
          loading={run.isPending}
          onClick={() => setConfirm(true)}
        >
          <Play size={15} />
          Запустить
        </Button>
      </div>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={dryRun ? "Начать проверочный запуск?" : "Выполнить плейбук?"}
        description={`${playbook.name} будет выполнен на ${targets.length ? `${targets.length} выбранных серверах` : "целях выбранного профиля"}. ${dryRun ? "Включён режим проверки." : "Операция может изменить состояние инфраструктуры."}`}
        confirmLabel="Запустить"
        pending={run.isPending}
        onConfirm={() => run.mutate()}
      />
    </div>
  );
}
function InventoryBindings({
  value,
  onChange,
  servers,
}: {
  value: Values;
  onChange: (v: Values) => void;
  servers: ServerOption[];
}) {
  const [selector, setSelector] = useState("");
  return (
    <div className="auto-form">
      {Object.entries(value).map(([key, item]) => {
        const mapping =
          item && typeof item === "object" && !Array.isArray(item) ? item : {};
        const ids = Array.isArray(mapping.server_ids)
          ? mapping.server_ids.filter((v): v is number => typeof v === "number")
          : [];
        return (
          <div className="auto-task" key={key}>
            <div className="auto-task-head">
              <code>{key}</code>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Удалить группу ${key}`}
                onClick={() => {
                  const copy = { ...value };
                  delete copy[key];
                  onChange(copy);
                }}
              >
                <Trash2 size={14} />
              </Button>
            </div>
            <TargetPicker
              servers={servers}
              value={ids}
              onChange={(server_ids) =>
                onChange({ ...value, [key]: { ...mapping, server_ids } })
              }
            />
          </div>
        );
      })}
      <div className="auto-kv-add">
        <input
          aria-label="Имя группы Ansible"
          placeholder="Имя из hosts, например web"
          value={selector}
          onChange={(e) => setSelector(e.target.value)}
        />
        <Button
          disabled={!selector.trim() || selector in value}
          onClick={() => {
            onChange({
              ...value,
              [selector.trim()]: { server_ids: [], group_ids: [] },
            });
            setSelector("");
          }}
        >
          Добавить группу
        </Button>
      </div>
    </div>
  );
}
export function BindingProfiles({ playbook }: { playbook: Playbook }) {
  const query = useQuery({
    queryKey: ["automation", "bindings", playbook.id],
    queryFn: ({ signal }) => automationApi.bindings(playbook.id, signal),
  });
  const [editing, setEditing] = useState<Binding | null | undefined>(undefined);
  const [remove, setRemove] = useState<Binding | null>(null);
  const client = useQueryClient();
  const deletion = useMutation({
    mutationFn: () =>
      api.delete(`${playbookBase}${playbook.id}/bindings/${remove!.id}/`),
    onSuccess: () => {
      setRemove(null);
      void client.invalidateQueries({
        queryKey: ["automation", "bindings", playbook.id],
      });
    },
  });
  return (
    <>
      <Feedback error={deletion.error} />
      <Panel
        title="Профили запуска"
        description="Персональные цели, переменные и сохранённые секреты."
        actions={
          <Button onClick={() => setEditing(null)}>
            <Plus size={14} />
            Новый профиль
          </Button>
        }
      >
        {query.isPending ? (
          <Skeleton />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : (
          <DataTable
            rows={query.data?.bindings ?? []}
            rowKey={(r) => r.id}
            emptyTitle="Профилей пока нет"
            emptyDescription="Сохраните привязки целей и параметры для повторных запусков."
            columns={[
              {
                key: "name",
                label: "Профиль",
                render: (r) => (
                  <>
                    <strong>{r.name}</strong>
                    {r.is_default && <small>По умолчанию</small>}
                  </>
                ),
              },
              {
                key: "vars",
                label: "Параметры",
                render: (r) =>
                  `${Object.keys(r.variable_values).length} переменных · ${r.secret_variables.length} секретов`,
              },
              {
                key: "date",
                label: "Обновлён",
                render: (r) => formatDate(r.updated_at),
              },
              {
                key: "actions",
                label: "Действия",
                render: (r) => (
                  <div className="auto-toolbar">
                    <Button size="sm" onClick={() => setEditing(r)}>
                      Изменить
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={`Удалить профиль ${r.name}`}
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
        title={editing ? "Изменить профиль" : "Новый профиль"}
        wide
      >
        {editing !== undefined && (
          <BindingForm
            key={editing?.id ?? "new"}
            playbookId={playbook.id}
            binding={editing}
            done={() => setEditing(undefined)}
          />
        )}
      </Drawer>
      <ConfirmDialog
        open={!!remove}
        onOpenChange={(v) => !v && setRemove(null)}
        title="Удалить профиль запуска?"
        description={`Профиль «${remove?.name}» и его сохранённые секреты будут удалены.`}
        pending={deletion.isPending}
        onConfirm={() => deletion.mutate()}
        confirmLabel="Удалить"
      />
    </>
  );
}
function BindingForm({
  playbookId,
  binding,
  done,
}: {
  playbookId: number;
  binding: Binding | null;
  done: () => void;
}) {
  const canServers = usePermission("servers");
  const servers = useQuery({
    queryKey: ["automation", "servers"],
    queryFn: ({ signal }) => automationApi.servers(signal),
    enabled: canServers,
  });
  const [name, setName] = useState(binding?.name ?? "");
  const [mappings, setMappings] = useState<Values>(
    binding?.selector_mappings ?? {},
  );
  const [variables, setVariables] = useState<Values>(
    binding?.variable_values ?? {},
  );
  const [secrets, setSecrets] = useState<Values>({});
  const [removed, setRemoved] = useState<string[]>([]);
  const [defaultProfile, setDefault] = useState(binding?.is_default ?? false);
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: () => {
      const payload = {
        name,
        selector_mappings: mappings,
        variable_values: variables,
        secret_values: secrets,
        remove_secret_names: removed,
        is_default: defaultProfile,
        expected_version: binding?.version,
      };
      return binding
        ? api.patch(
            `${playbookBase}${playbookId}/bindings/${binding.id}/`,
            payload,
          )
        : api.post(`${playbookBase}${playbookId}/bindings/`, payload);
    },
    onSuccess: () => {
      setSecrets({});
      void client.invalidateQueries({
        queryKey: ["automation", "bindings", playbookId],
      });
      done();
    },
  });
  return (
    <form
      className="auto-form"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <Field label="Название профиля" htmlFor="binding-name">
        <input
          id="binding-name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      <InventoryBindings
        value={mappings}
        onChange={setMappings}
        servers={servers.data?.servers ?? []}
      />
      <KeyValues value={variables} onChange={setVariables} />
      <KeyValues
        label="Новые или обновлённые секреты"
        value={secrets}
        onChange={setSecrets}
        secret
      />
      {binding?.secret_variables.map((key) => (
        <label className="auto-check-row" key={key}>
          <input
            type="checkbox"
            checked={removed.includes(key)}
            onChange={(e) =>
              setRemoved(
                e.target.checked
                  ? [...removed, key]
                  : removed.filter((v) => v !== key),
              )
            }
          />
          Удалить сохранённый секрет {key}
        </label>
      ))}
      <label className="auto-check-row">
        <input
          type="checkbox"
          checked={defaultProfile}
          onChange={(e) => setDefault(e.target.checked)}
        />
        Использовать по умолчанию
      </label>
      <Feedback error={save.error || servers.error} />
      <Button type="submit" variant="primary" loading={save.isPending}>
        Сохранить профиль
      </Button>
    </form>
  );
}
interface Share {
  id: number;
  role: string;
  principal: { type: string; id: number; label: string };
  expires_at: string | null;
  revoked_at: string | null;
  capabilities: Record<string, boolean>;
}
export function PlaybookShares({ playbook }: { playbook: Playbook }) {
  const [principal, setPrincipal] = useState("");
  const [role, setRole] = useState("viewer");
  const [expires, setExpires] = useState("");
  const [remove, setRemove] = useState<Share | null>(null);
  const query = useQuery({
    queryKey: ["automation", "shares", playbook.id],
    queryFn: ({ signal }) =>
      api.get<{ shares: Share[] }>(
        `${playbookBase}${playbook.id}/shares/`,
        signal,
      ),
  });
  const candidates = useQuery({
    queryKey: ["automation", "share-candidates", playbook.id],
    queryFn: ({ signal }) =>
      api.get<{
        candidates: {
          users: { id: number; label: string; username: string }[];
          groups: { id: number; label: string }[];
        };
      }>(`${playbookBase}${playbook.id}/shares/candidates/?limit=50`, signal),
  });
  const client = useQueryClient();
  const add = useMutation({
    mutationFn: () =>
      api.post(`${playbookBase}${playbook.id}/shares/`, {
        principal_type: principal.split(":")[0],
        principal_id: Number(principal.split(":")[1]),
        role,
        expires_at: expires ? new Date(expires).toISOString() : null,
      }),
    onSuccess: () => {
      setPrincipal("");
      void client.invalidateQueries({
        queryKey: ["automation", "shares", playbook.id],
      });
    },
  });
  const revoke = useMutation({
    mutationFn: () =>
      api.delete(`${playbookBase}${playbook.id}/shares/${remove!.id}/`),
    onSuccess: () => {
      setRemove(null);
      void client.invalidateQueries({
        queryKey: ["automation", "shares", playbook.id],
      });
    },
  });
  return (
    <div className="auto-stack">
      <Panel
        title="Предоставить доступ"
        description="Пользователи и группы текущего рабочего пространства."
      >
        <form
          className="auto-pad auto-form"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <div className="auto-form-grid">
            <Field label="Пользователь или группа" htmlFor="share-principal">
              <select
                id="share-principal"
                required
                value={principal}
                onChange={(e) => setPrincipal(e.target.value)}
              >
                <option value="">Выберите получателя</option>
                <optgroup label="Пользователи">
                  {candidates.data?.candidates.users.map((u) => (
                    <option key={u.id} value={`user:${u.id}`}>
                      {u.label || u.username}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Группы">
                  {candidates.data?.candidates.groups.map((g) => (
                    <option key={g.id} value={`group:${g.id}`}>
                      {g.label}
                    </option>
                  ))}
                </optgroup>
              </select>
            </Field>
            <Field label="Роль" htmlFor="share-role">
              <select
                id="share-role"
                value={role}
                onChange={(e) => setRole(e.target.value)}
              >
                <option value="viewer">Читатель</option>
                <option value="operator">Оператор</option>
                <option value="editor">Редактор</option>
                <option value="manager">Управляющий</option>
              </select>
            </Field>
            <Field label="Доступ до (необязательно)" htmlFor="share-expires">
              <input
                id="share-expires"
                type="datetime-local"
                value={expires}
                onChange={(e) => setExpires(e.target.value)}
              />
            </Field>
          </div>
          <Feedback error={add.error || revoke.error || candidates.error} />
          <div>
            <Button
              type="submit"
              variant="primary"
              loading={add.isPending}
              disabled={!principal}
            >
              Предоставить доступ
            </Button>
          </div>
        </form>
      </Panel>
      <Panel title="Текущие разрешения">
        {query.isPending ? (
          <Skeleton />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : (
          <DataTable
            rows={(query.data?.shares ?? []).filter((s) => !s.revoked_at)}
            rowKey={(r) => r.id}
            emptyTitle="Плейбук доступен только владельцу"
            columns={[
              {
                key: "principal",
                label: "Получатель",
                render: (r) => r.principal.label,
              },
              { key: "role", label: "Роль", render: (r) => r.role },
              {
                key: "expires",
                label: "Срок",
                render: (r) =>
                  r.expires_at ? formatDate(r.expires_at) : "Без срока",
              },
              {
                key: "status",
                label: "Доступ",
                render: (r) => (
                  <StatusBadge
                    status={
                      r.expires_at && Date.parse(r.expires_at) < Date.now()
                        ? "disabled"
                        : "active"
                    }
                  />
                ),
              },
              {
                key: "action",
                label: "Действие",
                render: (r) => (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setRemove(r)}
                  >
                    Отозвать
                  </Button>
                ),
              },
            ]}
          />
        )}
      </Panel>
      <ConfirmDialog
        open={!!remove}
        onOpenChange={(v) => !v && setRemove(null)}
        title="Отозвать доступ?"
        description={`Получатель «${remove?.principal.label}» потеряет разрешения этого приглашения.`}
        onConfirm={() => revoke.mutate()}
        pending={revoke.isPending}
        confirmLabel="Отозвать"
      />
    </div>
  );
}
