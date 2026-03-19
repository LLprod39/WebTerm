import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  FileCode2,
  FolderOpen,
  Loader2,
  Plus,
  RefreshCw,
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
function nextTabId() {
  tabSeq += 1;
  return `tab_${tabSeq}`;
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
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const activeTab = tabs.find((t) => t.id === activeTabId) || null;

  const openFile = useCallback(
    async (filePath: string) => {
      const existing = tabs.find((t) => t.path === filePath);
      if (existing) {
        setActiveTabId(existing.id);
        setShowOpenDialog(false);
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
          toast({
            title: "New file",
            description: `${filePath} will be created when you save it`,
          });
        }
      }
    },
    [server.id, tabs, toast],
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
    [server.id, tabs, toast],
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

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden" onKeyDown={handleKeyDown}>
      {/* Tab bar */}
      <div className="flex items-center gap-0.5 border-b border-border/60 bg-muted/30 px-1">
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
                  "group flex items-center gap-1.5 rounded-t-md px-3 py-1.5 text-xs transition-colors",
                  activeTabId === tab.id
                    ? "bg-card text-foreground border border-b-0 border-border/60"
                    : "text-muted-foreground hover:text-foreground hover:bg-card/50",
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
                  className="ml-0.5 flex h-4 w-4 items-center justify-center rounded opacity-0 group-hover:opacity-100 hover:bg-muted transition-opacity"
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
          className="h-7 w-7 shrink-0 p-0"
          onClick={() => setShowOpenDialog(true)}
        >
          <Plus className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Open file dialog */}
      {showOpenDialog && (
        <div className="border-b border-border/60 bg-muted/20 px-4 py-3">
          <div className="flex items-center gap-2">
            <FolderOpen className="h-4 w-4 shrink-0 text-muted-foreground" />
            <Input
              value={openPath}
              onChange={(e) => setOpenPath(e.target.value)}
              placeholder="/etc/nginx/nginx.conf or relative path (new files are allowed)..."
              className="h-8 flex-1 font-mono text-xs"
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
              className="h-8 text-xs"
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
                className="h-8 text-xs"
                onClick={() => setShowOpenDialog(false)}
              >
                Cancel
              </Button>
            )}
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
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
                className="rounded-full border border-border/70 bg-background/90 px-2 py-0.5 text-[10px] text-muted-foreground hover:text-foreground hover:border-primary/30 transition-colors"
              >
                {path}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Editor area */}
      <div className="min-h-0 flex-1 overflow-hidden">
        {!activeTab ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            <div className="text-center">
              <FileCode2 className="mx-auto mb-3 h-8 w-8 text-muted-foreground/50" />
              <div>Open a file to start editing</div>
              <div className="mt-1 text-xs">Enter a file path or click a quick-open preset</div>
            </div>
          </div>
        ) : activeTab.loading ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
            <span className="ml-2 text-sm text-muted-foreground">Loading {activeTab.filename}...</span>
          </div>
        ) : activeTab.error ? (
          <div className="flex h-full items-center justify-center p-6">
            <div className="max-w-md rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-center">
              <AlertTriangle className="mx-auto h-5 w-5 text-destructive" />
              <div className="mt-2 text-sm text-destructive">{activeTab.error}</div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="mt-3 h-8 text-xs"
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
            className="h-full w-full resize-none border-0 bg-card p-4 font-mono text-[13px] leading-6 text-foreground outline-none selection:bg-primary/20"
            style={{ tabSize: 4 }}
          />
        )}
      </div>

      {/* Status bar */}
      <footer className="flex h-7 items-center justify-between border-t border-border/60 bg-muted/30 px-3 text-[11px] text-muted-foreground">
        <div className="flex items-center gap-3">
          {activeTab && (
            <>
              <span className="font-mono truncate max-w-64">{activeTab.path}</span>
              <span>{getLanguageHint(activeTab.filename)}</span>
              <span>{activeTab.encoding}</span>
              {activeTab.isNew && (
                <span className="rounded-full bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-400">New file</span>
              )}
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          {activeTab && (
            <>
              {activeTab.dirty && (
                <span className="rounded-full bg-primary/15 px-1.5 py-0.5 text-[10px] text-primary">Modified</span>
              )}
              <span>{activeTab.content.split("\n").length} lines</span>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-5 gap-1 px-1.5 text-[11px]"
                onClick={() => void saveFile(activeTab.id)}
                disabled={!activeTab.dirty}
              >
                <Save className="h-3 w-3" />
                Save
              </Button>
            </>
          )}
        </div>
      </footer>
    </div>
  );
}
