import {
  ArrowUp,
  Download,
  File,
  FileCode2,
  Folder,
  FolderPlus,
  Pencil,
  RefreshCw,
  Search,
  Shield,
  Trash2,
  Upload,
  User,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { FrontendServer, SftpEntry } from "@/lib/api";
import { cn } from "@/lib/utils";

import { formatBytes, formatRuCount } from "./sftpFormat";

export interface SftpBreadcrumbSegment {
  label: string;
  path: string;
}

interface SftpDirectoryBrowserProps {
  server: FrontendServer;
  entries: SftpEntry[];
  visibleEntries: SftpEntry[];
  selectedEntry: SftpEntry | null;
  selectedPath: string | null;
  searchQuery: string;
  isLoading: boolean;
  error: string;
  homePath: string;
  parentPath: string | null;
  breadcrumbSegments: SftpBreadcrumbSegment[];
  onSearchQueryChange: (query: string) => void;
  onCreateFile: () => void;
  onCreateFolder: () => void;
  onUploadClick: () => void;
  onRefresh: () => void;
  onOpenPath: (path: string) => void;
  onSelectPath: (path: string) => void;
  onOpenSelectedEntry: () => void;
  onRename: () => void;
  onChmod: () => void;
  onChown: () => void;
  onDelete: () => void;
  onOpenEntryInEditor: (entry: SftpEntry) => void;
  onDownload: (entry: SftpEntry) => void;
}

function formatTimestamp(value: number) {
  if (!value) return "";
  try {
    return new Date(value * 1000).toLocaleString();
  } catch {
    return "";
  }
}

function entryIcon(entry: SftpEntry) {
  if (entry.is_dir) return Folder;
  return File;
}

export function SftpDirectoryBrowser({
  server,
  entries,
  visibleEntries,
  selectedEntry,
  selectedPath,
  searchQuery,
  isLoading,
  error,
  homePath,
  parentPath,
  breadcrumbSegments,
  onSearchQueryChange,
  onCreateFile,
  onCreateFolder,
  onUploadClick,
  onRefresh,
  onOpenPath,
  onSelectPath,
  onOpenSelectedEntry,
  onRename,
  onChmod,
  onChown,
  onDelete,
  onOpenEntryInEditor,
  onDownload,
}: SftpDirectoryBrowserProps) {
  const directoryCount = entries.filter((entry) => entry.is_dir).length;
  const fileCount = entries.length - directoryCount;

  return (
    <>
      <div className="border-b border-border bg-card px-4 py-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-foreground">Файлы SFTP</div>
            <div className="truncate font-mono text-xs text-muted-foreground">
              {server.username}@{server.host}:{server.port}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-9 border-border bg-background px-3 text-xs"
              onClick={onCreateFile}
            >
              <FileCode2 className="h-4 w-4" />
              Новый файл
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-9 border-border bg-background px-3 text-xs"
              onClick={onCreateFolder}
            >
              <FolderPlus className="h-4 w-4" />
              Новая папка
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-9 border-border bg-background px-3 text-xs"
              onClick={onUploadClick}
            >
              <Upload className="h-4 w-4" />
              Загрузить
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-9 border-border bg-background px-3 text-xs"
              onClick={onRefresh}
            >
              <RefreshCw className={cn("h-4 w-4", isLoading && "animate-spin")} />
              Обновить
            </Button>
          </div>
        </div>

        <div className="mt-3 flex flex-col gap-2 lg:flex-row lg:items-center">
          <div className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto">
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-9 shrink-0 border-border bg-background px-3 text-xs"
              onClick={() => onOpenPath(homePath)}
            >
              Домой
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-9 shrink-0 border-border bg-background px-2 text-xs"
              onClick={() => parentPath && onOpenPath(parentPath)}
              disabled={!parentPath}
              aria-label="На уровень выше"
            >
              <ArrowUp className="h-4 w-4" />
            </Button>
            {breadcrumbSegments.map((segment, index) => (
              <button
                key={`${segment.path}-${index}`}
                type="button"
                onClick={() => onOpenPath(segment.path)}
                className="flex h-9 shrink-0 items-center rounded-lg border border-border bg-background px-3 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {segment.label}
              </button>
            ))}
          </div>
          <div className="relative min-w-[14rem] lg:w-64">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(event) => onSearchQueryChange(event.target.value)}
              placeholder="Поиск файлов..."
              aria-label="Поиск файлов"
              className="h-9 border-border bg-background pl-9 text-xs"
            />
          </div>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="border-b border-border bg-secondary/20 px-4 py-2.5">
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
              <span>{formatRuCount(visibleEntries.length, "объект", "объекта", "объектов")}</span>
              <span>•</span>
              <span>{formatRuCount(directoryCount, "папка", "папки", "папок")}</span>
              <span>•</span>
              <span>{formatRuCount(fileCount, "файл", "файла", "файлов")}</span>
            </div>
            {selectedEntry ? (
              <div className="flex flex-col gap-2 rounded-xl border border-border bg-background/80 px-3 py-2">
                <div className="min-w-0">
                  <div className="truncate text-xs font-medium text-foreground">{selectedEntry.name}</div>
                  <div className="truncate font-mono text-xs text-muted-foreground">{selectedEntry.path}</div>
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  {!selectedEntry.is_dir ? (
                    <Button type="button" size="sm" variant="ghost" className="h-9 justify-start px-2 text-xs" onClick={onOpenSelectedEntry}>
                      <FileCode2 className="mr-1 h-3.5 w-3.5" />
                      Редактировать
                    </Button>
                  ) : null}
                  <Button type="button" size="sm" variant="ghost" className="h-9 justify-start px-2 text-xs" onClick={onRename}>
                    <Pencil className="mr-1 h-3.5 w-3.5" />
                    Переименовать
                  </Button>
                  <Button type="button" size="sm" variant="ghost" className="h-9 justify-start px-2 text-xs" onClick={onChmod}>
                    <Shield className="mr-1 h-3.5 w-3.5" />
                    Права
                  </Button>
                  <Button type="button" size="sm" variant="ghost" className="h-9 justify-start px-2 text-xs" onClick={onChown}>
                    <User className="mr-1 h-3.5 w-3.5" />
                    Владелец
                  </Button>
                  <Button type="button" size="sm" variant="ghost" className="h-9 justify-start px-2 text-xs text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={onDelete}>
                    <Trash2 className="mr-1 h-3.5 w-3.5" />
                    Удалить
                  </Button>
                </div>
              </div>
            ) : null}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {error ? (
            <div className="px-4 py-6 text-sm text-destructive">{error}</div>
          ) : visibleEntries.length === 0 && !isLoading ? (
            <div className="workspace-empty m-4">
              <div className="text-sm font-medium text-foreground">
                {entries.length === 0 ? "Папка пустая." : "Поиск ничего не нашел."}
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
                      onClick={() => onSelectPath(entry.path)}
                      onDoubleClick={() => {
                        if (entry.is_dir) {
                          onOpenPath(entry.path);
                          return;
                        }
                        onOpenEntryInEditor(entry);
                      }}
                    >
                      <div className={cn("rounded-xl p-2", entry.is_dir ? "bg-primary/10 text-primary" : "bg-secondary text-muted-foreground")}>
                        <Icon className="h-4 w-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium text-foreground">{entry.name}</div>
                        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                          <span>{entry.is_dir ? "Папка" : "Файл"}</span>
                          {!entry.is_dir ? <span>{formatBytes(entry.size)}</span> : null}
                          {entry.modified_at ? <span>{formatTimestamp(entry.modified_at)}</span> : null}
                        </div>
                      </div>
                    </button>

                    {entry.is_dir ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-9 px-3 text-xs"
                        onClick={() => onOpenPath(entry.path)}
                      >
                        Открыть
                      </Button>
                    ) : (
                      <div className="flex shrink-0 items-center gap-2">
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="h-9 px-3 text-xs"
                          onClick={() => onOpenEntryInEditor(entry)}
                        >
                          <FileCode2 className="mr-1.5 h-3.5 w-3.5" />
                          Редактировать
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="h-9 border-border bg-background px-3 text-xs"
                          onClick={() => onDownload(entry)}
                        >
                          <Download className="mr-1.5 h-3.5 w-3.5" />
                          Скачать
                        </Button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
