/**
 * Floating resizable/draggable window for editing remote files via SFTP.
 *
 * Uses CodeEditor (CodeMirror 6) for syntax highlighting.
 * Multi-tab support, Ctrl+S save, unsaved-changes guard.
 * Can be minimized to a small bar or maximized to fill screen.
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
  X,
  AlertTriangle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { useI18n } from "@/lib/i18n";
import { readServerTextFile, writeServerTextFile } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CodeEditor, getLanguageLabel } from "./CodeEditor";

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
}

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
  onClose: () => void;
}

/* ------------------------------------------------------------------ */
/*  Component                                                           */
/* ------------------------------------------------------------------ */

type WindowMode = "normal" | "minimized" | "maximized";

const DEFAULT_RECT = { x: 80, y: 60, w: 900, h: 560 };

export function FileEditorModal({ serverId, open, initialPath, onClose }: FileEditorModalProps) {
  const { t } = useI18n();
  const { toast } = useToast();
  const [tabs, setTabs] = useState<EditorTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);
  const [openPath, setOpenPath] = useState("");
  const [showOpen, setShowOpen] = useState(false);
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

  /* ---- drag title bar ---- */
  const onDragStart = useCallback((e: React.MouseEvent) => {
    if (mode === "maximized") return;
    e.preventDefault();
    dragRef.current = { startX: e.clientX, startY: e.clientY, origX: rect.x, origY: rect.y };
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const dx = ev.clientX - dragRef.current.startX;
      const dy = ev.clientY - dragRef.current.startY;
      setRect((r) => ({ ...r, x: dragRef.current!.origX + dx, y: Math.max(0, dragRef.current!.origY + dy) }));
    };
    const onUp = () => { dragRef.current = null; window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, [mode, rect.x, rect.y]);

  /* ---- resize ---- */
  const onResizeStart = useCallback((e: React.MouseEvent) => {
    if (mode === "maximized") return;
    e.preventDefault();
    e.stopPropagation();
    resizeRef.current = { startX: e.clientX, startY: e.clientY, origW: rect.w, origH: rect.h, origX: rect.x, origY: rect.y };
    const onMove = (ev: MouseEvent) => {
      if (!resizeRef.current) return;
      const dx = ev.clientX - resizeRef.current.startX;
      const dy = ev.clientY - resizeRef.current.startY;
      setRect((r) => ({ ...r, w: Math.max(480, resizeRef.current!.origW + dx), h: Math.max(300, resizeRef.current!.origH + dy) }));
    };
    const onUp = () => { resizeRef.current = null; window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, [mode, rect.w, rect.h]);

  /* ---- open file ---- */
  const openFile = useCallback(
    async (filePath: string) => {
      const existing = tabs.find((tb) => tb.path === filePath);
      if (existing) { setActiveTabId(existing.id); setShowOpen(false); return; }
      const id = nextTabId();
      const filename = filePath.split("/").pop() || filePath;
      const newTab: EditorTab = { id, path: filePath, filename, content: "", originalContent: "", encoding: "utf-8", isNew: false, dirty: false, loading: true, error: null };
      setTabs((prev) => [...prev, newTab]);
      setActiveTabId(id);
      setShowOpen(false);
      if (mode === "minimized") setMode("normal");
      try {
        const res = await readServerTextFile(serverId, filePath);
        if (!res.success) throw new Error("Failed to read file");
        setTabs((prev) => prev.map((tb) => tb.id === id ? { ...tb, content: res.file.content, originalContent: res.file.content, encoding: res.file.encoding || "utf-8", loading: false } : tb));
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to read file";
        const notFound = /не найден|not found|404/i.test(message);
        setTabs((prev) => prev.map((tb) => tb.id === id ? (notFound ? { ...tb, content: "", originalContent: "", isNew: true, loading: false, error: null } : { ...tb, loading: false, error: message }) : tb));
        if (notFound) toast({ title: t("editor.newFile"), description: `${filePath} — ${t("editor.willCreate")}` });
      }
    },
    [serverId, tabs, toast, t, mode],
  );

  /* ---- initial path ---- */
  useEffect(() => {
    if (!open || !initialPath) return;
    if (consumedPathRef.current === initialPath) return;
    consumedPathRef.current = initialPath;
    void openFile(initialPath);
  }, [open, initialPath, openFile]);

  useEffect(() => { if (!open) consumedPathRef.current = null; }, [open]);

  /* ---- save ---- */
  const savingRef = useRef<Set<string>>(new Set());
  const saveFile = useCallback(async (tabId: string) => {
    if (savingRef.current.has(tabId)) return;
    const tab = tabs.find((tb) => tb.id === tabId);
    if (!tab) return;
    savingRef.current.add(tabId);
    try {
      const res = await writeServerTextFile(serverId, tab.path, tab.content);
      if (!res.success) throw new Error("Save failed");
      setTabs((prev) => prev.map((tb) => (tb.id === tabId ? { ...tb, originalContent: tb.content, dirty: false, isNew: false } : tb)));
      toast({ title: t("editor.saved"), description: tab.filename });
    } catch (err) {
      toast({ title: t("editor.saveFailed"), description: err instanceof Error ? err.message : "Error", variant: "destructive" });
    } finally {
      savingRef.current.delete(tabId);
    }
  }, [serverId, tabs, toast, t]);

  /* ---- reload ---- */
  const reloadFile = useCallback(async (tabId: string) => {
    const tab = tabs.find((tb) => tb.id === tabId);
    if (!tab || tab.isNew) return;
    setTabs((prev) => prev.map((tb) => (tb.id === tabId ? { ...tb, loading: true, error: null } : tb)));
    try {
      const res = await readServerTextFile(serverId, tab.path);
      if (!res.success) throw new Error("Reload failed");
      setTabs((prev) => prev.map((tb) => tb.id === tabId ? { ...tb, content: res.file.content, originalContent: res.file.content, encoding: res.file.encoding || "utf-8", dirty: false, loading: false, error: null } : tb));
    } catch (err) {
      setTabs((prev) => prev.map((tb) => (tb.id === tabId ? { ...tb, loading: false, error: err instanceof Error ? err.message : "Reload failed" } : tb)));
    }
  }, [serverId, tabs]);

  /* ---- close tab ---- */
  const closeTab = useCallback((tabId: string) => {
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
  }, [activeTabId]);

  /* ---- content update ---- */
  const updateContent = useCallback((tabId: string, value: string) => {
    setTabs((prev) => prev.map((tb) => (tb.id === tabId ? { ...tb, content: value, dirty: value !== tb.originalContent } : tb)));
  }, []);

  /* ---- copy path ---- */
  const copyPath = useCallback(async () => {
    if (!activeTab?.path) return;
    await navigator.clipboard.writeText(activeTab.path);
    toast({ title: t("editor.pathCopied"), description: activeTab.path });
  }, [activeTab?.path, toast, t]);

  /* ---- close window ---- */
  const handleClose = useCallback(() => {
    const dirty = tabs.some((tb) => tb.dirty);
    if (dirty && !window.confirm(t("editor.unsavedWarn"))) return;
    setTabs([]);
    setActiveTabId(null);
    setShowOpen(false);
    setMode("normal");
    onClose();
  }, [tabs, onClose, t]);

  /* ---- keyboard ---- */
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); if (activeTabId) void saveFile(activeTabId); }
    if (e.key === "Escape") { e.preventDefault(); handleClose(); }
  }, [activeTabId, saveFile, handleClose]);

  /* ---- toggle maximize ---- */
  const toggleMaximize = useCallback(() => {
    setMode((m) => (m === "maximized" ? "normal" : "maximized"));
  }, []);

  if (!open) return null;

  /* ---- minimized bar ---- */
  if (mode === "minimized") {
    return (
      <div
        className="fixed bottom-4 left-4 z-[60] flex h-10 items-center gap-2 rounded-lg border border-white/10 bg-[#161b22] px-3 shadow-xl cursor-pointer select-none"
        onClick={() => setMode("normal")}
      >
        <FileCode2 className="h-4 w-4 text-blue-400" />
        <span className="text-xs font-medium text-zinc-300">{t("editor.title")}</span>
        {tabs.some((tb) => tb.dirty) && <span className="h-2 w-2 rounded-full bg-blue-500" />}
        <span className="text-[10px] text-zinc-500">{tabs.length} {tabs.length === 1 ? "tab" : "tabs"}</span>
        <button type="button" onClick={(e) => { e.stopPropagation(); handleClose(); }} className="ml-1 rounded p-0.5 text-zinc-500 hover:text-zinc-200 hover:bg-white/10">
          <X className="h-3 w-3" />
        </button>
      </div>
    );
  }

  const isMax = mode === "maximized";
  const style: React.CSSProperties = isMax
    ? { position: "fixed", inset: 0, width: "100%", height: "100%" }
    : { position: "fixed", left: rect.x, top: rect.y, width: rect.w, height: rect.h };

  return (
    <div
      ref={windowRef}
      className={cn(
        "z-[60] flex flex-col bg-[#0d1117] shadow-2xl border border-white/10",
        isMax ? "rounded-none" : "rounded-lg",
      )}
      style={style}
      onKeyDown={handleKeyDown}
    >
      {/* ---- title bar (draggable) ---- */}
      <div
        className={cn("flex items-center gap-2 border-b border-white/10 bg-[#161b22] px-3 py-1.5 select-none", isMax ? "" : "cursor-move rounded-t-lg")}
        onMouseDown={onDragStart}
        onDoubleClick={toggleMaximize}
      >
        <FileCode2 className="h-3.5 w-3.5 text-blue-400 shrink-0" />
        <span className="text-xs font-semibold text-zinc-200 truncate">{t("editor.title")}</span>
        {activeTab && <span className="text-[10px] text-zinc-500 truncate hidden sm:inline">— {activeTab.path}</span>}

        <div className="ml-auto flex items-center gap-0.5 shrink-0">
          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-zinc-400 hover:text-zinc-200" onClick={() => setShowOpen(true)} title={t("editor.open")}>
            <FolderOpen className="h-3 w-3" />
          </Button>
          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-zinc-400 hover:text-zinc-200" onClick={() => activeTabId && void saveFile(activeTabId)} disabled={!activeTab?.dirty} title={t("editor.save")}>
            <Save className="h-3 w-3" />
          </Button>
          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-zinc-400 hover:text-zinc-200" onClick={() => activeTabId && void reloadFile(activeTabId)} disabled={!activeTab || activeTab.isNew} title={t("editor.reload")}>
            <RefreshCw className="h-3 w-3" />
          </Button>
          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-zinc-400 hover:text-zinc-200" onClick={copyPath} disabled={!activeTab} title={t("editor.pathCopied")}>
            <Copy className="h-3 w-3" />
          </Button>
          <div className="mx-1 h-4 w-px bg-white/10" />
          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-zinc-400 hover:text-yellow-400" onClick={() => setMode("minimized")} title="Minimize">
            <Minus className="h-3 w-3" />
          </Button>
          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-zinc-400 hover:text-zinc-200" onClick={toggleMaximize} title={isMax ? "Restore" : "Maximize"}>
            {isMax ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
          </Button>
          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-zinc-400 hover:text-red-400" onClick={handleClose} title="Close">
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* ---- tab bar ---- */}
      <div className="flex items-center gap-0.5 border-b border-white/5 bg-[#0d1117] px-2 py-0.5 overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => { setActiveTabId(tab.id); setShowOpen(false); }}
            className={cn(
              "group flex items-center gap-1.5 rounded px-2 py-0.5 text-[11px] transition-colors shrink-0",
              activeTabId === tab.id ? "bg-[#161b22] text-zinc-200" : "text-zinc-500 hover:bg-white/5 hover:text-zinc-300",
            )}
          >
            <FileCode2 className="h-3 w-3 shrink-0" />
            <span className="max-w-28 truncate">{tab.filename}</span>
            {tab.dirty && <span className="h-1.5 w-1.5 rounded-full bg-blue-500 shrink-0" />}
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); closeTab(tab.id); }}
              className="ml-0.5 flex h-3.5 w-3.5 items-center justify-center rounded opacity-0 group-hover:opacity-100 hover:bg-white/10"
            >
              <X className="h-2.5 w-2.5" />
            </button>
          </button>
        ))}
        <button type="button" onClick={() => setShowOpen(true)} className="ml-1 flex h-5 w-5 items-center justify-center rounded text-zinc-500 hover:bg-white/5 hover:text-zinc-300 shrink-0">
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
              className="h-7 flex-1 border-zinc-700 bg-[#0d1117] font-mono text-[11px] text-zinc-200 placeholder:text-zinc-600"
              onKeyDown={(e) => { if (e.key === "Enter" && openPath.trim()) { e.preventDefault(); void openFile(openPath.trim()); } }}
              autoFocus
            />
            <Button size="sm" className="h-7 text-[11px]" disabled={!openPath.trim()} onClick={() => void openFile(openPath.trim())}>
              {t("editor.openBtn")}
            </Button>
            {tabs.length > 0 && (
              <Button size="sm" variant="ghost" className="h-7 text-[11px] text-zinc-500" onClick={() => setShowOpen(false)}>
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
            <span className="ml-2 text-xs text-zinc-500">{t("editor.loading")} {activeTab.filename}…</span>
          </div>
        ) : activeTab.error ? (
          <div className="flex h-full items-center justify-center p-4">
            <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-4 text-center">
              <AlertTriangle className="mx-auto h-5 w-5 text-red-400" />
              <div className="mt-1 text-xs text-red-300">{activeTab.error}</div>
              <Button size="sm" variant="outline" className="mt-2 text-[11px]" onClick={() => { closeTab(activeTab.id); setShowOpen(true); }}>
                {t("editor.tryAnother")}
              </Button>
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
      <div className={cn("flex h-6 items-center justify-between border-t border-white/5 bg-[#161b22] px-3 text-[10px] text-zinc-500", !isMax && "rounded-b-lg")}>
        <div className="flex items-center gap-2">
          {activeTab && (
            <>
              <span className="max-w-48 truncate font-mono">{activeTab.path}</span>
              <span>{getLanguageLabel(activeTab.filename)}</span>
              <span>{activeTab.encoding}</span>
              {activeTab.isNew && <span className="rounded bg-zinc-800 px-1 py-0.5 text-[9px]">{t("editor.newFile")}</span>}
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          {activeTab?.dirty && <span className="rounded bg-blue-500/10 px-1 py-0.5 text-[9px] text-blue-400">{t("editor.modified")}</span>}
          {activeTab && (
            <>
              <span>{lineCount} {t("editor.lines")}</span>
              <span>{charCount} {t("editor.chars")}</span>
            </>
          )}
        </div>
      </div>

      {/* ---- resize handle ---- */}
      {!isMax && (
        <div
          className="absolute bottom-0 right-0 h-4 w-4 cursor-nwse-resize"
          onMouseDown={onResizeStart}
          style={{ background: "linear-gradient(135deg, transparent 50%, rgba(255,255,255,0.15) 50%)", borderRadius: "0 0 0.5rem 0" }}
        />
      )}
    </div>
  );
}
