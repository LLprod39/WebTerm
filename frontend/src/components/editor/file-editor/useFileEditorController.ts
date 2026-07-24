import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useToast } from "@/hooks/use-toast";
import { useI18n } from "@/lib/i18n";
import {
  isElevatableFileError,
  readServerTextFile,
  writeServerTextFile,
} from "@/lib/api";

import {
  type EditorTab,
  type FileEditorModalProps,
  nextTabId,
  type SudoPrompt,
} from "./types";
import { useFileEditorWindow } from "./useFileEditorWindow";

export function useFileEditorController({
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

  const {
    mode,
    setMode,
    rect,
    windowRef,
    onDragStart,
    onResizeStart,
    toggleMaximize,
  } = useFileEditorWindow();

  const activeTab = tabs.find((tb) => tb.id === activeTabId) ?? null;
  const lineCount = useMemo(() => (activeTab ? activeTab.content.split("\n").length : 0), [activeTab]);
  const charCount = useMemo(() => (activeTab ? activeTab.content.length : 0), [activeTab]);
  const tabCountLabel = useMemo(() => {
    const suffix = tabs.length === 1 ? t("editor.tabSingular") : t("editor.tabPlural");
    return `${tabs.length} ${suffix}`;
  }, [tabs.length, t]);

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
        setTabs((prev) => prev.map((tb) => (tb.id === id ? { ...tb, loading: true, error: null } : tb)));
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
                prev.map((tb) => (tb.id === id ? { ...tb, loading: false, error: null } : tb)),
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
    [serverId, tabs, toast, t, mode, setMode],
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
  }, [onClose, setMode]);

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

  return {
    t,
    tabs,
    activeTabId,
    setActiveTabId,
    openPath,
    setOpenPath,
    showOpen,
    setShowOpen,
    confirmCloseOpen,
    setConfirmCloseOpen,
    sudoPrompt,
    setSudoPrompt,
    sudoPassword,
    setSudoPassword,
    sudoBusy,
    mode,
    setMode,
    rect,
    windowRef,
    activeTab,
    lineCount,
    charCount,
    tabCountLabel,
    onDragStart,
    onResizeStart,
    openFile,
    saveFile,
    submitSudoPrompt,
    reloadFile,
    closeTab,
    updateContent,
    copyPath,
    closeWindow,
    handleClose,
    handleKeyDown,
    toggleMaximize,
  };
}

export type FileEditorController = ReturnType<typeof useFileEditorController>;
