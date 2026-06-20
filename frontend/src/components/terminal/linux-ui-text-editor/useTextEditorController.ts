import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { readServerTextFile, writeServerTextFile, type FrontendServer } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";

import {
  filenameFromPath,
  nextTabId,
  readRecentTextFiles,
  type EditorTab,
  writeRecentTextFiles,
} from "./textEditorModel";

export function useTextEditorController({
  server,
  initialPath,
  onPathConsumed,
}: {
  server: FrontendServer;
  initialPath?: string;
  onPathConsumed?: () => void;
}) {
  const { toast } = useToast();
  const { lang } = useI18n();
  const [tabs, setTabs] = useState<EditorTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);
  const [openPath, setOpenPath] = useState(initialPath || "");
  const [showOpenDialog, setShowOpenDialog] = useState(!initialPath);
  const [recentPaths, setRecentPaths] = useState<string[]>(() => readRecentTextFiles());
  const [softWrap, setSoftWrap] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const consumedInitialPathRef = useRef<string | null>(null);

  const activeTab = tabs.find((tab) => tab.id === activeTabId) || null;
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
      const existing = tabs.find((tab) => tab.path === filePath);
      if (existing) {
        setActiveTabId(existing.id);
        setShowOpenDialog(false);
        pushRecentPath(filePath);
        return;
      }

      const id = nextTabId();
      const filename = filenameFromPath(filePath);
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
        if (!res.success) throw new Error(localize(lang, "Не удалось прочитать файл", "Failed to read file"));
        pushRecentPath(filePath);
        setTabs((prev) =>
          prev.map((tab) =>
            tab.id === id
              ? {
                  ...tab,
                  content: res.file.content,
                  originalContent: res.file.content,
                  encoding: res.file.encoding || "utf-8",
                  isNew: false,
                  loading: false,
                }
              : tab,
          ),
        );
      } catch (err) {
        const message = err instanceof Error ? err.message : localize(lang, "Не удалось прочитать файл", "Failed to read file");
        const isMissingFileError = /не найдены|not found|404/i.test(message);
        setTabs((prev) =>
          prev.map((tab) =>
            tab.id === id
              ? isMissingFileError
                ? {
                    ...tab,
                    content: "",
                    originalContent: "",
                    encoding: "utf-8",
                    isNew: true,
                    loading: false,
                    error: null,
                  }
                : { ...tab, loading: false, error: message }
              : tab,
          ),
        );
        if (isMissingFileError) {
          pushRecentPath(filePath);
          toast({
            title: localize(lang, "Новый файл", "New file"),
            description: localize(lang, `${filePath} будет создан при сохранении`, `${filePath} will be created when you save it`),
          });
        }
      }
    },
    [lang, pushRecentPath, server.id, tabs, toast],
  );

  useEffect(() => {
    if (initialPath && consumedInitialPathRef.current !== initialPath) {
      consumedInitialPathRef.current = initialPath;
      void openFile(initialPath);
      onPathConsumed?.();
      return;
    }
    if (!initialPath && tabs.length === 0) {
      setShowOpenDialog(true);
    }
  }, [initialPath, onPathConsumed, openFile, tabs.length]);

  const saveFile = useCallback(
    async (tabId: string) => {
      const tab = tabs.find((item) => item.id === tabId);
      if (!tab) return;

      try {
        const res = await writeServerTextFile(server.id, tab.path, tab.content);
        if (!res.success) throw new Error(localize(lang, "Не удалось сохранить", "Failed to save"));
        pushRecentPath(tab.path);
        setTabs((prev) =>
          prev.map((item) =>
            item.id === tabId
              ? { ...item, originalContent: item.content, dirty: false, isNew: false }
              : item,
          ),
        );
        toast({ title: localize(lang, "Сохранено", "Saved"), description: tab.filename });
      } catch (err) {
        toast({
          title: localize(lang, "Сохранение не удалось", "Save failed"),
          description: err instanceof Error ? err.message : localize(lang, "Неизвестная ошибка", "Unknown error"),
          variant: "destructive",
        });
      }
    },
    [lang, pushRecentPath, server.id, tabs, toast],
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
        if (!res.success) throw new Error(localize(lang, "Не удалось перезагрузить файл", "Failed to reload file"));
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
              ? { ...item, loading: false, error: err instanceof Error ? err.message : localize(lang, "Не удалось перезагрузить файл", "Failed to reload file") }
              : item,
          ),
        );
      }
    },
    [lang, server.id, tabs],
  );

  const closeTab = useCallback(
    (tabId: string) => {
      setTabs((prev) => {
        const next = prev.filter((tab) => tab.id !== tabId);
        if (activeTabId === tabId) {
          const idx = prev.findIndex((tab) => tab.id === tabId);
          const fallback = next[Math.min(idx, next.length - 1)]?.id || null;
          setActiveTabId(fallback);
          if (!fallback) setShowOpenDialog(true);
        }
        return next;
      });
    },
    [activeTabId],
  );

  const updateContent = useCallback((tabId: string, content: string) => {
    setTabs((prev) =>
      prev.map((tab) =>
        tab.id === tabId
          ? { ...tab, content, dirty: content !== tab.originalContent }
          : tab,
      ),
    );
  }, []);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "s") {
        event.preventDefault();
        if (activeTabId) void saveFile(activeTabId);
      }
    },
    [activeTabId, saveFile],
  );

  const copyPath = useCallback(async () => {
    if (!activeTab?.path) return;
    await navigator.clipboard.writeText(activeTab.path);
    toast({ title: localize(lang, "Путь скопирован", "Path copied"), description: activeTab.path });
  }, [activeTab?.path, lang, toast]);

  return {
    activeCharCount,
    activeLineCount,
    activeTab,
    activeTabId,
    closeTab,
    copyPath,
    handleKeyDown,
    lang,
    openFile,
    openPath,
    recentPaths,
    reloadFile,
    saveFile,
    setActiveTabId,
    setOpenPath,
    setShowOpenDialog,
    setSoftWrap,
    showOpenDialog,
    softWrap,
    tabs,
    textareaRef,
    updateContent,
  };
}
