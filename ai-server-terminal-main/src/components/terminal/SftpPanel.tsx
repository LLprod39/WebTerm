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
  ArrowUp,
  Download,
  File,
  FileCode2,
  Folder,
  FolderPlus,
  Loader2,
  Pencil,
  RefreshCw,
  Save,
  Trash2,
  Upload,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import {
  createServerFolder,
  deleteServerFile,
  downloadServerFile,
  listServerFiles,
  readServerTextFile,
  renameServerFile,
  saveBlobAsFile,
  type FrontendServer,
  type SftpEntry,
  uploadServerFiles,
  writeServerTextFile,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";

type TransferStatus = "queued" | "running" | "success" | "error" | "cancelled";
type TransferDirection = "upload" | "download";

interface TransferItem {
  id: string;
  direction: TransferDirection;
  name: string;
  remotePath: string;
  targetDir: string;
  file?: File;
  status: TransferStatus;
  progress: number;
  loaded: number;
  total?: number;
  error?: string;
  overwrite?: boolean;
}

export interface SftpPanelHandle {
  enqueueUploads: (files: FileList | File[]) => void;
  refresh: () => void;
}

interface SftpPanelProps {
  server: FrontendServer;
  active?: boolean;
  onOpenInEditor?: (path: string) => void;
}

let transferSeq = 0;

function nextTransferId() {
  transferSeq += 1;
  return `transfer_${transferSeq}`;
}

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const power = Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024)));
  const amount = value / 1024 ** power;
  return `${amount >= 10 || power === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[power]}`;
}

function formatTimestamp(value: number) {
  if (!value) return "";
  try {
    return new Date(value * 1000).toLocaleString();
  } catch {
    return "";
  }
}

function transferStatusLabel(item: TransferItem) {
  switch (item.status) {
    case "queued":
      return "В очереди";
    case "running":
      return "Передача";
    case "success":
      return "Готово";
    case "cancelled":
      return "Отменено";
    case "error":
      return item.error || "Ошибка";
    default:
      return item.status;
  }
}

function entryIcon(entry: SftpEntry) {
  if (entry.is_dir) return Folder;
  return File;
}

export const SftpPanel = forwardRef<SftpPanelHandle, SftpPanelProps>(function SftpPanel(
  { server, active = true, onOpenInEditor }: SftpPanelProps,
  ref,
) {
  const { toast } = useToast();
  const uploadInputRef = useRef<HTMLInputElement>(null);
  const abortControllersRef = useRef<Record<string, AbortController>>({});
  const loadSeqRef = useRef(0);
  const editorLoadSeqRef = useRef(0);

  const [currentPath, setCurrentPath] = useState(".");
  const [pathInput, setPathInput] = useState(".");
  const [homePath, setHomePath] = useState(".");
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [entries, setEntries] = useState<SftpEntry[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState("");
  const [transfers, setTransfers] = useState<TransferItem[]>([]);
  const [editorPath, setEditorPath] = useState<string | null>(null);
  const [editorFilename, setEditorFilename] = useState("");
  const [editorEncoding, setEditorEncoding] = useState("utf-8");
  const [editorContent, setEditorContent] = useState("");
  const [savedEditorContent, setSavedEditorContent] = useState("");
  const [editorError, setEditorError] = useState("");
  const [isEditorLoading, setIsEditorLoading] = useState(false);
  const [isEditorSaving, setIsEditorSaving] = useState(false);

  const selectedEntry = useMemo(
    () => entries.find((entry) => entry.path === selectedPath) || null,
    [entries, selectedPath],
  );

  const isEditorDirty = useMemo(
    () => Boolean(editorPath) && editorContent !== savedEditorContent,
    [editorContent, editorPath, savedEditorContent],
  );

  const editorSizeLabel = useMemo(() => {
    if (!editorPath) return "";
    return formatBytes(new TextEncoder().encode(editorContent).length);
  }, [editorContent, editorPath]);

  const resetEditor = useCallback(() => {
    editorLoadSeqRef.current += 1;
    setEditorPath(null);
    setEditorFilename("");
    setEditorEncoding("utf-8");
    setEditorContent("");
    setSavedEditorContent("");
    setEditorError("");
    setIsEditorLoading(false);
    setIsEditorSaving(false);
  }, []);

  const confirmDiscardEditorChanges = useCallback((nextActionLabel: string) => {
    if (!isEditorDirty) return true;
    return window.confirm(`Есть несохранённые изменения. Продолжить и ${nextActionLabel}?`);
  }, [isEditorDirty]);

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

  useEffect(() => {
    Object.values(abortControllersRef.current).forEach((controller) => controller.abort());
    abortControllersRef.current = {};
    setCurrentPath(".");
    setPathInput(".");
    setHomePath(".");
    setParentPath(null);
    setEntries([]);
    setSelectedPath(null);
    setTransfers([]);
    setError("");
    resetEditor();
    void loadDirectory(".");
  }, [loadDirectory, resetEditor, server.id]);

  useEffect(() => () => {
    Object.values(abortControllersRef.current).forEach((controller) => controller.abort());
    abortControllersRef.current = {};
  }, []);

  useEffect(() => {
    if (!active) return;
    if (!entries.length && !isLoading && !error) {
      void loadDirectory(currentPath);
    }
  }, [active, currentPath, entries.length, error, isLoading, loadDirectory]);

  const enqueueUploadFiles = useCallback((files: FileList | File[]) => {
    const nextFiles = Array.from(files || []).filter((file) => file.size >= 0);
    if (!nextFiles.length) return;

    setTransfers((prev) => [
      ...prev,
      ...nextFiles.map((file) => ({
        id: nextTransferId(),
        direction: "upload" as const,
        name: file.name,
        remotePath: `${currentPath.replace(/\/$/, "")}/${file.name}`,
        targetDir: currentPath,
        file,
        status: "queued" as const,
        progress: 0,
        loaded: 0,
        total: file.size,
      })),
    ]);
  }, [currentPath]);

  useImperativeHandle(ref, () => ({
    enqueueUploads: (files) => {
      enqueueUploadFiles(files);
    },
    refresh: () => {
      void loadDirectory(currentPath);
    },
  }), [currentPath, enqueueUploadFiles, loadDirectory]);

  const updateTransfer = useCallback((id: string, patch: Partial<TransferItem>) => {
    setTransfers((prev) => prev.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }, []);

  const retryTransfer = useCallback((id: string, overwrite = false) => {
    setTransfers((prev) =>
      prev.map((item) =>
        item.id === id
          ? { ...item, status: "queued", progress: 0, loaded: 0, error: undefined, overwrite }
          : item,
      ),
    );
  }, []);

  const removeTransfer = useCallback((id: string) => {
    const controller = abortControllersRef.current[id];
    if (controller) controller.abort();
    setTransfers((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const cancelTransfer = useCallback((id: string) => {
    const controller = abortControllersRef.current[id];
    if (controller) {
      controller.abort();
      return;
    }
    updateTransfer(id, { status: "cancelled" });
  }, [updateTransfer]);

  const queueDownload = useCallback((entry: SftpEntry) => {
    if (entry.is_dir) {
      toast({ variant: "destructive", description: "Скачивание папок пока не поддерживается." });
      return;
    }
    setTransfers((prev) => [
      ...prev,
      {
        id: nextTransferId(),
        direction: "download",
        name: entry.name,
        remotePath: entry.path,
        targetDir: currentPath,
        status: "queued",
        progress: 0,
        loaded: 0,
        total: entry.size,
      },
    ]);
  }, [currentPath, toast]);

  const runTransfer = useCallback(async (item: TransferItem) => {
    const controller = new AbortController();
    abortControllersRef.current[item.id] = controller;
    updateTransfer(item.id, { status: "running", error: undefined });

    try {
      if (item.direction === "upload") {
        if (!item.file) {
          throw new Error("Файл для загрузки не найден");
        }
        await uploadServerFiles(server.id, {
          path: item.targetDir,
          files: [item.file],
          overwrite: item.overwrite,
          signal: controller.signal,
          onProgress: ({ loaded, total }) => {
            updateTransfer(item.id, {
              loaded,
              total,
              progress: total ? Math.round((loaded / total) * 100) : 0,
            });
          },
        });
        updateTransfer(item.id, {
          status: "success",
          loaded: item.file.size,
          total: item.file.size,
          progress: 100,
        });
        if (item.targetDir === currentPath) {
          void loadDirectory(currentPath);
        }
        return;
      }

      const result = await downloadServerFile(server.id, {
        path: item.remotePath,
        signal: controller.signal,
        onProgress: ({ loaded, total }) => {
          updateTransfer(item.id, {
            loaded,
            total,
            progress: total ? Math.round((loaded / total) * 100) : 0,
          });
        },
      });
      saveBlobAsFile(result.blob, result.filename);
      updateTransfer(item.id, {
        status: "success",
        loaded: result.size,
        total: result.size,
        progress: 100,
      });
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        updateTransfer(item.id, { status: "cancelled", error: undefined });
        return;
      }
      const message = err instanceof Error ? err.message : "Передача завершилась ошибкой";
      updateTransfer(item.id, { status: "error", error: message });
    } finally {
      delete abortControllersRef.current[item.id];
    }
  }, [currentPath, loadDirectory, server.id, updateTransfer]);

  useEffect(() => {
    if (transfers.some((item) => item.status === "running")) return;
    const nextItem = transfers.find((item) => item.status === "queued");
    if (!nextItem) return;
    void runTransfer(nextItem);
  }, [runTransfer, transfers]);

  const openTextEditor = useCallback(async (entry: SftpEntry, options?: { forceReload?: boolean }) => {
    if (entry.is_dir) return;

    const isSameFile = editorPath === entry.path;
    if (isSameFile && !options?.forceReload) {
      setSelectedPath(entry.path);
      return;
    }

    if (!isSameFile && !confirmDiscardEditorChanges("открыть другой файл")) {
      return;
    }

    const seq = editorLoadSeqRef.current + 1;
    editorLoadSeqRef.current = seq;
    setIsEditorLoading(true);
    setEditorError("");
    setSelectedPath(entry.path);

    try {
      const result = await readServerTextFile(server.id, entry.path);
      if (editorLoadSeqRef.current !== seq) return;

      setEditorPath(result.file.path);
      setEditorFilename(result.file.filename);
      setEditorEncoding(result.file.encoding);
      setEditorContent(result.file.content);
      setSavedEditorContent(result.file.content);
    } catch (err) {
      if (editorLoadSeqRef.current !== seq) return;
      const message = err instanceof Error ? err.message : "Не удалось открыть файл";
      setEditorError(message);
      toast({ variant: "destructive", description: message });
    } finally {
      if (editorLoadSeqRef.current === seq) {
        setIsEditorLoading(false);
      }
    }
  }, [confirmDiscardEditorChanges, editorPath, server.id, toast]);

  const reloadEditor = useCallback(async () => {
    if (!editorPath) return;
    if (!confirmDiscardEditorChanges("перезагрузить файл")) return;

    const entry = entries.find((item) => item.path === editorPath) || {
      path: editorPath,
      name: editorFilename || editorPath.split("/").filter(Boolean).pop() || editorPath,
      kind: "file" as const,
      is_dir: false,
      is_symlink: false,
      size: 0,
      permissions: "",
      modified_at: 0,
    };

    await openTextEditor(entry, { forceReload: true });
  }, [confirmDiscardEditorChanges, editorFilename, editorPath, entries, openTextEditor]);

  const closeEditor = useCallback(() => {
    if (!confirmDiscardEditorChanges("закрыть редактор")) return;
    resetEditor();
  }, [confirmDiscardEditorChanges, resetEditor]);

  const saveEditor = useCallback(async () => {
    if (!editorPath) return;

    setIsEditorSaving(true);
    setEditorError("");
    try {
      const result = await writeServerTextFile(server.id, editorPath, editorContent);
      setEditorPath(result.file.path);
      setEditorFilename(result.file.filename);
      setEditorEncoding(result.file.encoding);
      setEditorContent(result.file.content);
      setSavedEditorContent(result.file.content);
      toast({ description: "Файл сохранён." });
      void loadDirectory(currentPath);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Не удалось сохранить файл";
      setEditorError(message);
      toast({ variant: "destructive", description: message });
    } finally {
      setIsEditorSaving(false);
    }
  }, [currentPath, editorContent, editorPath, loadDirectory, server.id, toast]);

  const handleEntryOpen = useCallback((entry: SftpEntry) => {
    if (entry.is_dir) {
      void loadDirectory(entry.path);
      return;
    }
    void openTextEditor(entry);
  }, [loadDirectory, openTextEditor]);

  const handleOpenEditor = useCallback(() => {
    if (!selectedEntry || selectedEntry.is_dir) {
      toast({ variant: "destructive", description: "Выберите текстовый файл." });
      return;
    }
    void openTextEditor(selectedEntry);
  }, [openTextEditor, selectedEntry, toast]);

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
      if (editorPath === previousPath && result.entry?.path) {
        setEditorPath(result.entry.path);
        setEditorFilename(result.entry.name);
      }
      toast({ description: "Имя обновлено." });
      void loadDirectory(result.path || currentPath);
    } catch (err) {
      toast({ variant: "destructive", description: err instanceof Error ? err.message : "Не удалось переименовать" });
    }
  }, [currentPath, editorPath, loadDirectory, selectedEntry, server.id, toast]);

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

  const handleManualPathSubmit = useCallback(() => {
    if (!pathInput.trim()) return;
    void loadDirectory(pathInput.trim());
  }, [loadDirectory, pathInput]);

  const handleDrop = useCallback((event: ReactDragEvent<HTMLDivElement>) => {
    if (!event.dataTransfer?.files?.length) return;
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
    enqueueUploadFiles(event.dataTransfer.files);
  }, [enqueueUploadFiles]);

  const activeTransfers = useMemo(
    () => transfers.filter((item) => item.status === "queued" || item.status === "running"),
    [transfers],
  );

  const showEditorPane = Boolean(editorPath) || isEditorLoading;

  return (
    <div
      className={cn(
        "flex h-full min-h-0 flex-col bg-card",
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
      <div className="border-b border-border px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-foreground">Files</div>
            <div className="truncate font-mono text-[11px] text-muted-foreground">
              {server.username}@{server.host}:{server.port}
            </div>
          </div>
          <div className="flex items-center gap-1">
            <Button type="button" size="sm" variant="ghost" className="h-8 px-2" onClick={() => uploadInputRef.current?.click()}>
              <Upload className="h-3.5 w-3.5" />
            </Button>
            <Button type="button" size="sm" variant="ghost" className="h-8 px-2" onClick={handleCreateFolder}>
              <FolderPlus className="h-3.5 w-3.5" />
            </Button>
            <Button type="button" size="sm" variant="ghost" className="h-8 px-2" onClick={refreshDirectory}>
              <RefreshCw className={cn("h-3.5 w-3.5", isLoading && "animate-spin")} />
            </Button>
          </div>
        </div>

        <div className="mt-3 flex items-center gap-2">
          <Button type="button" size="sm" variant="outline" className="h-8 px-2" onClick={() => void loadDirectory(homePath)}>
            Home
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8 px-2"
            onClick={() => parentPath && void loadDirectory(parentPath)}
            disabled={!parentPath}
          >
            <ArrowUp className="h-3.5 w-3.5" />
          </Button>
          <Input
            value={pathInput}
            onChange={(event) => setPathInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                handleManualPathSubmit();
              }
            }}
            className="h-8 text-xs font-mono"
          />
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col xl:flex-row">
        <div className={cn("flex min-h-0 flex-1 flex-col", showEditorPane && "xl:border-r xl:border-border")}>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {error ? (
              <div className="px-4 py-6 text-sm text-destructive">{error}</div>
            ) : entries.length === 0 && !isLoading ? (
              <div className="px-4 py-6 text-sm text-muted-foreground">Папка пуста.</div>
            ) : (
              <div className="divide-y divide-border/40">
                {entries.map((entry) => {
                  const Icon = entryIcon(entry);
                  const isSelected = entry.path === selectedPath;
                  const isEditing = entry.path === editorPath;
                  return (
                    <button
                      key={entry.path}
                      type="button"
                      className={cn(
                        "flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-secondary/40",
                        isSelected && "bg-primary/8",
                      )}
                      onClick={() => setSelectedPath(entry.path)}
                      onDoubleClick={() => handleEntryOpen(entry)}
                    >
                      <div className={cn("rounded-lg p-2", entry.is_dir ? "bg-primary/10 text-primary" : "bg-secondary text-muted-foreground")}>
                        <Icon className="h-4 w-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <div className="truncate text-sm font-medium text-foreground">{entry.name}</div>
                          {isEditing ? (
                            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
                              open
                            </span>
                          ) : null}
                        </div>
                        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                          <span>{entry.permissions || (entry.is_dir ? "dir" : "file")}</span>
                          {!entry.is_dir ? <span>{formatBytes(entry.size)}</span> : null}
                        </div>
                      </div>
                      <div className="shrink-0 text-[11px] text-muted-foreground">{formatTimestamp(entry.modified_at)}</div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div className="border-t border-border px-4 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={() => selectedEntry && queueDownload(selectedEntry)} disabled={!selectedEntry || selectedEntry.is_dir}>
                <Download className="mr-1 h-3.5 w-3.5" />
                Download
              </Button>
              <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={handleOpenEditor} disabled={!selectedEntry || selectedEntry.is_dir}>
                <FileCode2 className="mr-1 h-3.5 w-3.5" />
                Edit
              </Button>
              <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={handleRename} disabled={!selectedEntry}>
                <Pencil className="mr-1 h-3.5 w-3.5" />
                Rename
              </Button>
              <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={handleDelete} disabled={!selectedEntry}>
                <Trash2 className="mr-1 h-3.5 w-3.5" />
                Delete
              </Button>
            </div>
            <div className="mt-2 text-[11px] text-muted-foreground">
              Drag and drop files into the terminal or this panel to upload into <span className="font-mono">{currentPath}</span>.
            </div>
          </div>
        </div>

        {showEditorPane ? (
          <div className="flex min-h-0 w-full flex-col bg-background/70 xl:max-w-[48%] xl:min-w-[360px]">
            <div className="border-b border-border px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                    <FileCode2 className="h-4 w-4 text-primary" />
                    <span className="truncate">{editorFilename || "Text Editor"}</span>
                    {isEditorDirty ? (
                      <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-600">
                        unsaved
                      </span>
                    ) : null}
                  </div>
                  <div className="truncate font-mono text-[11px] text-muted-foreground">
                    {editorPath || "Загрузка файла..."}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <Button type="button" size="sm" variant="ghost" className="h-8 px-2" onClick={() => void reloadEditor()} disabled={!editorPath || isEditorLoading || isEditorSaving}>
                    <RefreshCw className={cn("h-3.5 w-3.5", isEditorLoading && "animate-spin")} />
                  </Button>
                  <Button type="button" size="sm" variant="ghost" className="h-8 px-2" onClick={() => void saveEditor()} disabled={!editorPath || isEditorLoading || isEditorSaving || !isEditorDirty}>
                    {isEditorSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                  </Button>
                  <Button type="button" size="sm" variant="ghost" className="h-8 px-2" onClick={closeEditor} disabled={isEditorSaving}>
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            </div>

            <div className="flex min-h-0 flex-1 flex-col">
              {isEditorLoading ? (
                <div className="flex min-h-[280px] flex-1 items-center justify-center text-sm text-muted-foreground">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Открываем файл...
                </div>
              ) : (
                <>
                  {editorError ? (
                    <div className="border-b border-border bg-destructive/5 px-4 py-2 text-xs text-destructive">
                      {editorError}
                    </div>
                  ) : null}
                  <div className="min-h-0 flex-1 p-4">
                    <Textarea
                      value={editorContent}
                      onChange={(event) => setEditorContent(event.target.value)}
                      spellCheck={false}
                      className="h-full min-h-[280px] resize-none border-border/60 bg-background font-mono text-xs leading-5"
                      placeholder="Выберите текстовый файл для редактирования."
                      disabled={!editorPath || isEditorSaving}
                    />
                  </div>
                  <div className="border-t border-border px-4 py-2 text-[11px] text-muted-foreground">
                    <div className="flex items-center justify-between gap-2">
                      <span>{editorEncoding.toUpperCase()}</span>
                      <span>{editorSizeLabel}</span>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        ) : null}
      </div>

      <div className="border-t border-border bg-secondary/20">
        <div className="flex items-center justify-between px-4 py-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Transfers {activeTransfers.length > 0 ? `(${activeTransfers.length})` : ""}
          </div>
          {transfers.length > 0 ? (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7 px-2 text-[11px]"
              onClick={() => setTransfers((prev) => prev.filter((item) => item.status === "queued" || item.status === "running"))}
            >
              Clear finished
            </Button>
          ) : null}
        </div>
        <div className="max-h-56 overflow-y-auto">
          {transfers.length === 0 ? (
            <div className="px-4 pb-4 text-xs text-muted-foreground">Очередь передач пуста.</div>
          ) : (
            <div className="divide-y divide-border/40">
              {transfers.map((item) => (
                <div key={item.id} className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <div className={cn("rounded p-1.5", item.direction === "upload" ? "bg-primary/10 text-primary" : "bg-secondary text-muted-foreground")}>
                      {item.direction === "upload" ? <Upload className="h-3.5 w-3.5" /> : <Download className="h-3.5 w-3.5" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm text-foreground">{item.name}</div>
                      <div className="truncate text-[11px] text-muted-foreground">{transferStatusLabel(item)}</div>
                    </div>
                    {item.status === "running" ? <Loader2 className="h-4 w-4 animate-spin text-primary" /> : null}
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-7 px-2"
                      onClick={() => (item.status === "running" || item.status === "queued" ? cancelTransfer(item.id) : removeTransfer(item.id))}
                    >
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                  <div className="mt-2">
                    <Progress value={item.progress} className="h-2" />
                    <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
                      <span>
                        {formatBytes(item.loaded)}
                        {item.total ? ` / ${formatBytes(item.total)}` : ""}
                      </span>
                      <span>{item.progress}%</span>
                    </div>
                    {item.status === "error" ? (
                      <div className="mt-2 flex items-center gap-2">
                        <Button type="button" size="sm" variant="outline" className="h-7 text-[11px]" onClick={() => retryTransfer(item.id)}>
                          Retry
                        </Button>
                        {item.direction === "upload" && item.error?.toLowerCase().includes("существ") ? (
                          <Button type="button" size="sm" variant="outline" className="h-7 text-[11px]" onClick={() => retryTransfer(item.id, true)}>
                            Overwrite
                          </Button>
                        ) : null}
                        <div className="truncate text-[11px] text-destructive">{item.error}</div>
                      </div>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

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
