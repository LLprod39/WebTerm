import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type DragEvent as ReactDragEvent,
} from "react";

import {
  chmodServerFile,
  chownServerFile,
  createServerFolder,
  deleteServerFile,
  listServerFiles,
  renameServerFile,
  type FrontendServer,
  type SftpEntry,
  writeServerTextFile,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { DeleteDialog, UnsavedChangesDialog } from "@/components/system/ConfirmDialog";
import { SftpTransferQueue } from "./SftpTransferQueue";
import { SftpDirectoryBrowser } from "./sftp-panel/SftpDirectoryBrowser";
import { SftpActionDialog } from "./sftp-panel/SftpActionDialog";
import { SftpTextEditorSection } from "./sftp-panel/SftpTextEditorSection";
import {
  buildChildPath,
  defaultPermissionMode,
  getSftpBreadcrumbSegments,
  getVisibleSftpEntries,
} from "./sftp-panel/sftpPanelModel";
import { useSftpTransfers } from "./sftp-panel/useSftpTransfers";
import { useSftpTextEditor } from "./sftp-panel/useSftpTextEditor";

export interface SftpPanelHandle {
  enqueueUploads: (files: FileList | File[]) => void;
  refresh: () => void;
}

interface SftpPanelProps {
  server: FrontendServer;
  active?: boolean;
  onOpenInEditor?: (path: string) => void;
}

type SftpFormAction =
  | { type: "create-folder"; value: string; error?: string }
  | { type: "create-file"; value: string; error?: string }
  | { type: "rename"; value: string; entry: SftpEntry; error?: string }
  | { type: "chmod"; value: string; entry: SftpEntry; error?: string }
  | { type: "chown"; value: string; entry: SftpEntry; error?: string };

type PendingEditorAction =
  | { type: "open"; entry: SftpEntry }
  | { type: "reload" }
  | { type: "close" };

function formActionCopy(action: SftpFormAction | null) {
  if (!action) return null;
  switch (action.type) {
    case "create-folder":
      return {
        title: "Новая папка",
        description: "Папка будет создана в текущем каталоге.",
        label: "Имя папки",
        placeholder: "logs",
        confirmLabel: "Создать папку",
      };
    case "create-file":
      return {
        title: "Новый файл",
        description: "Пустой файл будет создан и открыт в редакторе.",
        label: "Имя файла",
        placeholder: "new-file.conf",
        confirmLabel: "Создать файл",
      };
    case "rename":
      return {
        title: "Переименовать объект",
        description: `Текущее имя: ${action.entry.name}`,
        label: "Новое имя",
        placeholder: action.entry.name,
        confirmLabel: "Переименовать",
      };
    case "chmod":
      return {
        title: "Изменить права доступа",
        description: `Права будут применены к ${action.entry.name}. Используйте формат 644, 755 или 0644.`,
        label: "Права",
        placeholder: defaultPermissionMode(action.entry),
        confirmLabel: "Обновить права",
      };
    case "chown":
      return {
        title: "Изменить владельца",
        description: `Владелец будет обновлён для ${action.entry.name}. Можно указать owner или owner:group.`,
        label: "Владелец",
        placeholder: "deploy:www-data",
        confirmLabel: "Обновить владельца",
      };
  }
}

export const SftpPanel = forwardRef<SftpPanelHandle, SftpPanelProps>(function SftpPanel(
  { server, active = true, onOpenInEditor }: SftpPanelProps,
  ref,
) {
  const { toast } = useToast();
  const uploadInputRef = useRef<HTMLInputElement>(null);
  const loadSeqRef = useRef(0);

  const [currentPath, setCurrentPath] = useState(".");
  const [searchQuery, setSearchQuery] = useState("");
  const [homePath, setHomePath] = useState(".");
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [entries, setEntries] = useState<SftpEntry[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState("");
  const [formAction, setFormAction] = useState<SftpFormAction | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<SftpEntry | null>(null);
  const [pendingEditorAction, setPendingEditorAction] = useState<PendingEditorAction | null>(null);
  const [isActionSubmitting, setIsActionSubmitting] = useState(false);

  const selectedEntry = useMemo(
    () => entries.find((entry) => entry.path === selectedPath) || null,
    [entries, selectedPath],
  );

  const visibleEntries = useMemo(() => {
    return getVisibleSftpEntries({ entries, searchQuery, showHidden: true });
  }, [entries, searchQuery]);

  const breadcrumbSegments = useMemo(() => {
    return getSftpBreadcrumbSegments(currentPath);
  }, [currentPath]);

  const loadDirectory = useCallback(async (path: string) => {
    const seq = loadSeqRef.current + 1;
    loadSeqRef.current = seq;
    setIsLoading(true);
    setError("");

    try {
      const result = await listServerFiles(server.id, path);
      if (loadSeqRef.current !== seq) return;
      setCurrentPath(result.path);
      setHomePath(result.home_path);
      setParentPath(result.parent_path);
      setEntries(result.entries);
      setSelectedPath((current) => (result.entries.some((entry) => entry.path === current) ? current : null));
    } catch (err) {
      if (loadSeqRef.current !== seq) return;
      const message = err instanceof Error ? err.message : "Не удалось загрузить файлы";
      setError(message);
    } finally {
      if (loadSeqRef.current === seq) {
        setIsLoading(false);
      }
    }
  }, [server.id]);

  const refreshDirectory = useCallback(() => {
    void loadDirectory(currentPath);
  }, [currentPath, loadDirectory]);

  const {
    closeEditor,
    editorContent,
    editorEncoding,
    editorError,
    editorFilename,
    editorPath,
    editorSizeLabel,
    isEditorDirty,
    isEditorLoading,
    isEditorSaving,
    openTextEditor,
    reloadEditor,
    resetEditor,
    saveEditor,
    setEditorContent,
    setEditorFile,
    syncRenamedEditorPath,
  } = useSftpTextEditor({
    currentPath,
    entries,
    loadDirectory,
    serverId: server.id,
    toast,
  });

  const {
    clearCompletedTransfers,
    enqueueUploadFiles,
    handleCancelOrRemoveTransfer,
    queueDownload,
    resetTransfers,
    retryTransfer,
    setTransfersExpanded,
    transfers,
    transfersExpanded,
  } = useSftpTransfers({
    currentPath,
    loadDirectory,
    serverId: server.id,
    toast,
  });

  useEffect(() => {
    setCurrentPath(".");
    setHomePath(".");
    setParentPath(null);
    setEntries([]);
    setSelectedPath(null);
    resetTransfers();
    setError("");
    resetEditor();
    if (active) {
      void loadDirectory(".");
    }
  }, [active, loadDirectory, resetEditor, resetTransfers, server.id]);

  useEffect(() => {
    if (!active) return;
    if (!entries.length && !isLoading && !error) {
      void loadDirectory(currentPath);
    }
  }, [active, currentPath, entries.length, error, isLoading, loadDirectory]);

  useImperativeHandle(ref, () => ({
    enqueueUploads: (files) => {
      enqueueUploadFiles(files);
    },
    refresh: () => {
      void loadDirectory(currentPath);
    },
  }), [currentPath, enqueueUploadFiles, loadDirectory]);

  const runEditorAction = useCallback((action: PendingEditorAction) => {
    if (action.type === "open") {
      void openTextEditor(action.entry);
      return;
    }
    if (action.type === "reload") {
      void reloadEditor();
      return;
    }
    closeEditor();
  }, [closeEditor, openTextEditor, reloadEditor]);

  const requestEditorAction = useCallback((action: PendingEditorAction) => {
    if (isEditorDirty) {
      setPendingEditorAction(action);
      return;
    }
    runEditorAction(action);
  }, [isEditorDirty, runEditorAction]);

  const handleOpenEditor = useCallback(() => {
    if (!selectedEntry || selectedEntry.is_dir) {
      toast({ variant: "destructive", description: "Выберите текстовый файл." });
      return;
    }
    if (onOpenInEditor) {
      onOpenInEditor(selectedEntry.path);
      return;
    }
    requestEditorAction({ type: "open", entry: selectedEntry });
  }, [onOpenInEditor, requestEditorAction, selectedEntry, toast]);

  const requireSelectedEntry = useCallback(() => {
    if (selectedEntry) return selectedEntry;
    toast({ variant: "destructive", description: "Выберите файл или папку." });
    return null;
  }, [selectedEntry, toast]);

  const handleCreateFolder = useCallback(() => {
    setFormAction({ type: "create-folder", value: "" });
  }, []);

  const handleCreateFile = useCallback(() => {
    setFormAction({ type: "create-file", value: "new-file.conf" });
  }, []);

  const handleRename = useCallback(() => {
    const entry = requireSelectedEntry();
    if (!entry) return;
    setFormAction({ type: "rename", value: entry.name, entry });
  }, [requireSelectedEntry]);

  const handleDelete = useCallback(() => {
    const entry = requireSelectedEntry();
    if (!entry) return;
    setDeleteTarget(entry);
  }, [requireSelectedEntry]);

  const handleChmod = useCallback(() => {
    const entry = requireSelectedEntry();
    if (!entry) return;
    setFormAction({ type: "chmod", value: defaultPermissionMode(entry), entry });
  }, [requireSelectedEntry]);

  const handleChown = useCallback(() => {
    const entry = requireSelectedEntry();
    if (!entry) return;
    setFormAction({ type: "chown", value: "", entry });
  }, [requireSelectedEntry]);

  const updateFormActionError = useCallback((message: string) => {
    setFormAction((current) => current ? { ...current, error: message } : current);
  }, []);

  const handleSubmitFormAction = useCallback(async () => {
    if (!formAction) return;
    const normalizedValue = formAction.value.trim();
    if (!normalizedValue) {
      updateFormActionError("Заполните поле.");
      return;
    }
    if (formAction.type === "chmod" && !/^[0-7]{3,4}$/.test(normalizedValue)) {
      updateFormActionError("Введите права в формате 644, 755 или 0644.");
      return;
    }
    if (formAction.type === "rename" && normalizedValue === formAction.entry.name) {
      setFormAction(null);
      return;
    }

    setIsActionSubmitting(true);
    try {
      if (formAction.type === "create-folder") {
        await createServerFolder(server.id, currentPath, normalizedValue);
        toast({ description: "Папка создана." });
        void loadDirectory(currentPath);
      } else if (formAction.type === "create-file") {
        const nextPath = buildChildPath(currentPath, normalizedValue);
        const result = await writeServerTextFile(server.id, nextPath, "");
        setSelectedPath(result.file.path);
        setEditorFile(result.file);
        toast({ description: "Файл создан." });
        void loadDirectory(currentPath);
        onOpenInEditor?.(result.file.path);
      } else if (formAction.type === "rename") {
        const previousPath = formAction.entry.path;
        const result = await renameServerFile(server.id, formAction.entry.path, normalizedValue);
        setSelectedPath(result.entry?.path || null);
        syncRenamedEditorPath(previousPath, result.entry);
        toast({ description: "Имя обновлено." });
        void loadDirectory(result.path || currentPath);
      } else if (formAction.type === "chmod") {
        const result = await chmodServerFile(server.id, formAction.entry.path, normalizedValue);
        toast({ description: "Права доступа обновлены." });
        void loadDirectory(result.path || currentPath);
      } else {
        const result = await chownServerFile(server.id, formAction.entry.path, normalizedValue, formAction.entry.is_dir);
        toast({ description: "Владелец обновлён." });
        void loadDirectory(result.path || currentPath);
      }
      setFormAction(null);
    } catch (err) {
      updateFormActionError(err instanceof Error ? err.message : "Не удалось выполнить действие.");
    } finally {
      setIsActionSubmitting(false);
    }
  }, [
    currentPath,
    formAction,
    loadDirectory,
    onOpenInEditor,
    server.id,
    setEditorFile,
    syncRenamedEditorPath,
    toast,
    updateFormActionError,
  ]);

  const confirmDelete = useCallback(async () => {
    if (!deleteTarget) return;
    setIsActionSubmitting(true);
    try {
      const result = await deleteServerFile(server.id, deleteTarget.path, deleteTarget.is_dir);
      if (editorPath === deleteTarget.path) {
        resetEditor();
      }
      setSelectedPath(null);
      toast({ description: "Удалено." });
      void loadDirectory(result.path || currentPath);
      setDeleteTarget(null);
    } catch (err) {
      toast({ variant: "destructive", description: err instanceof Error ? err.message : "Не удалось удалить" });
    } finally {
      setIsActionSubmitting(false);
    }
  }, [currentPath, deleteTarget, editorPath, loadDirectory, resetEditor, server.id, toast]);

  const handleDrop = useCallback((event: ReactDragEvent<HTMLDivElement>) => {
    if (!event.dataTransfer?.files?.length) return;
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
    enqueueUploadFiles(event.dataTransfer.files);
  }, [enqueueUploadFiles]);

  const openEntryInEditor = useCallback((entry: SftpEntry) => {
    setSelectedPath(entry.path);
    if (onOpenInEditor) {
      onOpenInEditor(entry.path);
      return;
    }
    requestEditorAction({ type: "open", entry });
  }, [onOpenInEditor, requestEditorAction]);

  const actionCopy = formActionCopy(formAction);

  return (
    <div
      className={cn(
        "flex h-full min-h-0 flex-col bg-card text-foreground",
        isDragging && "ring-2 ring-primary/60 ring-inset",
      )}
      onDragEnter={(event) => {
        if (event.dataTransfer?.types?.includes("Files")) {
          event.preventDefault();
          setIsDragging(true);
        }
      }}
      onDragOver={(event) => {
        if (event.dataTransfer?.types?.includes("Files")) {
          event.preventDefault();
        }
      }}
      onDragLeave={(event) => {
        if (event.currentTarget === event.target) {
          setIsDragging(false);
        }
      }}
      onDrop={handleDrop}
    >
      <SftpDirectoryBrowser
        server={server}
        entries={entries}
        visibleEntries={visibleEntries}
        selectedEntry={selectedEntry}
        selectedPath={selectedPath}
        searchQuery={searchQuery}
        isLoading={isLoading}
        error={error}
        homePath={homePath}
        parentPath={parentPath}
        breadcrumbSegments={breadcrumbSegments}
        onSearchQueryChange={setSearchQuery}
        onCreateFile={handleCreateFile}
        onCreateFolder={handleCreateFolder}
        onUploadClick={() => uploadInputRef.current?.click()}
        onRefresh={refreshDirectory}
        onOpenPath={(path) => void loadDirectory(path)}
        onSelectPath={(path) => setSelectedPath(path)}
        onOpenSelectedEntry={handleOpenEditor}
        onRename={handleRename}
        onChmod={handleChmod}
        onChown={handleChown}
        onDelete={handleDelete}
        onOpenEntryInEditor={openEntryInEditor}
        onDownload={queueDownload}
      />

      {editorPath && !onOpenInEditor ? (
        <SftpTextEditorSection
          editorContent={editorContent}
          editorEncoding={editorEncoding}
          editorError={editorError}
          editorFilename={editorFilename}
          editorPath={editorPath}
          editorSizeLabel={editorSizeLabel}
          isEditorDirty={isEditorDirty}
          isEditorLoading={isEditorLoading}
          isEditorSaving={isEditorSaving}
          onClose={() => requestEditorAction({ type: "close" })}
          onContentChange={setEditorContent}
          onReload={() => requestEditorAction({ type: "reload" })}
          onSave={saveEditor}
        />
      ) : null}

      <SftpTransferQueue
        transfers={transfers}
        expanded={transfersExpanded}
        onToggleExpanded={() => setTransfersExpanded((value) => !value)}
        onClearCompleted={clearCompletedTransfers}
        onRetry={retryTransfer}
        onCancelOrRemove={handleCancelOrRemoveTransfer}
      />

      <input
        ref={uploadInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(event) => {
          if (event.target.files?.length) {
            enqueueUploadFiles(event.target.files);
          }
          event.target.value = "";
        }}
      />
      {actionCopy ? (
        <SftpActionDialog
          open={Boolean(formAction)}
          title={actionCopy.title}
          description={actionCopy.description}
          label={actionCopy.label}
          value={formAction?.value ?? ""}
          placeholder={actionCopy.placeholder}
          error={formAction?.error}
          confirmLabel={actionCopy.confirmLabel}
          cancelLabel="Отмена"
          submitting={isActionSubmitting}
          onOpenChange={(open) => {
            if (!open && !isActionSubmitting) {
              setFormAction(null);
            }
          }}
          onValueChange={(value) => setFormAction((current) => current ? { ...current, value, error: "" } : current)}
          onSubmit={handleSubmitFormAction}
        />
      ) : null}
      <DeleteDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open && !isActionSubmitting) {
            setDeleteTarget(null);
          }
        }}
        title={deleteTarget?.is_dir ? "Удалить папку?" : "Удалить файл?"}
        description={
          deleteTarget?.is_dir
            ? `Папка "${deleteTarget.name}" будет удалена рекурсивно вместе с содержимым.`
            : `Файл "${deleteTarget?.name || ""}" будет удалён с сервера.`
        }
        confirmLabel="Удалить"
        cancelLabel="Отмена"
        onConfirm={confirmDelete}
      />
      <UnsavedChangesDialog
        open={Boolean(pendingEditorAction)}
        onOpenChange={(open) => {
          if (!open) setPendingEditorAction(null);
        }}
        title="Есть несохранённые изменения"
        description="Текущий файл изменён. Если продолжить, несохранённые правки будут потеряны."
        confirmLabel="Продолжить"
        cancelLabel="Вернуться к редактору"
        onConfirm={() => {
          if (pendingEditorAction) {
            runEditorAction(pendingEditorAction);
          }
          setPendingEditorAction(null);
        }}
      />
    </div>
  );
});
