import { useCallback, useEffect, useRef, useState } from "react";

import {
  downloadServerFile,
  saveBlobAsFile,
  type SftpEntry,
  uploadServerFiles,
} from "@/lib/api";

import type { TransferItem } from "../SftpTransferQueue";
import { createDownloadTransfer, createUploadTransfer } from "./sftpPanelModel";

type ToastFn = (options: { variant?: "default" | "destructive"; description?: string }) => void;

export function useSftpTransfers({
  currentPath,
  loadDirectory,
  serverId,
  toast,
}: {
  currentPath: string;
  loadDirectory: (path: string) => void | Promise<void>;
  serverId: number;
  toast: ToastFn;
}) {
  const abortControllersRef = useRef<Record<string, AbortController>>({});
  const [transfers, setTransfers] = useState<TransferItem[]>([]);
  const [transfersExpanded, setTransfersExpanded] = useState(true);

  const updateTransfer = useCallback((id: string, patch: Partial<TransferItem>) => {
    setTransfers((prev) => prev.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }, []);

  const abortAllTransfers = useCallback(() => {
    Object.values(abortControllersRef.current).forEach((controller) => controller.abort());
    abortControllersRef.current = {};
  }, []);

  const resetTransfers = useCallback(() => {
    abortAllTransfers();
    setTransfers([]);
  }, [abortAllTransfers]);

  const enqueueUploadFiles = useCallback((files: FileList | File[]) => {
    const nextFiles = Array.from(files || []).filter((file) => file.size >= 0);
    if (!nextFiles.length) return;
    setTransfers((prev) => [
      ...prev,
      ...nextFiles.map((file) => createUploadTransfer(file, currentPath)),
    ]);
  }, [currentPath]);

  const queueDownload = useCallback((entry: SftpEntry) => {
    if (entry.is_dir) {
      toast({ variant: "destructive", description: "Скачивание папок пока не поддерживается." });
      return;
    }
    setTransfers((prev) => [...prev, createDownloadTransfer(entry, currentPath)]);
  }, [currentPath, toast]);

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

  const handleCancelOrRemoveTransfer = useCallback((item: TransferItem) => {
    if (item.status === "running" || item.status === "queued") {
      cancelTransfer(item.id);
      return;
    }
    removeTransfer(item.id);
  }, [cancelTransfer, removeTransfer]);

  const clearCompletedTransfers = useCallback(() => {
    setTransfers((prev) => prev.filter((item) => item.status === "queued" || item.status === "running"));
  }, []);

  const runTransfer = useCallback(async (item: TransferItem) => {
    const controller = new AbortController();
    abortControllersRef.current[item.id] = controller;
    updateTransfer(item.id, { status: "running", error: undefined });

    try {
      if (item.direction === "upload") {
        if (!item.file) {
          throw new Error("Файл для загрузки не найден");
        }
        await uploadServerFiles(serverId, {
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

      const result = await downloadServerFile(serverId, {
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
  }, [currentPath, loadDirectory, serverId, updateTransfer]);

  useEffect(() => {
    if (transfers.some((item) => item.status === "running")) return;
    const nextItem = transfers.find((item) => item.status === "queued");
    if (!nextItem) return;
    void runTransfer(nextItem);
  }, [runTransfer, transfers]);

  useEffect(() => () => {
    abortAllTransfers();
  }, [abortAllTransfers]);

  return {
    clearCompletedTransfers,
    enqueueUploadFiles,
    handleCancelOrRemoveTransfer,
    queueDownload,
    resetTransfers,
    retryTransfer,
    setTransfersExpanded,
    transfers,
    transfersExpanded,
  };
}
