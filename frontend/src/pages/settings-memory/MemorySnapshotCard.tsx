import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ServerMemorySnapshotRecord } from "@/api";

type MemorySnapshotActionsProps = {
  item: ServerMemorySnapshotRecord;
  memoryActionKey: string | null;
  onArchive: (snapshotId: number) => void | Promise<void>;
  onPromoteToNote: (snapshotId: number) => void | Promise<void>;
  onPromoteToSkill: (snapshotId: number) => void | Promise<void>;
};

export function MemorySnapshotAudit({ item }: { item: ServerMemorySnapshotRecord }) {
  return (
    <div className="mt-3 space-y-2 text-[10px] text-muted-foreground">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-secondary px-1.5 py-0.5">{item.source_kind}</span>
        {item.source_ref ? <span className="rounded bg-secondary/60 px-1.5 py-0.5">{item.source_ref}</span> : null}
        <span>достоверность {Math.round((item.confidence || 0) * 100)}%</span>
        <span>важность {item.importance_score}</span>
        <span>стабильность {item.stability_score}</span>
        {item.created_by_username ? <span>автор: {item.created_by_username}</span> : null}
        {item.updated_at ? <span>{new Date(item.updated_at).toLocaleString()}</span> : null}
      </div>
      {item.action_summary ? <p className="text-[11px] text-foreground/80">{item.action_summary}</p> : null}
      {item.rewrite_reason ? <p>Причина изменения: {item.rewrite_reason}</p> : null}
      {item.prior_version ? <p>Предыдущая версия: v{item.prior_version}</p> : null}
      {item.history.length > 1 ? (
        <details className="rounded-md border border-border/60 bg-background/30 px-3 py-2">
          <summary className="cursor-pointer text-[11px] font-medium text-foreground">
            История версий ({item.history.length})
          </summary>
          <div className="mt-2 space-y-2">
            {item.history.map((historyItem) => (
              <div key={historyItem.id} className="rounded border border-border/50 bg-secondary/10 px-2 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={historyItem.is_active ? "secondary" : "outline"}>v{historyItem.version}</Badge>
                  {historyItem.source_kind ? <span>{historyItem.source_kind}</span> : null}
                  {historyItem.source_ref ? <span>{historyItem.source_ref}</span> : null}
                  {historyItem.created_by_username ? <span>автор: {historyItem.created_by_username}</span> : null}
                  {historyItem.updated_at ? <span>{new Date(historyItem.updated_at).toLocaleString()}</span> : null}
                </div>
                {historyItem.action_summary ? <p className="mt-1 text-[11px] text-foreground/80">{historyItem.action_summary}</p> : null}
                {historyItem.rewrite_reason ? <p className="mt-1">Причина изменения: {historyItem.rewrite_reason}</p> : null}
                {historyItem.content_preview ? (
                  <p className="mt-1 whitespace-pre-wrap text-[11px] leading-relaxed">{historyItem.content_preview}</p>
                ) : null}
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );
}

export function MemorySnapshotActions({
  item,
  memoryActionKey,
  onArchive,
  onPromoteToNote,
  onPromoteToSkill,
}: MemorySnapshotActionsProps) {
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      <Button
        size="sm"
        variant="outline"
        className="h-7 px-3 text-xs"
        disabled={memoryActionKey === `note:${item.id}`}
        onClick={() => void onPromoteToNote(item.id)}
      >
        {memoryActionKey === `note:${item.id}` ? "Утверждение..." : "Утвердить заметку"}
      </Button>
      {item.memory_key.startsWith("skill_draft:") ? (
        <Button
          size="sm"
          variant="outline"
          className="h-7 px-3 text-xs"
          disabled={memoryActionKey === `skill:${item.id}`}
          onClick={() => void onPromoteToSkill(item.id)}
        >
          {memoryActionKey === `skill:${item.id}` ? "Преобразование..." : "Преобразовать в навык"}
        </Button>
      ) : null}
      <Button
        size="sm"
        variant="outline"
        className="h-7 border-destructive/30 px-3 text-xs text-destructive hover:bg-destructive/10"
        disabled={memoryActionKey === `archive:${item.id}`}
        onClick={() => void onArchive(item.id)}
      >
        {memoryActionKey === `archive:${item.id}` ? "Архивация..." : "Архивировать"}
      </Button>
    </div>
  );
}

export function MemorySnapshotCard({
  item,
  actions,
}: {
  item: ServerMemorySnapshotRecord;
  actions?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-secondary/10 px-3 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-medium text-foreground">{item.title}</p>
        <Badge variant="secondary">{item.memory_key}</Badge>
        <Badge variant="outline">v{item.version}</Badge>
      </div>
      <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{item.content}</p>
      <MemorySnapshotAudit item={item} />
      {actions}
    </div>
  );
}
