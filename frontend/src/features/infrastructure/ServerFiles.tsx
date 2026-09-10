import { useEffect, useRef, useState, type FormEvent } from "react";
import { useBlocker } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUp,
  Download,
  File,
  Folder,
  FolderPlus,
  MoreHorizontal,
  RefreshCw,
  Save,
  Upload,
} from "lucide-react";
import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { serverWorkspaceApi, type FileEntry } from "@/api/server-workspace";
import type { ServerDetail } from "@/api/infrastructure";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
  EmptyState,
  ErrorState,
  Feedback,
  Field,
  Panel,
  Skeleton,
} from "@/components/ui";
import { formatDate, formatNumber } from "@/lib/utils";
type Action = {
  type: "rename" | "mkdir" | "chmod" | "chown";
  file?: FileEntry;
};
export function ServerFiles({
  server,
  onDirtyChange,
}: {
  server: ServerDetail;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const client = useQueryClient();
  const [path, setPath] = useState(".");
  const [pathInput, setPathInput] = useState(".");
  const [editing, setEditing] = useState<FileEntry | null>(null);
  const editingPath = useRef<string | null>(null);
  const [content, setContent] = useState("");
  const [original, setOriginal] = useState("");
  const [discard, setDiscard] = useState(false);
  const [action, setAction] = useState<Action | null>(null);
  const [value, setValue] = useState("");
  const [removing, setRemoving] = useState<FileEntry | null>(null);
  const writable = server.capabilities.write_files;
  const query = useQuery({
    queryKey: ["files", server.id, path],
    queryFn: ({ signal }) => serverWorkspaceApi.files(server.id, path, signal),
    enabled: server.capabilities.read_files,
    retry: false,
  });
  const refresh = () =>
    void client.invalidateQueries({ queryKey: ["files", server.id] });
  const read = useMutation({
    mutationFn: (file: FileEntry) =>
      serverWorkspaceApi.read(server.id, file.path),
    onSuccess: (data, file) => {
      if (editingPath.current !== file.path) return;
      setContent(data.file.content);
      setOriginal(data.file.content);
    },
  });
  const save = useMutation({
    mutationKey: ["server-workspace", server.id],
    mutationFn: (submitted: { path: string; content: string }) =>
      serverWorkspaceApi.write(server.id, submitted.path, submitted.content),
    gcTime: 0,
    onSuccess: (_data, submitted) => {
      if (editingPath.current === submitted.path)
        setOriginal(submitted.content);
      refresh();
    },
  });
  const download = useMutation({
    mutationFn: (file: FileEntry) =>
      serverWorkspaceApi.download(server.id, file),
  });
  const upload = useMutation({
    mutationKey: ["server-workspace", server.id],
    mutationFn: (submitted: { path: string; files: globalThis.File[] }) =>
      serverWorkspaceApi.upload(server.id, submitted.path, submitted.files),
    onSuccess: refresh,
  });
  const mutate = useMutation({
    mutationKey: ["server-workspace", server.id],
    mutationFn: () =>
      serverWorkspaceApi.fileAction(server.id, action!.type, {
        path: action?.file?.path ?? query.data?.path ?? path,
        ...(action?.type === "rename"
          ? { new_name: value }
          : action?.type === "mkdir"
            ? { name: value }
            : action?.type === "chmod"
              ? { mode: value }
              : { owner: value }),
      }),
    onSuccess: () => {
      setAction(null);
      refresh();
    },
  });
  const remove = useMutation({
    mutationKey: ["server-workspace", server.id],
    mutationFn: () =>
      serverWorkspaceApi.fileAction(server.id, "delete", {
        path: removing!.path,
        recursive: removing!.is_dir,
      }),
    onSuccess: () => {
      setRemoving(null);
      refresh();
    },
  });
  const dirty = !!editing && content !== original;
  const pending =
    save.isPending || upload.isPending || mutate.isPending || remove.isPending;
  const blocker = useBlocker(dirty || pending);
  useEffect(() => {
    onDirtyChange?.(dirty || pending);
  }, [dirty, pending, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (dirty || pending) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, pending]);
  if (!server.capabilities.read_files)
    return (
      <EmptyState
        title="Нет доступа к файлам"
        description="Владелец сервера должен предоставить разрешение на чтение файлов."
      />
    );
  function open(file: FileEntry) {
    if (file.is_dir) {
      upload.reset();
      setPath(file.path);
      setPathInput(file.path);
    } else {
      editingPath.current = file.path;
      setEditing(file);
      setContent("");
      setOriginal("");
      save.reset();
      read.mutate(file);
    }
  }
  function start(type: Action["type"], file?: FileEntry) {
    setAction({ type, file });
    setValue(
      type === "chmod"
        ? (file?.permissions_octal ?? "0644")
        : type === "rename"
          ? (file?.name ?? "")
          : "",
    );
    mutate.reset();
  }
  function navigate(e: FormEvent) {
    e.preventDefault();
    upload.reset();
    setPath(pathInput || ".");
  }
  return (
    <>
      <Panel
        title="Файлы"
        actions={
          <div className="row">
            <Button
              size="sm"
              aria-label="Обновить список файлов"
              onClick={() => void query.refetch()}
              loading={query.isFetching}
            >
              <RefreshCw size={14} />
            </Button>
            {writable && (
              <>
                <Button
                  size="sm"
                  disabled={upload.isPending}
                  onClick={() => start("mkdir")}
                >
                  <FolderPlus size={14} />
                  Создать папку
                </Button>
                <label className="btn btn-secondary btn-sm">
                  <Upload size={14} />
                  {upload.isPending ? "Загрузка…" : "Загрузить"}
                  <input
                    type="file"
                    multiple
                    className="sr-only"
                    disabled={upload.isPending}
                    onChange={(e) => {
                      if (e.target.files?.length)
                        upload.mutate({
                          path: query.data?.path ?? path,
                          files: Array.from(e.target.files),
                        });
                      e.target.value = "";
                    }}
                  />
                </label>
              </>
            )}
          </div>
        }
      >
        <form className="table-toolbar" onSubmit={navigate}>
          <Button
            size="icon"
            aria-label="Родительская папка"
            disabled={!query.data?.parent_path || upload.isPending}
            onClick={() => {
              upload.reset();
              setPath(query.data!.parent_path!);
              setPathInput(query.data!.parent_path!);
            }}
          >
            <ArrowUp size={15} />
          </Button>
          <input
            className="mono"
            aria-label="Путь к папке"
            disabled={upload.isPending}
            value={pathInput}
            onChange={(e) => setPathInput(e.target.value)}
          />
          <Button type="submit" disabled={upload.isPending}>
            Перейти
          </Button>
        </form>
        {query.isPending ? (
          <Skeleton />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : (
          <DataTable
            rows={query.data?.entries ?? []}
            rowKey={(f) => f.path}
            searchValue={(f) => f.name}
            searchPlaceholder="Найти файл в этой папке…"
            hideSinglePagePagination
            emptyTitle="Папка пуста"
            columns={[
              {
                key: "name",
                label: "Имя",
                sortValue: (f) => f.name,
                render: (f) => (
                  <button
                    className="btn btn-ghost btn-sm"
                    disabled={upload.isPending}
                    onClick={() => open(f)}
                  >
                    {f.is_dir ? <Folder size={16} /> : <File size={16} />}
                    <span className="mono">{f.name}</span>
                  </button>
                ),
              },
              {
                key: "size",
                label: "Размер",
                sortValue: (f) => f.size,
                render: (f) => (f.is_dir ? "—" : `${formatNumber(f.size)} B`),
              },
              {
                key: "mode",
                label: "Права",
                render: (f) => (
                  <span className="mono text-sm">{f.permissions}</span>
                ),
              },
              {
                key: "mtime",
                label: "Изменён",
                sortValue: (f) => f.modified_at,
                render: (f) =>
                  formatDate(new Date(f.modified_at * 1000).toISOString()),
              },
              {
                key: "actions",
                label: "",
                render: (f) => (
                  <div className="table-actions">
                    {!f.is_dir && (
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={`Скачать ${f.name}`}
                        loading={download.isPending}
                        onClick={() => download.mutate(f)}
                      >
                        <Download size={14} />
                      </Button>
                    )}
                    {writable && (
                      <Dropdown.Root>
                        <Dropdown.Trigger asChild>
                          <Button
                            size="icon"
                            variant="ghost"
                            aria-label={`Действия ${f.name}`}
                            disabled={upload.isPending}
                          >
                            <MoreHorizontal size={16} />
                          </Button>
                        </Dropdown.Trigger>
                        <Dropdown.Portal>
                          <Dropdown.Content className="menu-content">
                            <Dropdown.Item
                              className="menu-item"
                              onSelect={() => start("rename", f)}
                            >
                              Переименовать
                            </Dropdown.Item>
                            <Dropdown.Item
                              className="menu-item"
                              onSelect={() => start("chmod", f)}
                            >
                              Права доступа
                            </Dropdown.Item>
                            <Dropdown.Item
                              className="menu-item"
                              onSelect={() => start("chown", f)}
                            >
                              Владелец
                            </Dropdown.Item>
                            <Dropdown.Item
                              className="menu-item text-danger"
                              onSelect={() => {
                                remove.reset();
                                setRemoving(f);
                              }}
                            >
                              Удалить
                            </Dropdown.Item>
                          </Dropdown.Content>
                        </Dropdown.Portal>
                      </Dropdown.Root>
                    )}
                  </div>
                ),
              },
            ]}
          />
        )}
      </Panel>
      <Feedback
        error={download.error ?? upload.error}
        success={
          upload.isSuccess
            ? `Файлы загружены в ${upload.variables.path ?? path}`
            : undefined
        }
      />
      <Drawer
        wide
        open={!!editing}
        onOpenChange={(open) => {
          if (!open) {
            if (save.isPending) return;
            if (content !== original) setDiscard(true);
            else {
              editingPath.current = null;
              setEditing(null);
            }
          }
        }}
        title={editing?.name ?? "Редактор файла"}
        description={editing?.path}
        closeDisabled={save.isPending}
      >
        <div className="stack">
          {read.isPending ? (
            <Skeleton />
          ) : read.error ? (
            <ErrorState
              error={read.error}
              retry={() => editing && read.mutate(editing)}
            />
          ) : (
            <>
              <textarea
                className="mono file-editor"
                aria-label="Содержимое файла"
                readOnly={!writable}
                value={content}
                onChange={(e) => setContent(e.target.value)}
              />
              <div className="spread">
                <span className="muted text-sm">
                  {content !== original
                    ? "Есть несохранённые изменения"
                    : writable
                      ? "Все изменения сохранены"
                      : "Только чтение"}
                </span>
                {writable && (
                  <Button
                    variant="primary"
                    onClick={() =>
                      save.mutate({ path: editing!.path, content })
                    }
                    disabled={content === original}
                    loading={save.isPending}
                  >
                    <Save size={14} />
                    Сохранить
                  </Button>
                )}
              </div>
              <Feedback error={save.error} />
            </>
          )}
        </div>
      </Drawer>
      <ConfirmDialog
        open={discard}
        onOpenChange={setDiscard}
        title="Закрыть без сохранения?"
        description="Изменения в файле будут потеряны."
        confirmLabel="Не сохранять"
        pending={save.isPending}
        onConfirm={() => {
          setDiscard(false);
          editingPath.current = null;
          setEditing(null);
        }}
      />
      <ConfirmDialog
        open={blocker.state === "blocked"}
        onOpenChange={(open) => {
          if (!open && blocker.state === "blocked") blocker.reset();
        }}
        title={
          pending
            ? "Операция с файлами выполняется"
            : "Выйти без сохранения файла?"
        }
        description={
          pending
            ? "Дождитесь завершения операции перед выходом."
            : "Несохранённые изменения в редакторе будут потеряны."
        }
        confirmLabel="Выйти без сохранения"
        pending={pending}
        onConfirm={() => {
          if (!pending && blocker.state === "blocked") blocker.proceed();
        }}
      />
      <Drawer
        open={!!action}
        onOpenChange={(open) => {
          if (!open && !mutate.isPending) setAction(null);
        }}
        closeDisabled={mutate.isPending}
        title={
          action?.type === "mkdir"
            ? "Создать папку"
            : action?.type === "rename"
              ? "Переименовать"
              : action?.type === "chmod"
                ? "Изменить права"
                : "Изменить владельца"
        }
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (value.trim() && !mutate.isPending) mutate.mutate();
          }}
        >
          <fieldset
            className="stack"
            disabled={mutate.isPending}
            style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}
          >
            <p className="mono muted text-sm">
              {action?.file?.path ?? query.data?.path}
            </p>
            <Field
              label={
                action?.type === "chmod"
                  ? "Права в восьмеричной форме"
                  : action?.type === "chown"
                    ? "Владелец:группа"
                    : "Название"
              }
              htmlFor="file-action-value"
            >
              <input
                id="file-action-value"
                required
                autoFocus
                value={value}
                onChange={(e) => setValue(e.target.value)}
                pattern={action?.type === "chmod" ? "[0-7]{3,4}" : undefined}
              />
            </Field>
            <Feedback
              error={
                mutate.error?.message.includes("requires SFTPv4")
                  ? new Error(
                      "Сервер не поддерживает смену владельца по имени через эту версию SFTP. Измените владельца в SSH-терминале.",
                    )
                  : mutate.error
              }
            />
            <div className="row">
              <Button
                variant="primary"
                type="submit"
                loading={mutate.isPending}
                disabled={!value.trim()}
              >
                {action?.type === "mkdir"
                  ? "Создать папку"
                  : action?.type === "rename"
                    ? "Переименовать"
                    : "Применить"}
              </Button>
              <Button onClick={() => setAction(null)}>Отмена</Button>
            </div>
          </fieldset>
        </form>
      </Drawer>
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(open) => {
          if (!open && !remove.isPending) setRemoving(null);
        }}
        title="Удалить с сервера?"
        description={
          <div className="stack">
            <p>
              {removing?.path}
              {removing?.is_dir ? " и всё содержимое папки" : ""}. Это действие
              нельзя отменить.
            </p>
            <Feedback error={remove.error} />
          </div>
        }
        typedText={removing?.name}
        confirmLabel="Удалить"
        pending={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </>
  );
}
