import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type {
  ServerMemoryOverviewResponse,
  ServerMemorySnapshotRecord,
} from "@/lib/api";

export function MemorySnapshotAudit({ item }: { item: ServerMemorySnapshotRecord }) {
  return (
    <div className="mt-3 space-y-2 text-xs text-muted-foreground">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-secondary px-1.5 py-0.5">{item.source_kind}</span>
        {item.source_ref ? <span className="rounded bg-secondary/60 px-1.5 py-0.5">{item.source_ref}</span> : null}
        <span>confidence {Math.round((item.confidence || 0) * 100)}%</span>
        <span>importance {item.importance_score}</span>
        <span>stability {item.stability_score}</span>
        {item.created_by_username ? <span>by {item.created_by_username}</span> : null}
        {item.updated_at ? <span>{new Date(item.updated_at).toLocaleString()}</span> : null}
      </div>
      {item.action_summary ? <p className="text-xs text-foreground/80">{item.action_summary}</p> : null}
      {item.rewrite_reason ? <p>Reason: {item.rewrite_reason}</p> : null}
      {item.prior_version ? <p>Prior version: v{item.prior_version}</p> : null}
      {item.history.length > 1 ? (
        <details className="rounded-md border border-border/60 bg-background/30 px-3 py-2">
          <summary className="cursor-pointer text-xs font-medium text-foreground">
            Version history ({item.history.length})
          </summary>
          <div className="mt-2 space-y-2">
            {item.history.map((historyItem) => (
              <div key={historyItem.id} className="rounded border border-border/50 bg-secondary/10 px-2 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={historyItem.is_active ? "secondary" : "outline"}>v{historyItem.version}</Badge>
                  {historyItem.source_kind ? <span>{historyItem.source_kind}</span> : null}
                  {historyItem.source_ref ? <span>{historyItem.source_ref}</span> : null}
                  {historyItem.created_by_username ? <span>by {historyItem.created_by_username}</span> : null}
                  {historyItem.updated_at ? <span>{new Date(historyItem.updated_at).toLocaleString()}</span> : null}
                </div>
                {historyItem.action_summary ? <p className="mt-1 text-xs text-foreground/80">{historyItem.action_summary}</p> : null}
                {historyItem.rewrite_reason ? <p className="mt-1">Reason: {historyItem.rewrite_reason}</p> : null}
                {historyItem.content_preview ? (
                  <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed">{historyItem.content_preview}</p>
                ) : null}
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );
}

export function WorkerStateCard({
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
    <div className="rounded-lg border border-border bg-secondary/10 px-3 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-medium text-foreground">{label}</p>
        <span className={cn("rounded border px-1.5 py-0.5 text-xs uppercase tracking-wide", statusTone)}>
          {state.status}
        </span>
        {state.is_stale ? <Badge variant="destructive">stale</Badge> : null}
      </div>
      <div className="mt-2 space-y-1 text-xs text-muted-foreground">
        {state.command ? <p className="truncate">cmd: {state.command}</p> : null}
        <p>worker: {state.worker_key}</p>
        {state.hostname ? <p>host: {state.hostname}</p> : null}
        {state.pid ? <p>pid: {state.pid}</p> : null}
        {state.heartbeat_at ? <p>heartbeat: {new Date(state.heartbeat_at).toLocaleString()}</p> : null}
        {state.last_cycle_finished_at ? <p>last cycle: {new Date(state.last_cycle_finished_at).toLocaleString()}</p> : null}
        {state.last_error ? <p className="text-destructive">error: {state.last_error}</p> : null}
        {Object.keys(state.last_summary || {}).length ? (
          <details className="rounded border border-border/50 bg-background/30 px-2 py-2">
            <summary className="cursor-pointer text-xs font-medium text-foreground">Last summary</summary>
            <pre className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
              {JSON.stringify(state.last_summary, null, 2)}
            </pre>
          </details>
        ) : null}
      </div>
    </div>
  );
}

type MemoryCandidateActionsProps = {
  item: ServerMemorySnapshotRecord;
  actionKey: string | null;
  onPromoteNote: (snapshotId: number) => void | Promise<void>;
  onPromoteSkill: (snapshotId: number) => void | Promise<void>;
  onArchive: (snapshotId: number) => void | Promise<void>;
};

export function MemoryCandidateActions({
  item,
  actionKey,
  onPromoteNote,
  onPromoteSkill,
  onArchive,
}: MemoryCandidateActionsProps) {
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      <Button
        size="sm"
        variant="outline"
        className="h-7 px-3 text-xs"
        disabled={actionKey === `note:${item.id}`}
        onClick={() => void onPromoteNote(item.id)}
      >
        {actionKey === `note:${item.id}` ? "Promoting..." : "Promote Note"}
      </Button>
      {item.memory_key.startsWith("skill_draft:") ? (
        <Button
          size="sm"
          variant="outline"
          className="h-7 px-3 text-xs"
          disabled={actionKey === `skill:${item.id}`}
          onClick={() => void onPromoteSkill(item.id)}
        >
          {actionKey === `skill:${item.id}` ? "Promoting..." : "Promote Skill"}
        </Button>
      ) : null}
      <Button
        size="sm"
        variant="outline"
        className="h-7 px-3 text-xs text-destructive border-destructive/30 hover:bg-destructive/10"
        disabled={actionKey === `archive:${item.id}`}
        onClick={() => void onArchive(item.id)}
      >
        {actionKey === `archive:${item.id}` ? "Archiving..." : "Archive"}
      </Button>
    </div>
  );
}
