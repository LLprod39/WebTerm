import { useCallback, useMemo, useRef, useState } from "react";

import {
  readServerTextFile,
  type SftpEntry,
  type SftpTextFile,
  writeServerTextFile,
} from "@/lib/api";

import { formatBytes } from "./sftpFormat";

type ToastFn = (options: { variant?: "default" | "destructive"; description?: string }) => void;

function fallbackTextEntry(path: string, filename: string): SftpEntry {
  return {
    path,
    name: filename || path.split("/").filter(Boolean).pop() || path,
    kind: "file",
    is_dir: false,
    is_symlink: false,
    size: 0,
    permissions: "",
    modified_at: 0,
  };
}

export function useSftpTextEditor({
  currentPath,
  entries,
  loadDirectory,
  serverId,
  toast,
}: {
  currentPath: string;
  entries: SftpEntry[];
  loadDirectory: (path: string) => void | Promise<void>;
  serverId: number;
  toast: ToastFn;
}) {
  const editorLoadSeqRef = useRef(0);
  const [editorPath, setEditorPath] = useState<string | null>(null);
  const [editorFilename, setEditorFilename] = useState("");
  const [editorEncoding, setEditorEncoding] = useState("utf-8");
  const [editorContent, setEditorContent] = useState("");
  const [savedEditorContent, setSavedEditorContent] = useState("");
  const [editorError, setEditorError] = useState("");
  const [isEditorLoading, setIsEditorLoading] = useState(false);
  const [isEditorSaving, setIsEditorSaving] = useState(false);

  const isEditorDirty = useMemo(
    () => Boolean(editorPath) && editorContent !== savedEditorContent,
    [editorContent, editorPath, savedEditorContent],
  );

  const editorSizeLabel = useMemo(() => {
    if (!editorPath) return "";
    return formatBytes(new TextEncoder().encode(editorContent).length);
  }, [editorContent, editorPath]);

  const setEditorFile = useCallback((file: SftpTextFile) => {
    setEditorPath(file.path);
    setEditorFilename(file.filename);
    setEditorEncoding(file.encoding);
    setEditorContent(file.content);
    setSavedEditorContent(file.content);
    setEditorError("");
  }, []);

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

  const openTextEditor = useCallback(async (entry: SftpEntry, options?: { forceReload?: boolean }) => {
    if (entry.is_dir) return;

    const isSameFile = editorPath === entry.path;
    if (isSameFile && !options?.forceReload) {
      return;
    }

    if (!isSameFile && !confirmDiscardEditorChanges("открыть другой файл")) {
      return;
    }

    const seq = editorLoadSeqRef.current + 1;
    editorLoadSeqRef.current = seq;
    setIsEditorLoading(true);
    setEditorError("");

    try {
      const result = await readServerTextFile(serverId, entry.path);
      if (editorLoadSeqRef.current !== seq) return;
      setEditorFile(result.file);
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
  }, [confirmDiscardEditorChanges, editorPath, serverId, setEditorFile, toast]);

  const reloadEditor = useCallback(async () => {
    if (!editorPath) return;
    if (!confirmDiscardEditorChanges("перезагрузить файл")) return;
    const entry = entries.find((item) => item.path === editorPath) || fallbackTextEntry(editorPath, editorFilename);
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
      const result = await writeServerTextFile(serverId, editorPath, editorContent);
      setEditorFile(result.file);
      toast({ description: "Файл сохранён." });
      void loadDirectory(currentPath);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Не удалось сохранить файл";
      setEditorError(message);
      toast({ variant: "destructive", description: message });
    } finally {
      setIsEditorSaving(false);
    }
  }, [currentPath, editorContent, editorPath, loadDirectory, serverId, setEditorFile, toast]);

  const syncRenamedEditorPath = useCallback((previousPath: string, entry?: SftpEntry) => {
    if (editorPath !== previousPath || !entry?.path) return;
    setEditorPath(entry.path);
    setEditorFilename(entry.name);
  }, [editorPath]);

  return {
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
  };
}
