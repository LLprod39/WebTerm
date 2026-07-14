/**
 * Floating resizable/draggable window for editing remote files via SFTP.
 *
 * Uses CodeEditor (CodeMirror 6) for syntax highlighting.
 * Multi-tab support, Ctrl+S save, unsaved-changes guard.
 * Can be minimized to a small bar or maximized to fill screen.
 * Supports elevated (sudo) open/save when permission is denied.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Copy,
  FileCode2,
  FolderOpen,
  Loader2,
  Maximize2,
  Minimize2,
  Minus,
  Plus,
  RefreshCw,
  Save,
  Shield,
  X,
  AlertTriangle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { UnsavedChangesDialog } from "@/components/system/ConfirmDialog";
import { useToast } from "@/hooks/use-toast";
import { useI18n } from "@/lib/i18n";
import {
  isElevatableFileError,
  readServerTextFile,
  writeServerTextFile,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { CodeEditor } from "./CodeEditor";
import { getLanguageLabel } from "./codeEditorLanguage";

/* ------------------------------------------------------------------ */
/*  Types                                                               */
/* ------------------------------------------------------------------ */

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
  elevated: boolean;
}

type SudoPrompt =
  | { kind: "open"; tabId: string; path: string }
  | { kind: "save"; tabId: string; path: string }
  | null;

let _tabSeq = 0;
function nextTabId() {
  _tabSeq += 1;
  return `ftab_${_tabSeq}`;
}

/* ------------------------------------------------------------------ */
/*  Props                                                               */
/* ------------------------------------------------------------------ */

export interface FileEditorModalProps {
  serverId: number;
  open: boolean;
  initialPath?: string | null;
  /** Prefer elevated open (e.g. intercept of `sudo nano …`). */
  initialElevated?: boolean;
  onClose: () => void;
}

/* ------------------------------------------------------------------ */
/*  Component                                                           */
/* ------------------------------------------------------------------ */

type WindowMode = "normal" | "minimized" | "maximized";

const DEFAULT_RECT = { x: 80, y: 60, w: 900, h: 560 };

export function FileEditorModal({
  serverId,
  open,
  initialPath,
  initialElevated = false,
  onClose,
}: FileEditorModalProps) {
  const { t } = useI18n();
  const { toast } = useToast();
  const [tabs, setTabs] = useState<EditorTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);
  const [openPath, setOpenPath] = useState("");
  const [showOpen, setShowOpen] = useState(false);
  const [confirmCloseOpen, setConfirmCloseOpen] = useState(false);
  const [sudoPrompt, setSudoPrompt] = useState<SudoPrompt>(null);
  const [sudoPassword, setSudoPassword] = useState("");
  const [sudoBusy, setSudoBusy] = useState(false);
  const consumedPathRef = useRef<string | null>(null);

  /* ---- window state ---- */
  const [mode, setMode] = useState<WindowMode>("normal");
  const [rect, setRect] = useState(DEFAULT_RECT);
  const dragRef = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null);
  const resizeRef = useRef<{ startX: number; startY: number; origW: number; origH: number; origX: number; origY: number } | null>(null);
  const windowRef = useRef<HTMLDivElement>(null);

  const activeTab = tabs.find((tb) => tb.id === activeTabId) ?? null;
  const lineCount = useMemo(() => (activeTab ? activeTab.content.split("\n").length : 0), [activeTab]);
  const charCount = useMemo(() => (activeTab ? activeTab.content.length : 0), [activeTab]);
  const tabCountLabel = useMemo(() => {
    const suffix = tabs.length === 1 ? t("editor.tabSingular") : t("editor.tabPlural");
    return `${tabs.length} ${suffix}`;
  }, [tabs.length, t]);

  /* ---- drag title bar ---- */
  // Drag/resize read start geometry only from refs so a null ref or a
  // stale setState closure cannot crash the whole Terminal page (white screen).
  const onDragStart = useCallback((e: React.MouseEvent) => {
    if (mode === "maximized") return;
    const target = e.target as HTMLElement | null;
    if (target?.closest("button, input, a, [role='button'], [data-no-drag]")) return;

    e.preventDefault();
    e.stopPropagation();
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      origX: rect.x,
      origY: rect.y,
    };

    const onMove = (ev: MouseEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      const dx = ev.clientX - drag.startX;
      const dy = ev.clientY - drag.startY;
      const maxX = Math.max(0, window.innerWidth - 120);
      const maxY = Math.max(0, window.innerHeight - 48);
      try {
        setRect((r) => ({
          ...r,
          x: Math.min(maxX, Math.max(-r.w + 120, drag.origX + dx)),
          y: Math.min(maxY, Math.max(0, drag.origY + dy)),
        }));
      } catch {
        // never let drag update take down the tree
      }
    };
    const onUp = () => {
      dragRef.current = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("blur", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("blur", onUp);
  }, [mode, rect.x, rect.y]);

  /* ---- resize ---- */
  const onResizeStart = useCallback((e: React.MouseEvent) => {
    if (mode === "maximized") return;
    e.preventDefault();
    e.stopPropagation();
    resizeRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      origW: rect.w,
      origH: rect.h,
      origX: rect.x,
      origY: rect.y,
    };

    const onMove = (ev: MouseEvent) => {
      const resize = resizeRef.current;
      if (!resize) return;
      const dx = ev.clientX - resize.startX;
      const dy = ev.clientY - resize.startY;
      try {
        setRect((r) => ({
          ...r,
          w: Math.max(480, resize.origW + dx),
          h: Math.max(300, resize.origH + dy),
        }));
      } catch {
        // never let resize update take down the tree
      }
    };
    const onUp = () => {
      resizeRef.current = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("blur", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("blur", onUp);
  }, [mode, rect.w, rect.h, rect.x, rect.y]);

  /* ---- open file ---- */
  const openFile = useCallback(
    async (filePath: string, opts?: { preferElevated?: boolean; sudoPassword?: string }) => {
      const preferElevated = Boolean(opts?.preferElevated);
      const password = opts?.sudoPassword;
      const existing = tabs.find((tb) => tb.path === filePath);
      if (existing && !preferElevated && !password) {
        setActiveTabId(existing.id);
        setShowOpen(false);
        return;
      }
      const id = existing?.id || nextTabId();
      const filename = filePath.split("/").pop() || filePath;
      if (!existing) {
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
          elevated: preferElevated,
        };
        setTabs((prev) => [...prev, newTab]);
      } else {
        setTabs((prev) =>
          prev.map((tb) => (tb.id === id ? { ...tb, loading: true, error: null } : tb)),
        );
      }
      setActiveTabId(id);
      setShowOpen(false);
      if (mode === "minimized") setMode("normal");

      const applyContent = (content: string, encoding: string, elevated: boolean) => {
        setTabs((prev) =>
          prev.map((tb) =>
            tb.id === id
              ? {
                  ...tb,
                  content,
                  originalContent: content,
                  encoding: encoding || "utf-8",
                  loading: false,
                  error: null,
                  elevated,
                  isNew: false,
                  dirty: false,
                }
              : tb,
          ),
        );
      };

      try {
        // 1) If elevated preferred, try elevate first (stored sudo / NOPASSWD).
        if (preferElevated || password) {
          const res = await readServerTextFile(serverId, filePath, {
            elevate: true,
            sudoPassword: password,
          });
          if (!res.success) throw new Error(t("editor.sudoOpenFailed"));
          applyContent(res.file.content, res.file.encoding || "utf-8", true);
          if (preferElevated || password) {
            toast({ title: t("editor.elevatedOpen"), description: filePath });
          }
          return;
        }

        // 2) Normal SFTP read
        const res = await readServerTextFile(serverId, filePath);
        if (!res.success) throw new Error("Failed to read file");
        applyContent(res.file.content, res.file.encoding || "utf-8", false);
      } catch (err) {
        if (isElevatableFileError(err) && !password) {
          // Try silent elevate with stored sudo first
          try {
            const elevated = await readServerTextFile(serverId, filePath, { elevate: true });
            if (!elevated.success) throw new Error(t("editor.sudoOpenFailed"));
            applyContent(elevated.file.content, elevated.file.encoding || "utf-8", true);
            toast({ title: t("editor.elevatedOpen"), description: filePath });
            return;
          } catch (elevErr) {
            if (isElevatableFileError(elevErr)) {
              setTabs((prev) =>
                prev.map((tb) =>
                  tb.id === id ? { ...tb, loading: false, error: null } : tb,
                ),
              );
              setSudoPrompt({ kind: "open", tabId: id, path: filePath });
              setSudoPassword("");
              return;
            }
            const message = elevErr instanceof Error ? elevErr.message : t("editor.sudoOpenFailed");
            setTabs((prev) =>
              prev.map((tb) => (tb.id === id ? { ...tb, loading: false, error: message } : tb)),
            );
            return;
          }
        }

        const message = err instanceof Error ? err.message : "Failed to read file";
        const notFound = /не найден|not found|404/i.test(message);
        setTabs((prev) =>
          prev.map((tb) =>
            tb.id === id
              ? notFound
                ? {
                    ...tb,
                    content: "",
                    originalContent: "",
                    isNew: true,
                    loading: false,
                    error: null,
                    elevated: false,
                  }
                : { ...tb, loading: false, error: message }
              : tb,
          ),
        );
        if (notFound) toast({ title: t("editor.newFile"), description: `${filePath} — ${t("editor.willCreate")}` });
      }
    },
    [serverId, tabs, toast, t, mode],
  );

  /* ---- initial path ---- */
  useEffect(() => {
    if (!open || !initialPath) return;
    const key = `${initialPath}::${initialElevated ? "1" : "0"}`;
    if (consumedPathRef.current === key) return;
    consumedPathRef.current = key;
    void openFile(initialPath, { preferElevated: initialElevated });
  }, [open, initialPath, initialElevated, openFile]);

  useEffect(() => {
    if (!open) {
      consumedPathRef.current = null;
      setSudoPrompt(null);
      setSudoPassword("");
    }
  }, [open]);

  /* ---- save ---- */
  const savingRef = useRef<Set<string>>(new Set());
  const saveFile = useCallback(
    async (tabId: string, opts?: { elevate?: boolean; sudoPassword?: string }) => {
      if (savingRef.current.has(tabId)) return;
      const tab = tabs.find((tb) => tb.id === tabId);
      if (!tab) return;
      savingRef.current.add(tabId);
      const elevate = Boolean(opts?.elevate || tab.elevated);
      try {
        const res = await writeServerTextFile(serverId, tab.path, tab.content, {
          elevate,
          sudoPassword: opts?.sudoPassword,
        });
        if (!res.success) throw new Error("Save failed");
        setTabs((prev) =>
          prev.map((tb) =>
            tb.id === tabId
              ? { ...tb, originalContent: tb.content, dirty: false, isNew: false, elevated: elevate || tb.elevated }
              : tb,
          ),
        );
        toast({ title: t("editor.saved"), description: tab.filename });
      } catch (err) {
        if (isElevatableFileError(err) && !opts?.elevate && !tab.elevated) {
          // Try stored/NOPASSWD elevate once
          try {
            const elevated = await writeServerTextFile(serverId, tab.path, tab.content, { elevate: true });
            if (!elevated.success) throw new Error(t("editor.sudoSaveFailed"));
            setTabs((prev) =>
              prev.map((tb) =>
                tb.id === tabId
                  ? { ...tb, originalContent: tb.content, dirty: false, isNew: false, elevated: true }
                  : tb,
              ),
            );
            toast({ title: t("editor.saved"), description: `${tab.filename} (sudo)` });
            return;
          } catch (elevErr) {
            if (isElevatableFileError(elevErr)) {
              setSudoPrompt({ kind: "save", tabId, path: tab.path });
              setSudoPassword("");
              return;
            }
            toast({
              title: t("editor.saveFailed"),
              description: elevErr instanceof Error ? elevErr.message : t("editor.sudoSaveFailed"),
              variant: "destructive",
            });
            return;
          }
        }
        toast({
          title: t("editor.saveFailed"),
          description: err instanceof Error ? err.message : "Error",
          variant: "destructive",
        });
      } finally {
        savingRef.current.delete(tabId);
      }
    },
    [serverId, tabs, toast, t],
  );

  const submitSudoPrompt = useCallback(async () => {
    if (!sudoPrompt) return;
    setSudoBusy(true);
    try {
      if (sudoPrompt.kind === "open") {
        await openFile(sudoPrompt.path, {
          preferElevated: true,
          sudoPassword: sudoPassword || undefined,
        });
      } else {
        await saveFile(sudoPrompt.tabId, {
          elevate: true,
          sudoPassword: sudoPassword || undefined,
        });
      }
      setSudoPrompt(null);
      setSudoPassword("");
    } finally {
      setSudoBusy(false);
    }
  }, [sudoPrompt, sudoPassword, openFile, saveFile]);

  /* ---- reload ---- */
  const reloadFile = useCallback(
    async (tabId: string) => {
      const tab = tabs.find((tb) => tb.id === tabId);
      if (!tab || tab.isNew) return;
      setTabs((prev) => prev.map((tb) => (tb.id === tabId ? { ...tb, loading: true, error: null } : tb)));
      try {
        const res = await readServerTextFile(serverId, tab.path, tab.elevated ? { elevate: true } : {});
        if (!res.success) throw new Error("Reload failed");
        setTabs((prev) =>
          prev.map((tb) =>
            tb.id === tabId
              ? {
                  ...tb,
                  content: res.file.content,
                  originalContent: res.file.content,
                  encoding: res.file.encoding || "utf-8",
                  dirty: false,
                  loading: false,
                  error: null,
                }
              : tb,
          ),
        );
      } catch (err) {
        setTabs((prev) =>
          prev.map((tb) =>
            tb.id === tabId
              ? { ...tb, loading: false, error: err instanceof Error ? err.message : "Reload failed" }
              : tb,
          ),
        );
      }
    },
    [serverId, tabs],
  );

  /* ---- close tab ---- */
  const closeTab = useCallback(
    (tabId: string) => {
      setTabs((prev) => {
        const next = prev.filter((tb) => tb.id !== tabId);
        if (activeTabId === tabId) {
          const idx = prev.findIndex((tb) => tb.id === tabId);
          const fallback = next[Math.min(idx, next.length - 1)]?.id ?? null;
          setActiveTabId(fallback);
          if (!fallback) setShowOpen(true);
        }
        return next;
      });
    },
    [activeTabId],
  );

  /* ---- content update ---- */
  const updateContent = useCallback((tabId: string, value: string) => {
    setTabs((prev) =>
      prev.map((tb) => (tb.id === tabId ? { ...tb, content: value, dirty: value !== tb.originalContent } : tb)),
    );
  }, []);

  /* ---- copy path ---- */
  const copyPath = useCallback(async () => {
    if (!activeTab?.path) return;
    await navigator.clipboard.writeText(activeTab.path);
    toast({ title: t("editor.pathCopied"), description: activeTab.path });
  }, [activeTab?.path, toast, t]);

  const closeWindow = useCallback(() => {
    setTabs([]);
    setActiveTabId(null);
    setShowOpen(false);
    setMode("normal");
    setSudoPrompt(null);
    setSudoPassword("");
    onClose();
  }, [onClose]);

  /* ---- close window ---- */
  const handleClose = useCallback(() => {
    const dirty = tabs.some((tb) => tb.dirty);
    if (dirty) {
      setConfirmCloseOpen(true);
      return;
    }
    closeWindow();
  }, [closeWindow, tabs]);

  /* ---- keyboard ---- */
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        if (activeTabId) void saveFile(activeTabId);
      }
      if (e.key === "Escape") {
        e.preventDefault();
        handleClose();
      }
    },
    [activeTabId, saveFile, handleClose],
  );

  /* ---- toggle maximize ---- */
  const toggleMaximize = useCallback(() => {
    setMode((m) => (m === "maximized" ? "normal" : "maximized"));
  }, []);

  if (!open) return null;

  const sudoDialog = (
    <Dialog
      open={Boolean(sudoPrompt)}
      onOpenChange={(next) => {
        if (!next) {
          setSudoPrompt(null);
          setSudoPassword("");
        }
      }}
    >
      <DialogContent className="z-[90] max-w-md" closeLabel={t("editor.cancel")}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-amber-400" />
            {t("editor.sudoTitle")}
          </DialogTitle>
          <DialogDescription>
            {t("editor.sudoDescription")}
            {sudoPrompt?.path ? (
              <span className="mt-2 block font-mono text-xs text-foreground/80">{sudoPrompt.path}</span>
            ) : null}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <label className="block text-xs font-medium text-muted-foreground" htmlFor="editor-sudo-password">
            {t("editor.sudoPassword")}
          </label>
          <Input
            id="editor-sudo-password"
            type="password"
            autoComplete="current-password"
            value={sudoPassword}
            onChange={(e) => setSudoPassword(e.target.value)}
            placeholder={t("editor.sudoPasswordPlaceholder")}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void submitSudoPrompt();
              }
            }}
            autoFocus
          />
        </DialogBody>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            disabled={sudoBusy}
            onClick={() => {
              setSudoPrompt(null);
              setSudoPassword("");
            }}
          >
            {t("editor.cancel")}
          </Button>
          <Button type="button" disabled={sudoBusy} onClick={() => void submitSudoPrompt()}>
            {sudoBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Shield className="mr-2 h-4 w-4" />}
            {sudoPassword ? t("editor.sudoSubmit") : t("editor.sudoRetryStored")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  const unsavedCloseDialog = (
    <UnsavedChangesDialog
      open={confirmCloseOpen}
      onOpenChange={setConfirmCloseOpen}
      title={t("editor.unsavedTitle")}
      description={t("editor.unsavedWarn")}
      confirmLabel={t("editor.discardChanges")}
      cancelLabel={t("editor.cancel")}
      onConfirm={() => {
        setConfirmCloseOpen(false);
        closeWindow();
      }}
    />
  );

  /* ---- minimized bar ---- */
  if (mode === "minimized") {
    return (
      <>
        <div className="fixed bottom-4 left-4 z-[60] flex h-10 items-center gap-2 rounded-lg border border-white/10 bg-[#161b22] px-3 shadow-xl cursor-pointer select-none">
          <button
            type="button"
            className="flex min-w-0 items-center gap-2 text-left"
            onClick={() => setMode("normal")}
            aria-label={t("editor.restoreWindow")}
            title={t("editor.restoreWindow")}
          >
            <FileCode2 className="h-4 w-4 text-blue-400" />
            <span className="text-xs font-medium text-zinc-300">{t("editor.title")}</span>
            {tabs.some((tb) => tb.dirty) && <span className="h-2 w-2 rounded-full bg-blue-500" />}
            <span className="text-xs text-zinc-500">{tabCountLabel}</span>
          </button>
          <button
            type="button"
            onClick={handleClose}
            className="ml-1 rounded p-0.5 text-zinc-500 hover:text-zinc-200 hover:bg-white/10"
            aria-label={t("editor.closeWindow")}
            title={t("editor.closeWindow")}
          >
            <X className="h-3 w-3" />
          </button>
        </div>
        {unsavedCloseDialog}
        {sudoDialog}
      </>
    );
  }

  const isMax = mode === "maximized";
  const style: React.CSSProperties = isMax
    ? { position: "fixed", inset: 0, width: "100%", height: "100%" }
    : { position: "fixed", left: rect.x, top: rect.y, width: rect.w, height: rect.h };

  return (
    <>
      <div
        ref={windowRef}
        role="dialog"
        aria-modal="true"
        aria-label={t("editor.title")}
        className={cn(
          "z-[60] flex flex-col bg-[#0d1117] shadow-2xl border border-white/10",
          isMax ? "rounded-none" : "rounded-lg",
        )}
        style={style}
        onKeyDown={handleKeyDown}
      >
        {/* ---- title bar (draggable) ---- */}
        <div
          className={cn(
            "flex items-center gap-2 border-b border-white/10 bg-[#161b22] px-3 py-1.5 select-none",
            isMax ? "" : "cursor-move rounded-t-lg",
          )}
          onMouseDown={onDragStart}
          onDoubleClick={toggleMaximize}
        >
          <FileCode2 className="h-3.5 w-3.5 text-blue-400 shrink-0" />
          <span className="text-xs font-semibold text-zinc-200 truncate">{t("editor.title")}</span>
          {activeTab && (
            <span className="text-xs text-zinc-500 truncate hidden sm:inline">— {activeTab.path}</span>
          )}
          {activeTab?.elevated && (
            <span className="inline-flex items-center gap-1 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-300">
              <Shield className="h-3 w-3" />
              {t("editor.elevatedBadge")}
            </span>
          )}

          <div className="ml-auto flex items-center gap-0.5 shrink-0" data-no-drag>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0 text-zinc-400 hover:text-zinc-200"
              onClick={() => setShowOpen(true)}
              title={t("editor.open")}
              aria-label={t("editor.open")}
            >
              <FolderOpen className="h-3 w-3" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0 text-zinc-400 hover:text-zinc-200"
              onClick={() => activeTabId && void saveFile(activeTabId)}
              disabled={!activeTab?.dirty}
              title={t("editor.save")}
              aria-label={t("editor.save")}
            >
              <Save className="h-3 w-3" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0 text-zinc-400 hover:text-zinc-200"
              onClick={() => activeTabId && void reloadFile(activeTabId)}
              disabled={!activeTab || activeTab.isNew}
              title={t("editor.reload")}
              aria-label={t("editor.reload")}
            >
              <RefreshCw className="h-3 w-3" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0 text-zinc-400 hover:text-zinc-200"
              onClick={copyPath}
              disabled={!activeTab}
              title={t("editor.copyPath")}
              aria-label={t("editor.copyPath")}
            >
              <Copy className="h-3 w-3" />
            </Button>
            <div className="mx-1 h-4 w-px bg-white/10" />
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0 text-zinc-400 hover:text-yellow-400"
              onClick={() => setMode("minimized")}
              title={t("editor.minimize")}
              aria-label={t("editor.minimize")}
            >
              <Minus className="h-3 w-3" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0 text-zinc-400 hover:text-zinc-200"
              onClick={toggleMaximize}
              title={isMax ? t("editor.restoreWindow") : t("editor.maximize")}
              aria-label={isMax ? t("editor.restoreWindow") : t("editor.maximize")}
            >
              {isMax ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0 text-zinc-400 hover:text-red-400"
              onClick={handleClose}
              title={t("editor.closeWindow")}
              aria-label={t("editor.closeWindow")}
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {/* ---- tab bar ---- */}
        <div className="flex items-center gap-0.5 border-b border-white/5 bg-[#0d1117] px-2 py-0.5 overflow-x-auto">
          {tabs.map((tab) => (
            <div
              key={tab.id}
              className={cn(
                "group flex items-center gap-1.5 rounded px-2 py-0.5 text-xs transition-colors shrink-0",
                activeTabId === tab.id
                  ? "bg-[#161b22] text-zinc-200"
                  : "text-zinc-500 hover:bg-white/5 hover:text-zinc-300",
              )}
            >
              <button
                type="button"
                onClick={() => {
                  setActiveTabId(tab.id);
                  setShowOpen(false);
                }}
                className="flex min-w-0 items-center gap-1.5 text-left"
                aria-label={
                  tab.dirty
                    ? `${t("editor.openTab")} ${tab.filename}, ${t("editor.modified")}`
                    : `${t("editor.openTab")} ${tab.filename}`
                }
                title={tab.path}
              >
                <FileCode2 className="h-3 w-3 shrink-0" />
                <span className="max-w-28 truncate">{tab.filename}</span>
                {tab.elevated && <Shield className="h-3 w-3 text-amber-400 shrink-0" />}
                {tab.dirty && <span className="h-1.5 w-1.5 rounded-full bg-blue-500 shrink-0" />}
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  closeTab(tab.id);
                }}
                className="ml-0.5 flex h-3.5 w-3.5 items-center justify-center rounded opacity-0 group-hover:opacity-100 hover:bg-white/10"
                aria-label={`${t("editor.closeTab")} ${tab.filename}`}
                title={t("editor.closeTab")}
              >
                <X className="h-2.5 w-2.5" />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => setShowOpen(true)}
            className="ml-1 flex h-5 w-5 items-center justify-center rounded text-zinc-500 hover:bg-white/5 hover:text-zinc-300 shrink-0"
            aria-label={t("editor.open")}
            title={t("editor.open")}
          >
            <Plus className="h-3 w-3" />
          </button>
        </div>

        {/* ---- open dialog ---- */}
        {showOpen && (
          <div className="border-b border-white/5 bg-[#161b22] px-3 py-2">
            <div className="flex items-center gap-2">
              <FolderOpen className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
              <Input
                value={openPath}
                onChange={(e) => setOpenPath(e.target.value)}
                placeholder={t("editor.pathPlaceholder")}
                aria-label={t("editor.pathInput")}
                className="h-7 flex-1 border-zinc-700 bg-[#0d1117] font-mono text-xs text-zinc-200 placeholder:text-zinc-600"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && openPath.trim()) {
                    e.preventDefault();
                    void openFile(openPath.trim());
                  }
                }}
                autoFocus
              />
              <Button
                size="sm"
                className="h-7 text-xs"
                disabled={!openPath.trim()}
                onClick={() => void openFile(openPath.trim())}
              >
                {t("editor.openBtn")}
              </Button>
              {tabs.length > 0 && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 text-xs text-zinc-500"
                  onClick={() => setShowOpen(false)}
                >
                  {t("editor.cancel")}
                </Button>
              )}
            </div>
          </div>
        )}

        {/* ---- editor area ---- */}
        <div className="min-h-0 flex-1 overflow-hidden">
          {!activeTab ? (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <FileCode2 className="mx-auto mb-2 h-8 w-8 text-zinc-700" />
                <div className="text-xs text-zinc-500">{t("editor.emptyHint")}</div>
              </div>
            </div>
          ) : activeTab.loading ? (
            <div className="flex h-full items-center justify-center">
              <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
              <span className="ml-2 text-xs text-zinc-500">
                {t("editor.loading")} {activeTab.filename}…
              </span>
            </div>
          ) : activeTab.error ? (
            <div className="flex h-full items-center justify-center p-4">
              <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-4 text-center">
                <AlertTriangle className="mx-auto h-5 w-5 text-red-400" />
                <div className="mt-1 text-xs text-red-300">{activeTab.error}</div>
                <div className="mt-2 flex items-center justify-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-xs"
                    onClick={() => void openFile(activeTab.path, { preferElevated: true })}
                  >
                    <Shield className="mr-1 h-3 w-3" />
                    {t("editor.sudoRetryStored")}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-xs"
                    onClick={() => {
                      closeTab(activeTab.id);
                      setShowOpen(true);
                    }}
                  >
                    {t("editor.tryAnother")}
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <CodeEditor
              content={activeTab.content}
              filename={activeTab.filename}
              onChange={(value) => updateContent(activeTab.id, value)}
              onSave={() => void saveFile(activeTab.id)}
            />
          )}
        </div>

        {/* ---- status bar ---- */}
        <div
          className={cn(
            "flex h-6 items-center justify-between border-t border-white/5 bg-[#161b22] px-3 text-xs text-zinc-500",
            !isMax && "rounded-b-lg",
          )}
        >
          <div className="flex items-center gap-2">
            {activeTab && (
              <>
                <span className="max-w-48 truncate font-mono">{activeTab.path}</span>
                <span>{getLanguageLabel(activeTab.filename)}</span>
                <span>{activeTab.encoding}</span>
                {activeTab.isNew && (
                  <span className="rounded bg-zinc-800 px-1 py-0.5 text-xs">{t("editor.newFile")}</span>
                )}
                {activeTab.elevated && (
                  <span className="rounded bg-amber-500/10 px-1 py-0.5 text-xs text-amber-300">
                    {t("editor.elevatedBadge")}
                  </span>
                )}
              </>
            )}
          </div>
          <div className="flex items-center gap-2">
            {activeTab?.dirty && (
              <span className="rounded bg-blue-500/10 px-1 py-0.5 text-xs text-blue-400">
                {t("editor.modified")}
              </span>
            )}
            {activeTab && (
              <>
                <span>
                  {lineCount} {t("editor.lines")}
                </span>
                <span>
                  {charCount} {t("editor.chars")}
                </span>
              </>
            )}
          </div>
        </div>

        {/* ---- resize handle ---- */}
        {!isMax && (
          <div
            className="absolute bottom-0 right-0 h-4 w-4 cursor-nwse-resize"
            onMouseDown={onResizeStart}
            style={{
              background: "linear-gradient(135deg, transparent 50%, rgba(255,255,255,0.15) 50%)",
              borderRadius: "0 0 0.5rem 0",
            }}
          />
        )}
      </div>
      {unsavedCloseDialog}
      {sudoDialog}
    </>
  );
}
