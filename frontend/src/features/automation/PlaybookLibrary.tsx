import { useState, type FormEvent, type ChangeEvent } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { BookOpen, Plus, Upload, Library, Copy } from "lucide-react";
import { api } from "@/api/client";
import {
  automationApi,
  playbookBase,
  type Playbook,
  type Template,
  type Values,
} from "@/api/automation";
import {
  Button,
  DataTable,
  Drawer,
  ErrorState,
  Feedback,
  Field,
  PageHeader,
  Panel,
  Skeleton,
  StatusBadge,
  Tabs,
  JsonDetails,
} from "@/components/ui";
import { formatDate } from "@/lib/utils";

export function PlaybookLibrary() {
  const query = useQuery({
    queryKey: ["automation", "playbooks"],
    queryFn: ({ signal }) => automationApi.playbooks(signal),
  });
  const location = useLocation();
  const navigate = useNavigate();
  const archived = (
    location.state as { archived?: { id: number; name: string } } | null
  )?.archived;
  const restore = useMutation({
    mutationFn: () => api.post(`${playbookBase}${archived!.id}/restore/`),
    onSuccess: () =>
      navigate(`/automation/playbooks/${archived!.id}`, { replace: true }),
  });
  const [drawer, setDrawer] = useState("");
  const [kind, setKind] = useState("all");
  const rows = (query.data?.playbooks ?? []).filter(
    (item) => kind === "all" || item.kind === kind,
  );
  return (
    <>
      <PageHeader
        eyebrow="Автоматизация"
        title="Плейбуки"
        description="Версионируемые инструкции для повторяемых операций на инфраструктуре."
        actions={
          <>
            <Button onClick={() => setDrawer("import")}>
              <Upload size={15} />
              Импорт
            </Button>
            <Button onClick={() => setDrawer("templates")}>
              <Library size={15} />
              Шаблоны
            </Button>
            <Button variant="primary" onClick={() => setDrawer("create")}>
              <Plus size={16} />
              Новый плейбук
            </Button>
          </>
        }
      />
      <Feedback error={restore.error} />
      {archived && (
        <div className="auto-notice auto-toolbar">
          <span>«{archived.name}» перемещён в архив.</span>
          <Button
            size="sm"
            onClick={() => restore.mutate()}
            loading={restore.isPending}
          >
            Восстановить
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() =>
              navigate(location.pathname, { replace: true, state: null })
            }
          >
            Закрыть
          </Button>
        </div>
      )}
      <Panel>
        {query.isPending ? (
          <Skeleton />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : (
          <DataTable
            rows={rows}
            rowKey={(r) => r.id}
            searchValue={(r) =>
              `${r.name} ${r.description} ${r.tags.join(" ")}`
            }
            searchPlaceholder="Поиск плейбуков"
            emptyTitle="Создайте первый плейбук"
            emptyDescription="Добавьте Ansible YAML, команды runbook или импортируйте проект."
            emptyAction={
              <Button variant="primary" onClick={() => setDrawer("create")}>
                Создать плейбук
              </Button>
            }
            toolbar={
              <select
                aria-label="Тип плейбука"
                value={kind}
                onChange={(e) => setKind(e.target.value)}
              >
                <option value="all">Все типы</option>
                <option value="ansible">Ansible</option>
                <option value="runbook">Runbook</option>
              </select>
            }
            columns={[
              {
                key: "name",
                label: "Плейбук",
                sortValue: (r) => r.name,
                render: (r) => (
                  <div className="table-name">
                    <span className="table-icon">
                      <BookOpen size={17} />
                    </span>
                    <div className="auto-row-title">
                      <Link to={`/automation/playbooks/${r.id}`}>{r.name}</Link>
                      <small>
                        {r.description ||
                          `${r.task_count} задач · ${r.category}`}
                      </small>
                    </div>
                  </div>
                ),
              },
              {
                key: "revision",
                label: "Публикация",
                render: (r) => (
                  <>
                    <span>
                      {r.published_revision_number
                        ? `Версия ${r.published_revision_number}`
                        : "Не опубликован"}
                    </span>
                    {r.has_unpublished_draft && (
                      <small>Есть изменения в черновике</small>
                    )}
                  </>
                ),
              },
              {
                key: "type",
                label: "Тип",
                render: (r) => (
                  <span className="auto-tag">
                    {r.kind === "ansible" ? "Ansible" : "Runbook"}
                  </span>
                ),
              },
              {
                key: "status",
                label: "Последний запуск",
                render: (r) => (
                  <>
                    <StatusBadge status={r.last_run_status || "unknown"} />
                    <small>{formatDate(r.last_run_at)}</small>
                  </>
                ),
              },
              {
                key: "updated",
                label: "Изменён",
                sortValue: (r) => r.updated_at,
                render: (r) => formatDate(r.updated_at),
              },
            ]}
          />
        )}
      </Panel>
      <Drawer
        open={drawer !== ""}
        onOpenChange={(v) => !v && setDrawer("")}
        title={
          drawer === "create"
            ? "Новый плейбук"
            : drawer === "import"
              ? "Импорт плейбука"
              : "Библиотека шаблонов"
        }
        wide
      >
        {drawer === "create" ? (
          <CreatePlaybook />
        ) : drawer === "import" ? (
          <ImportPlaybook />
        ) : drawer === "templates" ? (
          <PlaybookTemplates />
        ) : null}
      </Drawer>
    </>
  );
}
function CreatePlaybook() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [kind, setKind] = useState("ansible");
  const [source, setSource] = useState("");
  const [command, setCommand] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      automationApi.createPlaybook({
        name,
        description,
        kind,
        source_yaml: kind === "ansible" ? source : "",
        tasks:
          kind === "runbook"
            ? [
                {
                  id: "task-1",
                  command,
                  description: "",
                  continue_on_error: false,
                },
              ]
            : [],
      }),
    onSuccess: (data) => navigate(`/automation/playbooks/${data.playbook.id}`),
  });
  return (
    <form
      className="auto-form"
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate();
      }}
    >
      <Field label="Название" htmlFor="playbook-name">
        <input
          id="playbook-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          maxLength={200}
        />
      </Field>
      <Field label="Описание" htmlFor="playbook-description">
        <textarea
          id="playbook-description"
          rows={2}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </Field>
      <Field label="Тип" htmlFor="playbook-kind">
        <select
          id="playbook-kind"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option value="ansible">Ansible YAML</option>
          <option value="runbook">Команды runbook</option>
        </select>
      </Field>
      {kind === "ansible" ? (
        <Field label="Ansible YAML" htmlFor="playbook-source">
          <textarea
            id="playbook-source"
            className="mono"
            rows={14}
            required
            value={source}
            onChange={(e) => setSource(e.target.value)}
            spellCheck={false}
          />
        </Field>
      ) : (
        <Field label="Первая команда" htmlFor="playbook-command">
          <textarea
            id="playbook-command"
            className="mono"
            required
            value={command}
            onChange={(e) => setCommand(e.target.value)}
          />
        </Field>
      )}
      <Feedback error={mutation.error} />
      <Button type="submit" variant="primary" loading={mutation.isPending}>
        Создать плейбук
      </Button>
    </form>
  );
}
interface ImportPreview {
  content_hash: string;
  entrypoint?: string;
  selected_entrypoint?: string;
  entrypoint_candidates?: string[];
  safe_to_commit?: boolean;
  secret_warnings?: { message?: string; code?: string; path?: string }[];
  controller_warnings?: { message?: string; code?: string; path?: string }[];
  complexity_warnings?: { message?: string; code?: string }[];
  blocking_reasons?: string[];
  project_path?: string;
  file_count?: number;
  size_bytes?: number;
  files?: { path: string; size_bytes?: number }[];
  warnings?: string[];
  [key: string]: unknown;
}
function ImportPlaybook() {
  const navigate = useNavigate();
  const [mode, setMode] = useState("yaml");
  const [content, setContent] = useState("");
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [entrypoint, setEntrypoint] = useState("");
  const [directory, setDirectory] = useState("");
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");
  const [token, setToken] = useState("");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const clear = () => setPreview(null);
  const payload = () => ({
    content,
    name,
    save: false,
    project_url: url,
    ref,
    path: directory,
    entrypoint,
    token,
  });
  const formData = (commit = false) => {
    const data = new FormData();
    if (file) data.append("bundle", file);
    data.append("name", name);
    data.append("entrypoint", entrypoint);
    data.append("project_path", directory);
    if (commit && preview) {
      data.append("expected_content_hash", preview.content_hash);
      data.append("expected_project_path", directory);
    }
    return data;
  };
  const inspect = useMutation({
    mutationFn: async () => {
      if (mode === "archive")
        return api.upload<{ preview: ImportPreview }>(
          `${playbookBase}import/preview/`,
          formData(),
        );
      if (mode === "gitlab")
        return api.post<{ preview: ImportPreview }>(
          `${playbookBase}import/gitlab/preview/`,
          payload(),
        );
      const result = await api.post<
        {
          preview?: ImportPreview | boolean;
          content_hash?: string;
          source_preview?: ImportPreview;
        } & ImportPreview
      >(`${playbookBase}import/`, payload());
      return {
        preview: {
          ...result,
          ...(typeof result.preview === "object" ? result.preview : {}),
          content_hash:
            result.content_hash ?? result.source_preview?.content_hash ?? "",
        },
      };
    },
    onSuccess: (data) => setPreview(data.preview),
  });
  const commit = useMutation({
    mutationFn: async () => {
      if (mode === "archive")
        return api.upload<{ playbook: Playbook }>(
          `${playbookBase}import/commit/`,
          formData(true),
        );
      return api.post<{ playbook: Playbook }>(
        `${playbookBase}import/${mode === "gitlab" ? "gitlab/commit/" : ""}`,
        {
          ...payload(),
          save: true,
          expected_content_hash: preview?.content_hash,
        },
      );
    },
    onSuccess: (data) => {
      setToken("");
      navigate(`/automation/playbooks/${data.playbook.id}`);
    },
  });
  const change =
    (setter: (value: string) => void) =>
    (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      setter(e.target.value);
      clear();
    };
  return (
    <div className="auto-form">
      <Tabs
        items={[
          { value: "yaml", label: "YAML" },
          { value: "archive", label: "Архив проекта" },
          { value: "gitlab", label: "GitLab" },
        ]}
        value={mode}
        onChange={(v) => {
          setMode(v);
          clear();
        }}
      />
      <Field label="Название" htmlFor="import-name">
        <input
          id="import-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      {mode === "yaml" ? (
        <Field label="Содержимое YAML" htmlFor="import-yaml">
          <textarea
            id="import-yaml"
            rows={14}
            className="mono"
            value={content}
            onChange={change(setContent)}
            spellCheck={false}
          />
        </Field>
      ) : mode === "archive" ? (
        <Field label="ZIP / TAR архив проекта" htmlFor="import-file">
          <input
            id="import-file"
            type="file"
            accept=".zip,.tar,.tgz,.gz"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              clear();
            }}
          />
        </Field>
      ) : (
        <>
          <Field label="GitLab URL проекта" htmlFor="import-url">
            <input
              id="import-url"
              type="url"
              value={url}
              onChange={change(setUrl)}
            />
          </Field>
          <Field label="Ветка, тег или commit" htmlFor="import-ref">
            <input id="import-ref" value={ref} onChange={change(setRef)} />
          </Field>
          <Field label="Токен доступа (если нужен)" htmlFor="import-token">
            <input
              id="import-token"
              type="password"
              autoComplete="off"
              value={token}
              onChange={change(setToken)}
            />
          </Field>
        </>
      )}
      {mode !== "yaml" && (
        <div className="auto-form-grid">
          <Field label="Каталог в проекте" htmlFor="import-directory">
            <input
              id="import-directory"
              value={directory}
              onChange={change(setDirectory)}
            />
          </Field>
          <Field label="Основной YAML файл" htmlFor="import-entrypoint">
            <input
              id="import-entrypoint"
              placeholder="Автоматическое определение"
              value={entrypoint}
              onChange={change(setEntrypoint)}
            />
          </Field>
        </div>
      )}
      <Feedback error={inspect.error || commit.error} />
      <Button
        loading={inspect.isPending}
        disabled={
          mode === "yaml"
            ? !content.trim()
            : mode === "archive"
              ? !file
              : !url.trim()
        }
        onClick={() => inspect.mutate()}
      >
        Проверить перед импортом
      </Button>
      {preview && (
        <Panel title="Проверка импорта">
          <div className="auto-pad auto-form">
            <p>
              {preview.file_count != null
                ? `${preview.file_count} файлов · `
                : ""}
              {preview.selected_entrypoint ||
                preview.entrypoint ||
                "YAML плейбук"}
            </p>
            {(preview.warnings ?? []).map((warning, i) => (
              <p className="notice notice-warning" key={i}>
                {warning}
              </p>
            ))}
            {preview.safe_to_commit === false && (
              <p className="notice notice-warning">
                Импорт заблокирован проверкой исходников. Исправьте замечания и
                повторите проверку.
              </p>
            )}
            {[
              ...(preview.secret_warnings ?? []),
              ...(preview.controller_warnings ?? []),
              ...(preview.complexity_warnings ?? []),
            ].map((warning, i) => (
              <p className="notice notice-warning" key={`check-${i}`}>
                {warning.message || warning.code}
              </p>
            ))}
            {preview.files?.slice(0, 30).map((item) => (
              <code key={item.path}>{item.path}</code>
            ))}
            <JsonDetails
              data={preview}
              label="Результаты проверки исходников"
            />
            <Button
              variant="primary"
              loading={commit.isPending}
              disabled={
                !preview.content_hash || preview.safe_to_commit === false
              }
              onClick={() => commit.mutate()}
            >
              Импортировать проверенную версию
            </Button>
          </div>
        </Panel>
      )}
    </div>
  );
}
function PlaybookTemplates() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("templates");
  const [recipe, setRecipe] = useState("");
  const [params, setParams] = useState<Values>({});
  const query = useQuery({
    queryKey: ["automation", "playbook-templates"],
    queryFn: ({ signal }) =>
      api.get<{ templates: Template[] }>(`${playbookBase}templates/`, signal),
  });
  const guided = useQuery({
    queryKey: ["automation", "guided"],
    queryFn: ({ signal }) =>
      api.get<{
        recipes: (Template & {
          fields: {
            key: string;
            label: string;
            type?: string;
            placeholder?: string;
            required?: boolean;
            options?: string[];
            default?: string | boolean;
          }[];
        })[];
      }>(`${playbookBase}guided/`, signal),
  });
  const install = useMutation({
    mutationFn: (slug: string) =>
      api.post<{ playbook: Playbook }>(
        `${playbookBase}templates/${slug}/install/`,
      ),
    onSuccess: (data) => navigate(`/automation/playbooks/${data.playbook.id}`),
  });
  const generate = useMutation({
    mutationFn: () =>
      api.post<{ playbook: Playbook }>(`${playbookBase}guided/generate/`, {
        slug: recipe,
        params,
        save: true,
      }),
    onSuccess: (data) => navigate(`/automation/playbooks/${data.playbook.id}`),
  });
  return (
    <>
      <Tabs
        items={[
          { value: "templates", label: "Готовые шаблоны" },
          { value: "guided", label: "Генератор" },
        ]}
        value={tab}
        onChange={setTab}
      />
      <Feedback
        error={install.error || generate.error || query.error || guided.error}
      />
      {tab === "templates" ? (
        <div className="auto-template-list">
          {query.isPending ? (
            <Skeleton />
          ) : (
            (query.data?.templates ?? []).map((t) => (
              <article className="auto-template" key={t.slug}>
                <h3>{t.name}</h3>
                <p>{t.description}</p>
                <Button
                  size="sm"
                  loading={install.isPending && install.variables === t.slug}
                  onClick={() => install.mutate(t.slug)}
                >
                  <Copy size={13} />
                  Добавить в библиотеку
                </Button>
              </article>
            ))
          )}
        </div>
      ) : (
        <form
          className="auto-form"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            generate.mutate();
          }}
        >
          <Field label="Рецепт" htmlFor="recipe-select">
            <select
              id="recipe-select"
              value={recipe}
              required
              onChange={(e) => {
                setRecipe(e.target.value);
                setParams(
                  Object.fromEntries(
                    (
                      guided.data?.recipes.find(
                        (r) => r.slug === e.target.value,
                      )?.fields ?? []
                    ).map((f) => [f.key, f.default ?? ""]),
                  ),
                );
              }}
            >
              <option value="">Выберите рецепт</option>
              {(guided.data?.recipes ?? []).map((r) => (
                <option key={r.slug} value={r.slug}>
                  {r.name}
                </option>
              ))}
            </select>
          </Field>
          {recipe && (
            <p className="muted">
              {guided.data?.recipes.find((r) => r.slug === recipe)?.description}
            </p>
          )}
          <div className="auto-form">
            {(
              guided.data?.recipes.find((r) => r.slug === recipe)?.fields ?? []
            ).map((field) =>
              field.type === "checkbox" ? (
                <label className="auto-check-row" key={field.key}>
                  <input
                    type="checkbox"
                    checked={params[field.key] === true}
                    onChange={(e) =>
                      setParams({ ...params, [field.key]: e.target.checked })
                    }
                  />
                  {field.label}
                </label>
              ) : (
                <Field
                  key={field.key}
                  label={field.label}
                  htmlFor={`recipe-${field.key}`}
                >
                  {field.type === "select" ? (
                    <select
                      id={`recipe-${field.key}`}
                      value={String(params[field.key] ?? "")}
                      onChange={(e) =>
                        setParams({ ...params, [field.key]: e.target.value })
                      }
                    >
                      {field.options?.map((option) => (
                        <option key={option}>{option}</option>
                      ))}
                    </select>
                  ) : field.type === "textarea" ? (
                    <textarea
                      id={`recipe-${field.key}`}
                      required={field.required}
                      placeholder={field.placeholder}
                      value={String(params[field.key] ?? "")}
                      onChange={(e) =>
                        setParams({ ...params, [field.key]: e.target.value })
                      }
                    />
                  ) : (
                    <input
                      id={`recipe-${field.key}`}
                      required={field.required}
                      placeholder={field.placeholder}
                      value={String(params[field.key] ?? "")}
                      onChange={(e) =>
                        setParams({ ...params, [field.key]: e.target.value })
                      }
                    />
                  )}
                </Field>
              ),
            )}
          </div>
          <Button
            type="submit"
            variant="primary"
            loading={generate.isPending}
            disabled={!recipe}
          >
            Создать из рецепта
          </Button>
        </form>
      )}
    </>
  );
}
