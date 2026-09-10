import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  Archive,
  Check,
  Copy,
  Download,
  Play,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import { useUnsavedEdits, confirmDiscardEdits } from "./unsaved";
import { api, ApiError } from "@/api/client";
import {
  automationApi,
  playbookBase,
  type Playbook,
  type PlaybookDraft,
  type Task,
  type Revision,
} from "@/api/automation";
import {
  Button,
  ConfirmDialog,
  DataTable,
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
import {
  PlaybookLaunch,
  BindingProfiles,
  PlaybookShares,
} from "./PlaybookOperations";
import { PlaybookCompatibility, GitlabRefresh } from "./PlaybookCompatibility";

export function PlaybookWorkspace() {
  const { id } = useParams();
  const numericId = Number(id);
  const query = useQuery({
    queryKey: ["automation", "playbook", numericId],
    queryFn: ({ signal }) => automationApi.playbook(numericId, signal),
  });
  const [tab, setTab] = useState("content");
  const [launch, setLaunch] = useState(false);
  const [archive, setArchive] = useState(false);
  const navigate = useNavigate();
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: (action: string) =>
      api.post<{ playbook?: Playbook }>(
        `${playbookBase}${numericId}/${action}/`,
      ),
    onSuccess: (data, action) => {
      void client.invalidateQueries({ queryKey: ["automation", "playbooks"] });
      if (action === "delete")
        navigate("/automation/playbooks", {
          state: {
            archived: {
              id: numericId,
              name: query.data?.playbook.name ?? "Плейбук",
            },
          },
        });
      else if (data.playbook)
        navigate(`/automation/playbooks/${data.playbook.id}`);
    },
  });
  if (query.isPending) return <Skeleton />;
  if (query.error)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  const pb = query.data!.playbook;
  const caps = pb.capabilities;
  const tabs = [
    { value: "content", label: "Содержимое" },
    { value: "revisions", label: "Версии" },
    ...(pb.kind === "ansible" && caps.can_validate
      ? [{ value: "compatibility", label: "Совместимость" }]
      : []),
    ...(caps.can_edit && pb.source?.type === "gitlab"
      ? [{ value: "source", label: "GitLab" }]
      : []),
    ...(caps.can_edit || caps.can_run
      ? [{ value: "bindings", label: "Профили запуска" }]
      : []),
    ...(caps.can_share ? [{ value: "shares", label: "Доступ" }] : []),
  ];
  return (
    <>
      <PageHeader
        eyebrow="Автоматизация / Плейбуки"
        title={pb.name}
        description={
          pb.description || "Управление инструкциями, версиями и запуском."
        }
        actions={
          <>
            <Link className="btn btn-ghost" to="/automation/playbooks">
              К библиотеке
            </Link>
            {caps.can_export && (
              <Button
                onClick={() => mutation.mutate("duplicate")}
                loading={mutation.isPending}
              >
                <Copy size={14} />
                Копия
              </Button>
            )}
            {caps.can_run && (
              <Button variant="primary" onClick={() => setLaunch(true)}>
                <Play size={14} />
                Запустить
              </Button>
            )}
          </>
        }
      />
      <Feedback error={mutation.error} />
      <Tabs
        items={tabs}
        value={tab}
        onChange={(value) => {
          if (confirmDiscardEdits()) setTab(value);
        }}
      />
      {tab === "content" ? (
        <div className="auto-detail-grid">
          <div>
            {caps.can_edit ? (
              <EditableDraft playbook={pb} />
            ) : (
              <Panel title="Опубликованная версия">
                <pre className="auto-source">
                  {pb.source_yaml ||
                    pb.tasks?.map((t) => t.command).join("\n\n") ||
                    "Нет опубликованного содержимого"}
                </pre>
              </Panel>
            )}
          </div>
          <Panel title="Сведения">
            <div className="auto-summary">
              <dl>
                <div>
                  <dt>Тип</dt>
                  <dd>{pb.kind === "ansible" ? "Ansible" : "Runbook"}</dd>
                </div>
                <div>
                  <dt>Публикация</dt>
                  <dd>
                    {pb.published_revision_number
                      ? `Версия ${pb.published_revision_number}`
                      : "Не опубликован"}
                  </dd>
                </div>
                <div>
                  <dt>Черновик</dt>
                  <dd>
                    <StatusBadge
                      status={pb.has_unpublished_draft ? "draft" : "success"}
                    >
                      {pb.has_unpublished_draft
                        ? "Есть изменения"
                        : "Совпадает с публикацией"}
                    </StatusBadge>
                  </dd>
                </div>
                <div>
                  <dt>Последний запуск</dt>
                  <dd>
                    <StatusBadge status={pb.last_run_status || "unknown"} />
                  </dd>
                </div>
                <div>
                  <dt>Изменён</dt>
                  <dd>{formatDate(pb.updated_at)}</dd>
                </div>
                <div>
                  <dt>Права</dt>
                  <dd>
                    {caps.is_owner
                      ? "Владелец"
                      : caps.can_edit
                        ? "Редактор"
                        : caps.can_run
                          ? "Оператор"
                          : "Чтение"}
                  </dd>
                </div>
              </dl>
              {pb.tags.length > 0 && (
                <div className="auto-tags">
                  {pb.tags.map((tag) => (
                    <span className="auto-tag" key={tag}>
                      {tag}
                    </span>
                  ))}
                </div>
              )}
              {caps.can_edit && <MetadataEditor playbook={pb} />}
              <Link to={`/automation/runs?playbook=${pb.id}`}>
                История запусков →
              </Link>
              {caps.can_delete && (
                <Button variant="ghost" onClick={() => setArchive(true)}>
                  <Archive size={14} />
                  Архивировать плейбук
                </Button>
              )}
            </div>
          </Panel>
        </div>
      ) : tab === "revisions" ? (
        <RevisionHistory playbook={pb} />
      ) : tab === "compatibility" ? (
        <PlaybookCompatibility playbook={pb} />
      ) : tab === "source" ? (
        <GitlabRefresh playbook={pb} />
      ) : tab === "bindings" ? (
        <BindingProfiles playbook={pb} />
      ) : (
        <PlaybookShares playbook={pb} />
      )}
      <PlaybookLaunch playbook={pb} open={launch} onOpenChange={setLaunch} />
      <ConfirmDialog
        open={archive}
        onOpenChange={setArchive}
        title="Архивировать плейбук?"
        description="Плейбук исчезнет из библиотеки. Существующие отчёты запусков останутся доступными."
        typedText={pb.name}
        confirmLabel="Архивировать"
        pending={mutation.isPending}
        onConfirm={() => mutation.mutate("delete")}
      />
    </>
  );
}
function MetadataEditor({ playbook }: { playbook: Playbook }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(playbook.name);
  const [description, setDescription] = useState(playbook.description);
  const [tags, setTags] = useState(playbook.tags.join(", "));
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: () =>
      automationApi.updatePlaybook(playbook.id, {
        name,
        description,
        tags: tags
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      }),
    onSuccess: () => {
      void client.invalidateQueries({
        queryKey: ["automation", "playbook", playbook.id],
      });
      void client.invalidateQueries({ queryKey: ["automation", "playbooks"] });
      setOpen(false);
    },
  });
  return (
    <details open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>Название и описание</summary>
      <form
        className="auto-form"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <Field label="Название" htmlFor="metadata-name">
          <input
            id="metadata-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field label="Описание" htmlFor="metadata-description">
          <textarea
            id="metadata-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <Field label="Теги через запятую" htmlFor="metadata-tags">
          <input
            id="metadata-tags"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
          />
        </Field>
        <Feedback error={save.error} />
        <Button type="submit" loading={save.isPending}>
          Сохранить сведения
        </Button>
      </form>
    </details>
  );
}
function EditableDraft({ playbook }: { playbook: Playbook }) {
  const draft = useQuery({
    queryKey: ["automation", "playbook-draft", playbook.id],
    queryFn: ({ signal }) => automationApi.draft(playbook.id, signal),
    refetchOnWindowFocus: false,
  });
  if (draft.isPending) return <Skeleton />;
  if (draft.error)
    return (
      <ErrorState error={draft.error} retry={() => void draft.refetch()} />
    );
  return draft.data!.draft.asset_bundle_id ? (
    <BundleEditor playbook={playbook} draft={draft.data!.draft} />
  ) : (
    <SourceEditor
      key={draft.data!.draft.version}
      playbook={playbook}
      draft={draft.data!.draft}
    />
  );
}
function SourceEditor({
  playbook,
  draft,
}: {
  playbook: Playbook;
  draft: PlaybookDraft;
}) {
  const [source, setSource] = useState(draft.source_yaml);
  const [tasks, setTasks] = useState(draft.tasks);
  const [success, setSuccess] = useState("");
  const client = useQueryClient();
  const dirty =
    source !== draft.source_yaml ||
    JSON.stringify(tasks) !== JSON.stringify(draft.tasks);
  useUnsavedEdits(dirty);
  const save = useMutation({
    mutationFn: () =>
      automationApi.saveDraft(playbook.id, {
        expected_draft_version: draft.version,
        source_yaml: source,
        tasks,
      }),
    onSuccess: (data) => {
      client.setQueryData(["automation", "playbook-draft", playbook.id], data);
      void client.invalidateQueries({
        queryKey: ["automation", "playbook", playbook.id],
      });
      setSuccess("Черновик сохранён");
    },
  });
  const update = (index: number, partial: Partial<Task>) =>
    setTasks(tasks.map((t, i) => (i === index ? { ...t, ...partial } : t)));
  const move = (index: number, delta: number) => {
    const next = [...tasks];
    [next[index], next[index + delta]] = [next[index + delta], next[index]];
    setTasks(next);
  };
  return (
    <Panel>
      <div className="auto-editor-header">
        <span className="mono">
          {draft.content_format.includes("runbook") ||
          playbook.kind === "runbook"
            ? "runbook"
            : draft.entrypoint}
        </span>
        <StatusBadge status={dirty ? "draft" : "success"}>
          {dirty ? "Не сохранено" : `Черновик v${draft.version}`}
        </StatusBadge>
      </div>
      {playbook.kind === "runbook" ? (
        <div className="auto-pad auto-form">
          {tasks.map((task, index) => (
            <div className="auto-task" key={task.id}>
              <div className="auto-task-head">
                <strong>Шаг {index + 1}</strong>
                <div className="auto-toolbar">
                  <Button
                    size="icon"
                    variant="ghost"
                    disabled={index === 0}
                    aria-label="Переместить выше"
                    onClick={() => move(index, -1)}
                  >
                    <ArrowUp size={13} />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    disabled={index === tasks.length - 1}
                    aria-label="Переместить ниже"
                    onClick={() => move(index, 1)}
                  >
                    <ArrowDown size={13} />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={`Удалить шаг ${index + 1}`}
                    onClick={() =>
                      setTasks(tasks.filter((_, i) => i !== index))
                    }
                  >
                    <Trash2 size={14} />
                  </Button>
                </div>
              </div>
              <Field label="Описание" htmlFor={`task-description-${task.id}`}>
                <input
                  id={`task-description-${task.id}`}
                  value={task.description}
                  onChange={(e) =>
                    update(index, { description: e.target.value })
                  }
                />
              </Field>
              <Field label="Команда" htmlFor={`task-command-${task.id}`}>
                <textarea
                  id={`task-command-${task.id}`}
                  className="mono"
                  value={task.command}
                  onChange={(e) => update(index, { command: e.target.value })}
                />
              </Field>
              <label className="auto-check-row">
                <input
                  type="checkbox"
                  checked={task.continue_on_error}
                  onChange={(e) =>
                    update(index, { continue_on_error: e.target.checked })
                  }
                />
                Продолжить при ошибке
              </label>
            </div>
          ))}
          <Button
            onClick={() =>
              setTasks([
                ...tasks,
                {
                  id: crypto.randomUUID(),
                  command: "",
                  description: "",
                  continue_on_error: false,
                },
              ])
            }
          >
            <Plus size={14} />
            Добавить шаг
          </Button>
        </div>
      ) : (
        <textarea
          aria-label="Редактор Ansible YAML"
          className="auto-editor"
          spellCheck={false}
          value={source}
          onChange={(e) => setSource(e.target.value)}
        />
      )}
      <div className="auto-pad">
        <Feedback error={save.error} success={success} />
        {save.error instanceof ApiError && save.error.status === 409 && (
          <p className="notice notice-warning">
            Черновик изменён другим редактором. Ваш текст сохранён в этом
            редакторе. Скопируйте изменения перед загрузкой новой версии.
          </p>
        )}
      </div>
      <div className="auto-action-strip">
        <Button
          variant="primary"
          loading={save.isPending}
          disabled={!dirty}
          onClick={() => save.mutate()}
        >
          <Save size={14} />
          Сохранить черновик
        </Button>
        <span className="auto-muted">Публикация — на вкладке «Версии».</span>
      </div>
    </Panel>
  );
}
interface FileTree {
  bundle_hash: string;
  draft_version: number;
  entrypoint: string;
  files: {
    path: string;
    editable: boolean;
    is_text: boolean;
    size_bytes: number;
  }[];
}
function BundleEditor({
  playbook,
  draft,
}: {
  playbook: Playbook;
  draft: PlaybookDraft;
}) {
  const [path, setPath] = useState(draft.entrypoint);
  const [view, setView] = useState("current");
  const tree = useQuery({
    queryKey: ["automation", "playbook-files", playbook.id, view],
    queryFn: ({ signal }) =>
      api.get<{ tree: FileTree }>(
        `${playbookBase}${playbook.id}/draft/files/?view=${view}`,
        signal,
      ),
    refetchOnWindowFocus: false,
  });
  const file = useQuery({
    queryKey: ["automation", "playbook-file", playbook.id, view, path],
    queryFn: ({ signal }) =>
      api.get<{
        file: {
          path: string;
          content: string;
          sha256: string;
          draft_version: number;
        };
      }>(
        `${playbookBase}${playbook.id}/draft/file/?view=${view}&path=${encodeURIComponent(path)}`,
        signal,
      ),
    refetchOnWindowFocus: false,
  });
  return (
    <Panel>
      <div className="auto-editor-header">
        <strong>Файлы проекта</strong>
        <select
          className="auto-inline-input"
          aria-label="Версия файлов"
          value={view}
          onChange={(e) => {
            if (confirmDiscardEdits()) setView(e.target.value);
          }}
        >
          <option value="current">Текущий черновик</option>
          <option value="base">Базовая версия</option>
          <option value="published">Опубликованная версия</option>
        </select>
      </div>
      <div className="auto-files-grid">
        <aside className="auto-file-sidebar">
          {tree.isPending ? (
            <Skeleton rows={3} />
          ) : tree.error ? (
            <ErrorState error={tree.error} />
          ) : (
            <div className="auto-file-list">
              {tree.data?.tree.files.map((item) => (
                <button
                  className={path === item.path ? "active" : ""}
                  key={item.path}
                  disabled={!item.is_text}
                  onClick={() => {
                    if (confirmDiscardEdits()) setPath(item.path);
                  }}
                >
                  {item.path}
                </button>
              ))}
            </div>
          )}
        </aside>
        <div>
          {file.isPending ? (
            <Skeleton />
          ) : file.error ? (
            <ErrorState error={file.error} />
          ) : tree.data && file.data ? (
            <BundleFileEditor
              key={`${view}:${path}:${file.data.file.sha256}`}
              playbookId={playbook.id}
              path={path}
              content={file.data.file.content}
              tree={tree.data.tree}
              editable={
                view === "current" &&
                !!tree.data.tree.files.find((f) => f.path === path)?.editable
              }
            />
          ) : null}
        </div>
      </div>
    </Panel>
  );
}
function BundleFileEditor({
  playbookId,
  path,
  content,
  tree,
  editable,
}: {
  playbookId: number;
  path: string;
  content: string;
  tree: FileTree;
  editable: boolean;
}) {
  const [text, setText] = useState(content);
  const client = useQueryClient();
  const dirty = text !== content;
  useUnsavedEdits(dirty);
  const save = useMutation({
    mutationFn: () =>
      api.patch(`${playbookBase}${playbookId}/draft/file/`, {
        path,
        content: text,
        expected_draft_version: tree.draft_version,
        expected_bundle_hash: tree.bundle_hash,
      }),
    onSuccess: () => {
      void client.invalidateQueries({
        queryKey: ["automation", "playbook-file", playbookId],
      });
      void client.invalidateQueries({
        queryKey: ["automation", "playbook-files", playbookId],
      });
      void client.invalidateQueries({
        queryKey: ["automation", "playbook-draft", playbookId],
      });
    },
  });
  return (
    <>
      <div className="auto-editor-header">
        <code>{path}</code>
        <StatusBadge status={dirty ? "draft" : "success"}>
          {dirty ? "Не сохранено" : editable ? "Черновик" : "Только чтение"}
        </StatusBadge>
      </div>
      <textarea
        aria-label={`Содержимое ${path}`}
        className="auto-editor"
        readOnly={!editable}
        value={text}
        onChange={(e) => setText(e.target.value)}
        spellCheck={false}
      />
      <div className="auto-pad">
        <Feedback error={save.error} />
        {save.error instanceof ApiError && save.error.status === 409 && (
          <p className="notice notice-warning">
            Файлы изменились. Скопируйте локальный текст, затем обновите список
            файлов.
          </p>
        )}
      </div>
      {editable && (
        <div className="auto-action-strip">
          <Button
            variant="primary"
            disabled={!dirty}
            loading={save.isPending}
            onClick={() => save.mutate()}
          >
            <Save size={14} />
            Сохранить файл
          </Button>
        </div>
      )}
    </>
  );
}
function RevisionHistory({ playbook }: { playbook: Playbook }) {
  const query = useQuery({
    queryKey: ["automation", "revisions", playbook.id],
    queryFn: ({ signal }) => automationApi.revisions(playbook.id, signal),
  });
  const [message, setMessage] = useState("");
  const [decision, setDecision] = useState<{
    action: string;
    revision: Revision;
  } | null>(null);
  const [selected, setSelected] = useState<Revision | null>(null);
  const client = useQueryClient();
  const refresh = () => {
    void client.invalidateQueries({
      queryKey: ["automation", "revisions", playbook.id],
    });
    void client.invalidateQueries({
      queryKey: ["automation", "playbook", playbook.id],
    });
    void client.invalidateQueries({
      queryKey: ["automation", "playbook-draft", playbook.id],
    });
  };
  const create = useMutation({
    mutationFn: async () => {
      const data = await automationApi.draft(playbook.id);
      return automationApi.createRevision(playbook.id, {
        expected_version: data.draft.version,
        message,
      });
    },
    onSuccess: () => {
      setMessage("");
      refresh();
    },
  });
  const action = useMutation({
    mutationFn: () =>
      api.post(
        `${playbookBase}${playbook.id}/revisions/${decision!.revision.id}/${decision!.action}/`,
        { message },
      ),
    onSuccess: () => {
      setDecision(null);
      refresh();
    },
  });
  const view = useMutation({
    mutationFn: (revision: number) =>
      api.get<{ revision: Revision }>(
        `${playbookBase}${playbook.id}/revisions/${revision}/`,
      ),
    onSuccess: (data) => setSelected(data.revision),
  });
  return (
    <div className="auto-stack">
      <Feedback error={create.error || action.error || view.error} />
      {playbook.capabilities.can_edit && (
        <Panel title="Сохранить версию">
          <form
            className="auto-pad auto-toolbar"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <input
              className="auto-inline-input"
              aria-label="Комментарий версии"
              placeholder="Что изменилось в этой версии?"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
            <Button type="submit" loading={create.isPending}>
              <Plus size={14} />
              Создать версию из черновика
            </Button>
          </form>
        </Panel>
      )}
      <Panel title="История версий">
        {query.isPending ? (
          <Skeleton />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : (
          <DataTable
            rows={query.data?.revisions ?? []}
            rowKey={(r) => r.id}
            emptyTitle="Версий пока нет"
            columns={[
              {
                key: "revision",
                label: "Версия",
                render: (r) => (
                  <>
                    <strong>v{r.revision_number}</strong>
                    {r.id === query.data?.published_revision_id && (
                      <small>
                        <StatusBadge status="success">Опубликована</StatusBadge>
                      </small>
                    )}
                  </>
                ),
              },
              {
                key: "message",
                label: "Изменения",
                render: (r) => r.message || "Без комментария",
              },
              {
                key: "author",
                label: "Автор",
                render: (r) => r.author_username || "—",
              },
              {
                key: "created",
                label: "Создана",
                render: (r) => formatDate(r.created_at),
              },
              {
                key: "actions",
                label: "Действия",
                render: (r) => (
                  <div className="auto-revision-actions">
                    <Button size="sm" onClick={() => view.mutate(r.id)}>
                      Открыть
                    </Button>
                    {playbook.capabilities.can_publish &&
                      r.id !== query.data?.published_revision_id && (
                        <>
                          <Button
                            size="sm"
                            onClick={() =>
                              setDecision({ action: "publish", revision: r })
                            }
                          >
                            <Check size={13} />
                            Опубликовать
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() =>
                              setDecision({ action: "rollback", revision: r })
                            }
                          >
                            Восстановить
                          </Button>
                        </>
                      )}
                    {playbook.capabilities.can_export && (
                      <a
                        className="btn btn-ghost btn-sm"
                        href={`${playbookBase}${playbook.id}/revisions/${r.id}/export/`}
                        download
                        aria-label={`Скачать версию ${r.revision_number}`}
                      >
                        <Download size={14} />
                      </a>
                    )}
                  </div>
                ),
              },
            ]}
          />
        )}
      </Panel>
      {selected && (
        <Panel
          title={`Версия ${selected.revision_number}`}
          actions={
            <Button size="sm" onClick={() => setSelected(null)}>
              Закрыть
            </Button>
          }
        >
          <pre className="auto-source">
            {selected.source_yaml ||
              selected.tasks?.map((t) => t.command).join("\n\n")}
          </pre>
          <div className="auto-pad">
            <JsonDetails
              data={{
                content_hash: selected.content_hash,
                bundle_hash: selected.bundle_hash,
              }}
              label="Контрольные суммы"
            />
          </div>
        </Panel>
      )}
      <ConfirmDialog
        open={!!decision}
        onOpenChange={(v) => !v && setDecision(null)}
        title={
          decision?.action === "publish"
            ? "Опубликовать версию?"
            : "Восстановить версию?"
        }
        description={`Версия ${decision?.revision.revision_number} ${decision?.action === "publish" ? "станет доступна для запусков и пользователей с доступом к плейбуку." : "станет основой восстановленного содержимого."}`}
        pending={action.isPending}
        onConfirm={() => action.mutate()}
        confirmLabel={
          decision?.action === "publish" ? "Опубликовать" : "Восстановить"
        }
      />
    </div>
  );
}
