import { Badge } from "@/components/ui/badge";
import type { ServerMemoryOverviewResponse } from "@/api";
import { cn } from "@/lib/utils";

function statusLabel(status: string) {
  if (status === "running") return "работает";
  if (status === "error") return "ошибка";
  if (status === "idle") return "ожидает";
  if (status === "stopped") return "остановлена";
  return status;
}

export function MemoryWorkerStateCard({
  label,
  state,
}: {
  label: string;
  state: ServerMemoryOverviewResponse["daemon_state"] | undefined;
}) {
  if (!state) return null;
  const statusTone =
    state.status === "running"
      ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
      : state.status === "error"
        ? "bg-destructive/10 text-destructive border-destructive/30"
        : "bg-secondary text-muted-foreground border-border";

  return (
    <div key={`${label}-${state.worker_key}`} className="rounded-xl border border-border/60 bg-secondary/10 px-3 py-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-medium text-foreground">{label}</p>
        <span className={cn("rounded border px-1.5 py-0.5 text-xs uppercase tracking-wide", statusTone)}>
          {statusLabel(state.status)}
        </span>
        {state.is_stale ? <Badge variant="destructive">нет отклика</Badge> : null}
      </div>
      <div className="mt-2 space-y-1 text-xs text-muted-foreground">
        {state.command ? <p className="truncate">Команда: {state.command}</p> : null}
        <p>Служба: {state.worker_key}</p>
        {state.hostname ? <p>Узел: {state.hostname}</p> : null}
        {state.pid ? <p>PID: {state.pid}</p> : null}
        {state.heartbeat_at ? <p>Последний отклик: {new Date(state.heartbeat_at).toLocaleString()}</p> : null}
        {state.last_cycle_finished_at ? <p>Последний цикл: {new Date(state.last_cycle_finished_at).toLocaleString()}</p> : null}
        {state.last_error ? <p className="text-destructive">Ошибка: {state.last_error}</p> : null}
        {Object.keys(state.last_summary || {}).length ? (
          <details className="rounded border border-border/50 bg-background/30 px-2 py-2">
            <summary className="cursor-pointer text-xs font-medium text-foreground">Последняя сводка</summary>
            <pre className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
              {JSON.stringify(state.last_summary, null, 2)}
            </pre>
          </details>
        ) : null}
      </div>
    </div>
  );
}
