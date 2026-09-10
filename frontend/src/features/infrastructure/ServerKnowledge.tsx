import { useState, type FormEvent } from "react";
import {
  useIsMutating,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { BookOpen, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import type { ServerDetail } from "@/api/infrastructure";
import {
  serverOperationsApi,
  type KnowledgeInput,
  type KnowledgeItem,
} from "@/api/server-operations";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
  EmptyState,
  ErrorState,
  Feedback,
  Field,
  LoadingState,
  Panel,
  StatusBadge,
} from "@/components/ui";
import "./server-operations.css";
import { useUnsavedEditsBlocker } from "@/features/automation/unsaved";

function KnowledgeEditor({
  server,
  item,
  categories,
  onSaved,
  onCancel,
}: {
  server: ServerDetail;
  item: KnowledgeItem | null;
  categories: { value: string; label: string }[];
  onSaved: () => void;
  onCancel: () => void;
}) {
  const client = useQueryClient();
  const [value, setValue] = useState<KnowledgeInput>({
    title: item?.title || "",
    content: item?.content || "",
    category: item?.category || "other",
    is_active: item?.is_active ?? true,
    confidence: item?.confidence ?? 1,
  });
  const [initial] = useState(() => JSON.stringify(value));
  const [discard, setDiscard] = useState(false);
  const dirty = initial !== JSON.stringify(value);
  const mutation = useMutation({
    mutationKey: ["server-workspace", server.id],
    mutationFn: () =>
      item
        ? serverOperationsApi.updateKnowledge(server.id, item.id, value)
        : serverOperationsApi.createKnowledge(server.id, value),
    onSuccess: () => {
      void client.invalidateQueries({
        queryKey: ["server-knowledge", server.id],
      });
      onSaved();
    },
  });
  const blocker = useUnsavedEditsBlocker(dirty || mutation.isPending);
  function close() {
    if (mutation.isPending) return;
    if (dirty) setDiscard(true);
    else onCancel();
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (
      !value.title.trim() ||
      !value.content.trim() ||
      mutation.isPending ||
      (item && !dirty)
    )
      return;
    mutation.mutate();
  }
  return (
    <>
      <Drawer
        open
        onOpenChange={(open) => !open && close()}
        closeDisabled={mutation.isPending}
        title={item ? "Изменить знание" : "Добавить знание"}
        description={server.name}
        wide
      >
        <form onSubmit={submit}>
          <fieldset
            className="stack"
            disabled={mutation.isPending}
            style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}
          >
            <Field label="Заголовок" htmlFor="knowledge-title">
              <input
                id="knowledge-title"
                value={value.title}
                onChange={(e) => setValue({ ...value, title: e.target.value })}
                maxLength={200}
                required
                autoFocus
              />
            </Field>
            <Field label="Категория" htmlFor="knowledge-category">
              <select
                id="knowledge-category"
                value={value.category}
                onChange={(e) =>
                  setValue({ ...value, category: e.target.value })
                }
              >
                {categories.map((category) => (
                  <option key={category.value} value={category.value}>
                    {category.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field
              label="Содержание"
              htmlFor="knowledge-content"
              description={`${value.content.length} / 8000 символов. Добавляйте факты и рабочий контекст без паролей и токенов.`}
            >
              <textarea
                id="knowledge-content"
                value={value.content}
                onChange={(e) =>
                  setValue({ ...value, content: e.target.value })
                }
                required
                maxLength={8000}
                rows={15}
              />
            </Field>
            {item && (
              <details>
                <summary>Дополнительно</summary>
                <Field
                  label="Достоверность, %"
                  htmlFor="knowledge-confidence"
                  description="Оценка надёжности факта для AI: от 0 до 100%."
                >
                  <input
                    id="knowledge-confidence"
                    type="number"
                    min="0"
                    max="100"
                    step="1"
                    required
                    value={Math.round((value.confidence ?? 1) * 100)}
                    onChange={(e) =>
                      setValue({
                        ...value,
                        confidence: Number(e.target.value) / 100,
                      })
                    }
                  />
                </Field>
              </details>
            )}
            <label className="row">
              <input
                type="checkbox"
                checked={value.is_active}
                onChange={(e) =>
                  setValue({ ...value, is_active: e.target.checked })
                }
              />
              Использовать в контексте AI
            </label>
            <Feedback error={mutation.error} />
            <div className="row">
              <Button
                variant="primary"
                type="submit"
                loading={mutation.isPending}
                disabled={
                  !value.title.trim() ||
                  !value.content.trim() ||
                  (!!item && !dirty)
                }
              >
                Сохранить
              </Button>
              <Button onClick={close} disabled={mutation.isPending}>
                Отмена
              </Button>
            </div>
          </fieldset>
        </form>
      </Drawer>
      <ConfirmDialog
        open={discard || blocker.state === "blocked"}
        onOpenChange={(open) => {
          if (!open && !mutation.isPending) {
            setDiscard(false);
            if (blocker.state === "blocked") blocker.reset();
          }
        }}
        title={
          mutation.isPending ? "Знание сохраняется" : "Закрыть без сохранения?"
        }
        description={
          mutation.isPending
            ? "Дождитесь завершения запроса."
            : "Изменения текста и настроек знания будут потеряны."
        }
        confirmLabel="Не сохранять"
        pending={mutation.isPending}
        onConfirm={() => {
          if (mutation.isPending) return;
          if (blocker.state === "blocked") blocker.proceed();
          else onCancel();
        }}
      />
    </>
  );
}
export function ServerKnowledge({ server }: { server: ServerDetail }) {
  const client = useQueryClient();
  const [inactive, setInactive] = useState(false);
  const [editor, setEditor] = useState<KnowledgeItem | "new" | null>(null);
  const [detail, setDetail] = useState<KnowledgeItem | null>(null);
  const [remove, setRemove] = useState<KnowledgeItem | null>(null);
  const pending =
    useIsMutating({ mutationKey: ["server-workspace", server.id] }) > 0;
  const query = useQuery({
    queryKey: ["server-knowledge", server.id, inactive],
    queryFn: ({ signal }) =>
      serverOperationsApi.knowledge(server.id, inactive, signal),
    enabled: server.can_edit,
    retry: false,
  });
  const deletion = useMutation({
    mutationKey: ["server-workspace", server.id],
    mutationFn: (item: KnowledgeItem) =>
      serverOperationsApi.deleteKnowledge(server.id, item.id),
    onSuccess: () => {
      setRemove(null);
      setDetail(null);
      void client.invalidateQueries({
        queryKey: ["server-knowledge", server.id],
      });
    },
  });
  if (!server.can_edit)
    return (
      <EmptyState
        icon={<BookOpen size={24} />}
        title="Знания управляются владельцем"
        description="Создание и изменение контекста сервера доступны его владельцу."
      />
    );
  return (
    <Panel
      title="Знания о сервере"
      description="Проверенные факты, инструкции и контекст, которые используются AI при работе с этим сервером."
      actions={
        <div className="row">
          <Button
            size="sm"
            onClick={() => void query.refetch()}
            loading={query.isFetching}
          >
            <RefreshCw size={14} />
            Обновить
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!query.data || pending}
            onClick={() => setEditor("new")}
          >
            <Plus size={14} />
            Добавить знание
          </Button>
        </div>
      }
    >
      <div className="stack">
        {query.isPending ? (
          <LoadingState />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : (
          <>
            <DataTable
              rows={query.data?.items || []}
              searchValue={(row) =>
                `${row.title} ${row.content} ${row.category_label}`
              }
              searchPlaceholder="Найти знание…"
              hideSinglePagePagination
              toolbar={
                <label className="row">
                  <input
                    type="checkbox"
                    checked={inactive}
                    disabled={pending}
                    onChange={(e) => setInactive(e.target.checked)}
                  />
                  Показать неактивные
                </label>
              }
              rowKey={(row) => row.id}
              emptyTitle={
                inactive ? "Знания ещё не добавлены" : "Нет активных знаний"
              }
              emptyDescription="Запишите назначение сервера, особенности развёртывания или порядок обслуживания."
              columns={[
                {
                  key: "title",
                  label: "Знание",
                  render: (row) => (
                    <button
                      className="text-link"
                      onClick={() => setDetail(row)}
                    >
                      {row.title}
                    </button>
                  ),
                  sortValue: (row) => row.title,
                },
                {
                  key: "category",
                  label: "Категория",
                  render: (row) => row.category_label,
                },
                {
                  key: "source",
                  label: "Источник",
                  render: (row) => <div>{row.source_label}</div>,
                },
                ...(inactive
                  ? [
                      {
                        key: "active",
                        label: "Состояние",
                        render: (row: KnowledgeItem) => (
                          <StatusBadge
                            status={row.is_active ? "active" : "inactive"}
                          >
                            {row.is_active ? "Используется AI" : "Отключено"}
                          </StatusBadge>
                        ),
                      },
                    ]
                  : []),
                {
                  key: "updated",
                  label: "Изменено",
                  render: (row) =>
                    row.updated_at
                      ? new Date(row.updated_at).toLocaleString("ru-RU")
                      : "—",
                  sortValue: (row) => row.updated_at || "",
                },
                {
                  key: "actions",
                  label: "Действия",
                  render: (row) => (
                    <div className="row">
                      <Button
                        size="icon"
                        aria-label={`Изменить ${row.title}`}
                        disabled={pending}
                        onClick={() => setEditor(row)}
                      >
                        <Pencil size={14} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Удалить ${row.title}`}
                        disabled={pending}
                        onClick={() => {
                          deletion.reset();
                          setRemove(row);
                        }}
                      >
                        <Trash2 size={14} />
                      </Button>
                    </div>
                  ),
                },
              ]}
            />
            {(query.data?.items.length ?? 0) >= 100 && (
              <p className="muted text-sm">Показаны 100 последних записей.</p>
            )}
          </>
        )}
      </div>
      {editor !== null && (
        <KnowledgeEditor
          key={editor === "new" ? "new" : editor.id}
          server={server}
          item={editor === "new" ? null : editor}
          categories={query.data?.categories || []}
          onSaved={() => {
            setEditor(null);
            setDetail(null);
          }}
          onCancel={() => setEditor(null)}
        />
      )}
      <Drawer
        open={detail !== null}
        onOpenChange={(open) => !open && setDetail(null)}
        title={detail?.title || "Знание"}
        description={
          detail ? `${detail.category_label} · ${detail.source_label}` : ""
        }
        wide
      >
        {detail && (
          <div className="stack">
            <div className="spread">
              <StatusBadge status={detail.is_active ? "active" : "inactive"}>
                {detail.is_active ? "Используется AI" : "Отключено"}
              </StatusBadge>
              <Button
                onClick={() => {
                  setEditor(detail);
                  setDetail(null);
                }}
              >
                <Pencil size={14} />
                Изменить
              </Button>
            </div>
            <div className="ops-knowledge-content">{detail.content}</div>
          </div>
        )}
      </Drawer>
      <ConfirmDialog
        open={remove !== null}
        onOpenChange={(open) => !open && !deletion.isPending && setRemove(null)}
        title="Удалить знание?"
        description={
          <>
            <p>
              «{remove?.title}» будет удалено. Связанный ручной снимок памяти
              будет архивирован.
            </p>
            <Feedback error={deletion.error} />
          </>
        }
        confirmLabel="Удалить знание"
        onConfirm={() =>
          remove && !deletion.isPending && deletion.mutate(remove)
        }
        pending={deletion.isPending}
      />
    </Panel>
  );
}
