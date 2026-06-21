import { Download, Loader2, Upload, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

export type TransferStatus = "queued" | "running" | "success" | "error" | "cancelled";
export type TransferDirection = "upload" | "download";

export interface TransferItem {
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

interface SftpTransferQueueProps {
  transfers: TransferItem[];
  expanded: boolean;
  onToggleExpanded: () => void;
  onClearCompleted: () => void;
  onRetry: (id: string, overwrite?: boolean) => void;
  onCancelOrRemove: (item: TransferItem) => void;
}

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const power = Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024)));
  const amount = value / 1024 ** power;
  return `${amount >= 10 || power === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[power]}`;
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

export function SftpTransferQueue({
  transfers,
  expanded,
  onToggleExpanded,
  onClearCompleted,
  onRetry,
  onCancelOrRemove,
}: SftpTransferQueueProps) {
  const activeCount = transfers.filter((item) => item.status === "queued" || item.status === "running").length;

  return (
    <div className="border-t border-border bg-secondary/20">
      <div className="flex items-center justify-between px-4 py-2">
        <button type="button" className="text-xs font-medium text-muted-foreground" onClick={onToggleExpanded}>
          Передачи {activeCount > 0 ? `(${activeCount})` : ""}
        </button>
        {transfers.length > 0 ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-8 rounded-lg px-2.5 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
            onClick={onClearCompleted}
          >
            Очистить готовые
          </Button>
        ) : null}
      </div>
      {expanded ? (
        <div className="max-h-56 overflow-y-auto">
          {transfers.length === 0 ? (
            <div className="px-4 pb-4 text-xs text-muted-foreground">Очередь передач пуста.</div>
          ) : (
            <div className="divide-y divide-border/60">
              {transfers.map((item) => (
                <div key={item.id} className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <div
                      className={cn(
                        "rounded-lg p-1.5",
                        item.direction === "upload" ? "bg-primary/10 text-primary" : "bg-secondary text-muted-foreground",
                      )}
                    >
                      {item.direction === "upload" ? (
                        <Upload className="h-3.5 w-3.5" />
                      ) : (
                        <Download className="h-3.5 w-3.5" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm text-foreground">{item.name}</div>
                      <div className="truncate text-xs text-muted-foreground">{transferStatusLabel(item)}</div>
                    </div>
                    {item.status === "running" ? <Loader2 className="h-4 w-4 animate-spin text-primary" /> : null}
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-7 rounded-lg px-2 text-muted-foreground hover:bg-secondary hover:text-foreground"
                      onClick={() => onCancelOrRemove(item)}
                      aria-label={
                        item.status === "running" || item.status === "queued"
                          ? "Отменить передачу"
                          : "Убрать передачу"
                      }
                    >
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                  <div className="mt-2">
                    <Progress value={item.progress} className="h-2" />
                    <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
                      <span>
                        {formatBytes(item.loaded)}
                        {item.total ? ` / ${formatBytes(item.total)}` : ""}
                      </span>
                      <span>{item.progress}%</span>
                    </div>
                    {item.status === "error" ? (
                      <div className="mt-2 flex items-center gap-2">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="h-7 rounded-lg border-border bg-background text-xs text-foreground hover:bg-secondary"
                          onClick={() => onRetry(item.id)}
                        >
                          Повторить
                        </Button>
                        {item.direction === "upload" && item.error?.toLowerCase().includes("существ") ? (
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            className="h-7 rounded-lg border-border bg-background text-xs text-foreground hover:bg-secondary"
                            onClick={() => onRetry(item.id, true)}
                          >
                            Перезаписать
                          </Button>
                        ) : null}
                        <div className="truncate text-xs text-destructive">{item.error}</div>
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
  );
}
