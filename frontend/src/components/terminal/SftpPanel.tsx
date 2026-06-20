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
import { SftpTransferQueue } from "./SftpTransferQueue";
import { SftpDirectoryBrowser } from "./sftp-panel/SftpDirectoryBrowser";
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
      setPathInput(result.path);
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
    confirmDiscardEditorChanges,
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
    void loadDirectory(".");
  }, [loadDirectory, resetEditor, resetTransfers, server.id]);

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

  const handleOpenEditor = useCallback(() => {
    if (!selectedEntry || selectedEntry.is_dir) {
      toast({ variant: "destructive", description: "Выберите текстовый файл." });
      return;
    }
    if (onOpenInEditor) {
      onOpenInEditor(selectedEntry.path);
      return;
    }
    void openTextEditor(selectedEntry);
  }, [onOpenInEditor, openTextEditor, selectedEntry, toast]);

  const handleCreateFolder = useCallback(async () => {
    const folderName = window.prompt("Новая папка", "");
    if (!folderName) return;
    try {
      await createServerFolder(server.id, currentPath, folderName);
      toast({ description: "Папка создана." });
      void loadDirectory(currentPath);
    } catch (err) {
      toast({ variant: "destructive", description: err instanceof Error ? err.message : "Не удалось создать папку" });
    }
  }, [currentPath, loadDirectory, server.id, toast]);

  const handleCreateFile = useCallback(async () => {
    const fileName = window.prompt("Новый файл", "new-file.conf");
    if (!fileName) return;
    const nextPath = buildChildPath(currentPath, fileName);
    try {
      const result = await writeServerTextFile(server.id, nextPath, "");
      setSelectedPath(result.file.path);
      setEditorFile(result.file);
      toast({ description: "Файл создан." });
      void loadDirectory(currentPath);
      onOpenInEditor?.(result.file.path);
    } catch (err) {
      toast({ variant: "destructive", description: err instanceof Error ? err.message : "Не удалось создать файл" });
    }
  }, [currentPath, loadDirectory, onOpenInEditor, server.id, setEditorFile, toast]);

  const handleRename = useCallback(async () => {
    if (!selectedEntry) {
      toast({ variant: "destructive", description: "Выберите файл или папку." });
      return;
    }

    const previousPath = selectedEntry.path;
    const nextName = window.prompt("Новое имя", selectedEntry.name);
    if (!nextName || nextName === selectedEntry.name) return;

    try {
      const result = await renameServerFile(server.id, selectedEntry.path, nextName);
      setSelectedPath(result.entry?.path || null);
      syncRenamedEditorPath(previousPath, result.entry);
      toast({ description: "Имя обновлено." });
      void loadDirectory(result.path || currentPath);
    } catch (err) {
      toast({ variant: "destructive", description: err instanceof Error ? err.message : "Не удалось переименовать" });
    }
  }, [currentPath, loadDirectory, selectedEntry, server.id, syncRenamedEditorPath, toast]);

  const handleDelete = useCallback(async () => {
    if (!selectedEntry) {
      toast({ variant: "destructive", description: "Выберите файл или папку." });
      return;
    }

    const confirmed = window.confirm(
      selectedEntry.is_dir
        ? `Удалить папку "${selectedEntry.name}" рекурсивно?`
        : `Удалить файл "${selectedEntry.name}"?`,
    );
    if (!confirmed) return;

    try {
      const result = await deleteServerFile(server.id, selectedEntry.path, selectedEntry.is_dir);
      if (editorPath === selectedEntry.path) {
        resetEditor();
      }
      setSelectedPath(null);
      toast({ description: "Удалено." });
      void loadDirectory(result.path || currentPath);
    } catch (err) {
      toast({ variant: "destructive", description: err instanceof Error ? err.message : "Не удалось удалить" });
    }
  }, [currentPath, editorPath, loadDirectory, resetEditor, selectedEntry, server.id, toast]);

  const handleChmod = useCallback(async () => {
    if (!selectedEntry) {
      toast({ variant: "destructive", description: "Выберите файл или папку." });
      return;
    }

    const mode = window.prompt("Новые права доступа", defaultPermissionMode(selectedEntry));
    if (!mode) return;
    const normalizedMode = mode.trim();
    if (!/^[0-7]{3,4}$/.test(normalizedMode)) {
      toast({ variant: "destructive", description: "Введите права в формате 644, 755 или 0644." });
      return;
    }

    try {
      const result = await chmodServerFile(server.id, selectedEntry.path, normalizedMode);
      toast({ description: "Права доступа обновлены." });
      void loadDirectory(result.path || currentPath);
    } catch (err) {
      toast({ variant: "destructive", description: err instanceof Error ? err.message : "Не удалось обновить права" });
    }
  }, [currentPath, loadDirectory, selectedEntry, server.id, toast]);

  const handleChown = useCallback(async () => {
    if (!selectedEntry) {
      toast({ variant: "destructive", description: "Выберите файл или папку." });
      return;
    }

    const owner = window.prompt("Новый владелец или владелец:группа", "");
    if (!owner) return;
    const normalizedOwner = owner.trim();
    if (!normalizedOwner) return;

    try {
      const result = await chownServerFile(server.id, selectedEntry.path, normalizedOwner, selectedEntry.is_dir);
      toast({ description: "Владелец обновлён." });
      void loadDirectory(result.path || currentPath);
    } catch (err) {
      toast({ variant: "destructive", description: err instanceof Error ? err.message : "Не удалось обновить владельца" });
    }
  }, [currentPath, loadDirectory, selectedEntry, server.id, toast]);

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
    void openTextEditor(entry);
  }, [onOpenInEditor, openTextEditor]);

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
          onClose={closeEditor}
          onContentChange={setEditorContent}
          onReload={reloadEditor}
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
    </div>
  );
});
