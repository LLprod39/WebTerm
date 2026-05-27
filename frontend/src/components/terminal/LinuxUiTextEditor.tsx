import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Copy,
  FileCode2,
  FolderOpen,
  Loader2,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  readServerTextFile,
  writeServerTextFile,
  type FrontendServer,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";

interface EditorTab {
  id: string;
  path: string;
  filename: string;
  content: string;
  originalContent: string;
  encoding: string;
  isNew: boolean;
  dirty: boolean;
  loading: boolean;
  error: string | null;
}

let tabSeq = 0;
const RECENT_TEXT_FILES_STORAGE_KEY = "linux_ui_recent_text_files_v1";
function nextTabId() {
  tabSeq += 1;
  return `tab_${tabSeq}`;
}

function readRecentTextFiles() {
  try {
    const raw = window.localStorage.getItem(RECENT_TEXT_FILES_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((item) => String(item || "").trim())
      .filter(Boolean)
      .slice(0, 8);
  } catch {
    return [];
  }
}

function writeRecentTextFiles(paths: string[]) {
  try {
    window.localStorage.setItem(RECENT_TEXT_FILES_STORAGE_KEY, JSON.stringify(paths.slice(0, 8)));
  } catch {
    // noop
  }
}

export function TextEditorWindow({
  server,
  active,
  initialPath,
  onPathConsumed,
}: {
  server: FrontendServer;
  active: boolean;
  initialPath?: string;
  onPathConsumed?: () => void;
}) {
  const { toast } = useToast();
  const [tabs, setTabs] = useState<EditorTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);
  const [openPath, setOpenPath] = useState(initialPath || "");
  const [showOpenDialog, setShowOpenDialog] = useState(!initialPath);
  const [recentPaths, setRecentPaths] = useState<string[]>(() => readRecentTextFiles());
  const [softWrap, setSoftWrap] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const activeTab = tabs.find((t) => t.id === activeTabId) || null;
  const activeLineCount = useMemo(() => (activeTab ? activeTab.content.split("\n").length : 0), [activeTab]);
  const activeCharCount = useMemo(() => (activeTab ? activeTab.content.length : 0), [activeTab]);

  const pushRecentPath = useCallback((path: string) => {
    const normalized = String(path || "").trim();
    if (!normalized) return;
    setRecentPaths((prev) => {
      const next = [normalized, ...prev.filter((item) => item !== normalized)].slice(0, 8);
      writeRecentTextFiles(next);
      return next;
    });
  }, []);

  const openFile = useCallback(
    async (filePath: string) => {
      const existing = tabs.find((t) => t.path === filePath);
      if (existing) {
        setActiveTabId(existing.id);
        setShowOpenDialog(false);
        pushRecentPath(filePath);
        return;
      }

      const id = nextTabId();
      const filename = filePath.split("/").pop() || filePath;
      const newTab: EditorTab = {
        id,
        path: filePath,
        filename,
        content: "",
        originalContent: "",
        encoding: "utf-8",
        isNew: false,
        dirty: false,
        loading: true,
        error: null,
      };

      setTabs((prev) => [...prev, newTab]);
      setActiveTabId(id);
      setShowOpenDialog(false);

      try {
        const res = await readServerTextFile(server.id, filePath);
        if (!res.success) throw new Error("Failed to read file");
        pushRecentPath(filePath);
        setTabs((prev) =>
          prev.map((t) =>
            t.id === id
              ? {
                  ...t,
                  content: res.file.content,
                  originalContent: res.file.content,
                  encoding: res.file.encoding || "utf-8",
                  isNew: false,
                  loading: false,
                }
              : t,
          ),
        );
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to read file";
        const isMissingFileError = /не найдены|not found|404/i.test(message);
        setTabs((prev) =>
          prev.map((t) =>
            t.id === id
              ? isMissingFileError
                ? {
                    ...t,
                    content: "",
                    originalContent: "",
                    encoding: "utf-8",
                    isNew: true,
                    loading: false,
                    error: null,
                  }
                : { ...t, loading: false, error: message }
              : t,
          ),
        );
        if (isMissingFileError) {
          pushRecentPath(filePath);
          toast({
            title: "New file",
            description: `${filePath} will be created when you save it`,
          });
        }
      }
    },
    [pushRecentPath, server.id, tabs, toast],
  );

  useEffect(() => {
    if (initialPath) {
      void openFile(initialPath);
      onPathConsumed?.();
    } else if (tabs.length === 0) {
      setShowOpenDialog(true);
    }
  }, [initialPath]);

  const saveFile = useCallback(
    async (tabId: string) => {
      const tab = tabs.find((t) => t.id === tabId);
      if (!tab) return;

      try {
        const res = await writeServerTextFile(server.id, tab.path, tab.content);
        if (!res.success) throw new Error("Failed to save");
        pushRecentPath(tab.path);
        setTabs((prev) =>
          prev.map((t) =>
            t.id === tabId
              ? { ...t, originalContent: t.content, dirty: false, isNew: false }
              : t,
          ),
        );
        toast({ title: "Saved", description: tab.filename });
      } catch (err) {
        toast({
          title: "Save failed",
          description: err instanceof Error ? err.message : "Unknown error",
          variant: "destructive",
        });
      }
    },
    [pushRecentPath, server.id, tabs, toast],
  );

  const reloadFile = useCallback(
    async (tabId: string) => {
      const tab = tabs.find((item) => item.id === tabId);
      if (!tab || tab.isNew) return;

      setTabs((prev) =>
        prev.map((item) => (item.id === tabId ? { ...item, loading: true, error: null } : item)),
      );

      try {
        const res = await readServerTextFile(server.id, tab.path);
        if (!res.success) throw new Error("Failed to reload file");
        setTabs((prev) =>
          prev.map((item) =>
            item.id === tabId
              ? {
                  ...item,
                  content: res.file.content,
                  originalContent: res.file.content,
                  encoding: res.file.encoding || "utf-8",
                  dirty: false,
                  loading: false,
                  error: null,
                }
              : item,
          ),
        );
      } catch (err) {
        setTabs((prev) =>
          prev.map((item) =>
            item.id === tabId
              ? { ...item, loading: false, error: err instanceof Error ? err.message : "Failed to reload file" }
              : item,
          ),
        );
      }
    },
    [server.id, tabs],
  );

  const closeTab = useCallback(
    (tabId: string) => {
      setTabs((prev) => {
        const next = prev.filter((t) => t.id !== tabId);
        if (activeTabId === tabId) {
          const idx = prev.findIndex((t) => t.id === tabId);
          const fallback = next[Math.min(idx, next.length - 1)]?.id || null;
          setActiveTabId(fallback);
          if (!fallback) setShowOpenDialog(true);
        }
        return next;
      });
    },
    [activeTabId],
  );

  const updateContent = useCallback(
    (tabId: string, content: string) => {
      setTabs((prev) =>
        prev.map((t) =>
          t.id === tabId
            ? { ...t, content, dirty: content !== t.originalContent }
            : t,
        ),
      );
    },
    [],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        if (activeTabId) void saveFile(activeTabId);
      }
    },
    [activeTabId, saveFile],
  );

  const getLanguageHint = (filename: string) => {
    const ext = filename.split(".").pop()?.toLowerCase() || "";
    const map: Record<string, string> = {
      py: "Python", js: "JavaScript", ts: "TypeScript", tsx: "TSX", jsx: "JSX",
      json: "JSON", yaml: "YAML", yml: "YAML", toml: "TOML",
      sh: "Shell", bash: "Bash", zsh: "Zsh",
      conf: "Config", cfg: "Config", ini: "INI",
      md: "Markdown", txt: "Text", log: "Log",
      html: "HTML", css: "CSS", scss: "SCSS",
      xml: "XML", sql: "SQL", dockerfile: "Dockerfile",
      rs: "Rust", go: "Go", c: "C", cpp: "C++", h: "C Header",
      java: "Java", rb: "Ruby", php: "PHP",
      nginx: "Nginx", service: "systemd",
    };
    return map[ext] || "Plain text";
  };

  const copyPath = useCallback(async () => {
    if (!activeTab?.path) return;
    await navigator.clipboard.writeText(activeTab.path);
    toast({ title: "Path copied", description: activeTab.path });
  }, [activeTab?.path, toast]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-card text-foreground" onKeyDown={handleKeyDown}>
      <div className="border-b border-border bg-card px-3 py-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-foreground">Text Editor</div>
            <div className="mt-1 truncate text-xs text-muted-foreground">
              {activeTab?.path || "Open a config, script, or note file to edit it inline."}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-8 rounded-xl border-border bg-background px-3 text-xs text-foreground hover:bg-secondary"
              onClick={() => setShowOpenDialog(true)}
            >
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              Open
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-8 rounded-xl border-border bg-background px-3 text-xs text-foreground hover:bg-secondary"
              onClick={() => activeTabId && void saveFile(activeTabId)}
              disabled={!activeTabId || !activeTab?.dirty}
            >
              <Save className="mr-1.5 h-3.5 w-3.5" />
              Save
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-8 rounded-xl border-border bg-background px-3 text-xs text-foreground hover:bg-secondary"
              onClick={copyPath}
              disabled={!activeTab?.path}
            >
              <Copy className="mr-1.5 h-3.5 w-3.5" />
              Copy Path
            </Button>
            <Button
              type="button"
              size="sm"
              variant={softWrap ? "default" : "outline"}
              className="h-8 rounded-xl border-border px-3 text-xs"
              onClick={() => setSoftWrap((value) => !value)}
            >
              Wrap
            </Button>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-0.5 border-b border-border bg-secondary/30 px-2">
        <ScrollArea className="flex-1">
          <div className="flex items-center gap-0.5 py-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => {
                  setActiveTabId(tab.id);
                  setShowOpenDialog(false);
                }}
                className={cn(
                  "group flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs transition-colors",
                  activeTabId === tab.id
                    ? "border border-border bg-background text-foreground"
                    : "text-muted-foreground hover:bg-background/80 hover:text-foreground",
                )}
              >
                <FileCode2 className="h-3 w-3 shrink-0" />
                <span className="max-w-32 truncate">{tab.filename}</span>
                {tab.dirty && <span className="h-1.5 w-1.5 rounded-full bg-primary shrink-0" />}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(tab.id);
                  }}
                  className="ml-0.5 flex h-4 w-4 items-center justify-center rounded opacity-0 transition-opacity group-hover:opacity-100 hover:bg-secondary"
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              </button>
            ))}
          </div>
        </ScrollArea>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 w-7 shrink-0 rounded-xl p-0 text-muted-foreground hover:bg-secondary hover:text-foreground"
          onClick={() => setShowOpenDialog(true)}
        >
          <Plus className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Open file dialog */}
      {showOpenDialog && (
        <div className="border-b border-border bg-secondary/20 px-4 py-3">
          <div className="flex items-center gap-2">
            <FolderOpen className="h-4 w-4 shrink-0 text-muted-foreground" />
            <Input
              value={openPath}
              onChange={(e) => setOpenPath(e.target.value)}
              placeholder="/etc/nginx/nginx.conf or relative path (new files are allowed)..."
              className="h-8 flex-1 rounded-xl border-border bg-background font-mono text-xs text-foreground placeholder:text-muted-foreground"
              onKeyDown={(e) => {
                if (e.key === "Enter" && openPath.trim()) {
                  e.preventDefault();
                  void openFile(openPath.trim());
                }
              }}
              autoFocus
            />
            <Button
              type="button"
              size="sm"
              className="h-8 rounded-xl text-xs"
              disabled={!openPath.trim()}
              onClick={() => void openFile(openPath.trim())}
            >
              Open / Create
            </Button>
            {tabs.length > 0 && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-8 rounded-xl text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
                onClick={() => setShowOpenDialog(false)}
              >
                Cancel
              </Button>
            )}
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {[
              "/etc/nginx/nginx.conf",
              "/etc/hosts",
              "/etc/fstab",
              "/etc/crontab",
              "/etc/ssh/sshd_config",
              "~/.bashrc",
              "/etc/environment",
            ].map((path) => (
              <button
                key={path}
                type="button"
                onClick={() => void openFile(path)}
                className="rounded-full border border-border bg-background px-2 py-0.5 text-[10px] text-muted-foreground transition-colors hover:border-primary/20 hover:bg-secondary hover:text-foreground"
              >
                {path}
              </button>
            ))}
          </div>
          {recentPaths.length > 0 ? (
            <div className="mt-3">
              <div className="mb-1.5 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Recent</div>
              <div className="flex flex-wrap gap-1.5">
                {recentPaths.map((path) => (
                  <button
                    key={path}
                    type="button"
                    onClick={() => void openFile(path)}
                    className="rounded-full border border-border bg-background px-2.5 py-0.5 text-[10px] text-muted-foreground transition-colors hover:border-primary/20 hover:bg-secondary hover:text-foreground"
                  >
                    {path}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-hidden bg-transparent">
        {!activeTab ? (
          <div className="flex h-full items-center justify-center px-6 text-sm text-muted-foreground">
            <div className="text-center">
              <FileCode2 className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
              <div>Open a file to start editing</div>
              <div className="mt-1 text-xs">Use a path, a preset, or a recent file from this workspace.</div>
            </div>
          </div>
        ) : activeTab.loading ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
            <span className="ml-2 text-sm text-muted-foreground">Loading {activeTab.filename}...</span>
          </div>
        ) : activeTab.error ? (
          <div className="flex h-full items-center justify-center p-6">
            <div className="max-w-md rounded-[1.25rem] border border-destructive/25 bg-destructive/10 p-4 text-center">
              <AlertTriangle className="mx-auto h-5 w-5 text-destructive" />
              <div className="mt-2 text-sm text-destructive">{activeTab.error}</div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="mt-3 h-8 rounded-xl border-border bg-background text-xs text-foreground hover:bg-secondary"
                onClick={() => {
                  closeTab(activeTab.id);
                  setOpenPath(activeTab.path);
                  setShowOpenDialog(true);
                }}
              >
                Try another file
              </Button>
            </div>
          </div>
        ) : (
          <textarea
            ref={textareaRef}
            value={activeTab.content}
            onChange={(e) => updateContent(activeTab.id, e.target.value)}
            spellCheck={false}
            className={cn(
              "h-full w-full resize-none border-0 bg-transparent p-5 font-mono text-[13px] leading-6 text-foreground outline-none selection:bg-primary/20",
              softWrap ? "whitespace-pre-wrap break-words" : "whitespace-pre overflow-auto",
            )}
            style={{ tabSize: 4 }}
          />
        )}
      </div>

      <footer className="flex min-h-8 items-center justify-between border-t border-border bg-secondary/20 px-3 py-2 text-[11px] text-muted-foreground">
        <div className="flex items-center gap-3">
          {activeTab && (
            <>
              <span className="max-w-64 truncate font-mono">{activeTab.path}</span>
              <span>{getLanguageHint(activeTab.filename)}</span>
              <span>{activeTab.encoding}</span>
              {activeTab.isNew && (
                <span className="rounded-full bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">New file</span>
              )}
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          {activeTab && (
            <>
              {activeTab.dirty && (
                <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">Modified</span>
              )}
              <span>{activeLineCount} lines</span>
              <span>{activeCharCount} chars</span>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-6 gap-1 rounded-lg px-2 text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground"
                onClick={() => void saveFile(activeTab.id)}
                disabled={!activeTab.dirty}
              >
                <Save className="h-3 w-3" />
                Save
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-6 gap-1 rounded-lg px-2 text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground"
                onClick={() => void reloadFile(activeTab.id)}
                disabled={activeTab.isNew}
              >
                <RotateCcw className="h-3 w-3" />
                Reload
              </Button>
            </>
          )}
        </div>
      </footer>
    </div>
  );
}
