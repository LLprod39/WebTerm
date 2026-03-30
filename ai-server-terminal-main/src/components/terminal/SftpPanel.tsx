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
  ExternalLink,
  File,
  FileCode2,
  Folder,
  FolderPlus,
  Loader2,
  Pencil,
  RefreshCw,
  Search,
  Save,
  Shield,
  Trash2,
  Upload,
  User,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import {
  chmodServerFile,
  chownServerFile,
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

function buildChildPath(basePath: string, name: string) {
  const normalizedName = String(name || "").trim().replace(/^\/+/, "");
  if (!normalizedName) return basePath;
  if (!basePath || basePath === ".") return normalizedName;
  return `${basePath.replace(/\/+$/, "")}/${normalizedName}`;
}

function defaultPermissionMode(entry: SftpEntry) {
  if (entry.permissions_octal) {
    return entry.permissions_octal.replace(/^0+/, "") || "0";
  }

  const symbolic = entry.permissions || "";
  if (symbolic.length < 10) return entry.is_dir ? "755" : "644";
  const triplets = [symbolic.slice(1, 4), symbolic.slice(4, 7), symbolic.slice(7, 10)];
  const octal = triplets
    .map((segment) => {
      let value = 0;
      if (segment.includes("r")) value += 4;
      if (segment.includes("w")) value += 2;
      if (/[xsStT]/.test(segment)) value += 1;
      return String(value);
    })
    .join("");
  return octal || (entry.is_dir ? "755" : "644");
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
  const [searchQuery, setSearchQuery] = useState("");
  const [showHidden, setShowHidden] = useState(true);
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
  const [transfersExpanded, setTransfersExpanded] = useState(true);

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

  const visibleEntries = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return [...entries]
      .filter((entry) => (showHidden ? true : !entry.name.startsWith(".")))
      .filter((entry) => {
        if (!query) return true;
        return `${entry.name} ${entry.path} ${entry.permissions || ""}`.toLowerCase().includes(query);
      })
      .sort((left, right) => {
        if (left.is_dir !== right.is_dir) return left.is_dir ? -1 : 1;
        return left.name.localeCompare(right.name, undefined, { sensitivity: "base", numeric: true });
      });
  }, [entries, searchQuery, showHidden]);

  const breadcrumbSegments = useMemo(() => {
    if (!currentPath || currentPath === ".") {
      return [{ label: ".", path: "." }];
    }
    const absolute = currentPath.startsWith("/");
    const segments = currentPath.split("/").filter(Boolean);
    let cursor = absolute ? "" : "";
    return segments.map((segment, index) => {
      cursor = absolute
        ? `${cursor}/${segment}`.replace(/\/+/g, "/")
        : index === 0
          ? segment
          : `${cursor}/${segment}`;
      return {
        label: segment,
        path: cursor || "/",
      };
    });
  }, [currentPath]);

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

  const handleCreateFile = useCallback(async () => {
    const fileName = window.prompt("New file", "new-file.conf");
    if (!fileName) return;
    const nextPath = buildChildPath(currentPath, fileName);
    try {
      const result = await writeServerTextFile(server.id, nextPath, "");
      setSelectedPath(result.file.path);
      setEditorPath(result.file.path);
      setEditorFilename(result.file.filename);
      setEditorEncoding(result.file.encoding);
      setEditorContent(result.file.content);
      setSavedEditorContent(result.file.content);
      setEditorError("");
      toast({ description: "File created." });
      void loadDirectory(currentPath);
    } catch (err) {
      toast({ variant: "destructive", description: err instanceof Error ? err.message : "Could not create file" });
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
      <div className="border-b border-border bg-card px-4 py-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-foreground">SFTP</div>
            <div className="truncate font-mono text-[11px] text-muted-foreground">
              {server.username}@{server.host}:{server.port}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" variant="outline" className="h-8 border-border bg-background px-3 text-xs" onClick={() => uploadInputRef.current?.click()}>
              <Upload className="h-3.5 w-3.5" />
              Upload
            </Button>
            <Button type="button" size="sm" variant="outline" className="h-8 border-border bg-background px-3 text-xs" onClick={refreshDirectory}>
              <RefreshCw className={cn("h-3.5 w-3.5", isLoading && "animate-spin")} />
              Refresh
            </Button>
          </div>
        </div>

        <div className="mt-3 flex flex-col gap-2 lg:flex-row lg:items-center">
          <div className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto">
            <Button type="button" size="sm" variant="outline" className="h-8 shrink-0 border-border bg-background px-3 text-xs" onClick={() => void loadDirectory(homePath)}>
              Home
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-8 shrink-0 border-border bg-background px-2 text-xs"
              onClick={() => parentPath && void loadDirectory(parentPath)}
              disabled={!parentPath}
              aria-label="Open parent folder"
            >
              <ArrowUp className="h-3.5 w-3.5" />
            </Button>
            {breadcrumbSegments.map((segment, index) => (
              <button
                key={`${segment.path}-${index}`}
                type="button"
                onClick={() => void loadDirectory(segment.path)}
                className="shrink-0 rounded-lg border border-border bg-background px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                {segment.label}
              </button>
            ))}
          </div>
          <div className="relative min-w-[14rem] lg:w-64">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search files..."
              aria-label="Search files"
              className="h-8 border-border bg-background pl-9 text-xs"
            />
          </div>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="border-b border-border bg-secondary/20 px-4 py-2.5">
          <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
            <span>{visibleEntries.length} items</span>
            <span>•</span>
            <span>{entries.filter((entry) => entry.is_dir).length} folders</span>
            <span>•</span>
            <span>{entries.filter((entry) => !entry.is_dir).length} files</span>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {error ? (
            <div className="px-4 py-6 text-sm text-destructive">{error}</div>
          ) : visibleEntries.length === 0 && !isLoading ? (
            <div className="workspace-empty m-4">
              <div className="text-sm font-medium text-foreground">
                {entries.length === 0 ? "This folder is empty." : "Nothing matched the current search."}
              </div>
            </div>
          ) : (
            <div className="divide-y divide-border/60">
              {visibleEntries.map((entry) => {
                const Icon = entryIcon(entry);
                const isSelected = entry.path === selectedPath;
                return (
                  <div
                    key={entry.path}
                    className={cn(
                      "flex items-center gap-3 px-4 py-3 transition-colors hover:bg-secondary/40",
                      isSelected && "bg-secondary/40",
                    )}
                  >
                    <button
                      type="button"
                      className="flex min-w-0 flex-1 items-center gap-3 text-left"
                      onClick={() => setSelectedPath(entry.path)}
                      onDoubleClick={() => (entry.is_dir ? void loadDirectory(entry.path) : queueDownload(entry))}
                    >
                      <div className={cn("rounded-xl p-2", entry.is_dir ? "bg-primary/10 text-primary" : "bg-secondary text-muted-foreground")}>
                        <Icon className="h-4 w-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium text-foreground">{entry.name}</div>
                        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                          <span>{entry.is_dir ? "Folder" : "File"}</span>
                          {!entry.is_dir ? <span>{formatBytes(entry.size)}</span> : null}
                          {entry.modified_at ? <span>{formatTimestamp(entry.modified_at)}</span> : null}
                        </div>
                      </div>
                    </button>

                    {entry.is_dir ? (
                      <Button type="button" size="sm" variant="ghost" className="h-8 px-2.5 text-xs" onClick={() => void loadDirectory(entry.path)}>
                        Open
                      </Button>
                    ) : (
                      <Button type="button" size="sm" variant="outline" className="h-8 border-border bg-background px-2.5 text-xs" onClick={() => queueDownload(entry)}>
                        <Download className="mr-1.5 h-3.5 w-3.5" />
                        Download
                      </Button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-border bg-secondary/20">
        <div className="flex items-center justify-between px-4 py-2">
          <button
            type="button"
            className="text-[11px] font-medium text-muted-foreground"
            onClick={() => setTransfersExpanded((value) => !value)}
          >
            Transfers {activeTransfers.length > 0 ? `(${activeTransfers.length})` : ""}
          </button>
          {transfers.length > 0 ? (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7 rounded-lg px-2 text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground"
              onClick={() => setTransfers((prev) => prev.filter((item) => item.status === "queued" || item.status === "running"))}
            >
              Clear finished
            </Button>
          ) : null}
        </div>
        {transfersExpanded ? (
          <div className="max-h-56 overflow-y-auto">
            {transfers.length === 0 ? (
              <div className="px-4 pb-4 text-xs text-muted-foreground">Transfer queue is empty.</div>
            ) : (
              <div className="divide-y divide-border/60">
                {transfers.map((item) => (
                  <div key={item.id} className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className={cn("rounded-lg p-1.5", item.direction === "upload" ? "bg-primary/10 text-primary" : "bg-secondary text-muted-foreground")}>
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
                        className="h-7 rounded-lg px-2 text-muted-foreground hover:bg-secondary hover:text-foreground"
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
                          <Button type="button" size="sm" variant="outline" className="h-7 rounded-lg border-border bg-background text-[11px] text-foreground hover:bg-secondary" onClick={() => retryTransfer(item.id)}>
                            Retry
                          </Button>
                          {item.direction === "upload" && item.error?.toLowerCase().includes("существ") ? (
                            <Button type="button" size="sm" variant="outline" className="h-7 rounded-lg border-border bg-background text-[11px] text-foreground hover:bg-secondary" onClick={() => retryTransfer(item.id, true)}>
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
        ) : null}
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
