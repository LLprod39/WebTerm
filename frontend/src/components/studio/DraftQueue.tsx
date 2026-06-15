import { Clock, FileText, GitBranch, HelpCircle, Loader2, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buildDraftCanvasModel } from "@/components/studio/draftGraphModel";
import { getDraftResponse } from "@/components/studio/draftQueueModel";
import { getPipelineDraftStatus } from "@/components/studio/pipelineDraftStatus";
import { formatRelativeTime } from "@/components/studio/StudioActivityText";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { StudioPipelineDraftSession } from "@/lib/studioPipelineDraftsApi";

export function DraftStatusBadge({
  session,
  lang,
}: {
  session: StudioPipelineDraftSession | null;
  lang: string;
}) {
  const response = getDraftResponse(session);
  const status = response
    ? getPipelineDraftStatus(response, lang)
    : {
        label: localize(lang, "Ожидает запроса", "Waiting"),
        className: "border-border bg-secondary/40 text-muted-foreground",
        icon: HelpCircle,
      };
  const StatusIcon = status.icon;
  return (
    <Badge variant="outline" className={cn("max-w-[10rem] shrink-0 gap-1", status.className)}>
      <StatusIcon className="h-3 w-3" />
      <span className="min-w-0 truncate">{status.label}</span>
    </Badge>
  );
}

export function DraftListItem({
  session,
  active,
  lang,
  onSelect,
  onDiscard,
  discarding,
}: {
  session: StudioPipelineDraftSession;
  active: boolean;
  lang: string;
  onSelect: () => void;
  onDiscard: () => void;
  discarding: boolean;
}) {
  const response = getDraftResponse(session);
  const status = getPipelineDraftStatus(response, lang);
  const StatusIcon = status.icon;
  const model = buildDraftCanvasModel(session);
  const canDiscard = session.status !== "applied" && session.status !== "discarded";
  const title = session.title || localize(lang, "Черновик", "Draft");

  return (
    <div
      className={cn(
        "group grid grid-cols-[minmax(0,1fr)_auto] gap-2 rounded-lg border px-3 py-3 transition-colors",
        active ? "border-primary/45 bg-primary/10" : "border-border/70 bg-card/70 hover:border-primary/30 hover:bg-secondary/25",
      )}
    >
      <button type="button" className="min-w-0 cursor-pointer text-left" onClick={onSelect}>
        <div className="flex min-w-0 items-center gap-2">
          <FileText className="h-3.5 w-3.5 shrink-0 text-primary" />
          <span className="truncate text-xs font-semibold text-foreground">
            {title}
          </span>
        </div>
        <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-muted-foreground">
          {session.user_goal || response?.patch_summary || localize(lang, "Без описания", "No description")}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
          <span className="inline-flex items-center gap-1 rounded border border-border/70 px-1.5 py-0.5">
            <Clock className="h-3 w-3" />
            {formatRelativeTime(session.updated_at, lang)}
          </span>
          <span className={cn("inline-flex items-center gap-1 rounded border px-1.5 py-0.5", status.className)}>
            <StatusIcon className="h-3 w-3" />
            {status.label}
          </span>
          <span className="inline-flex items-center gap-1 rounded border border-border/70 px-1.5 py-0.5">
            <GitBranch className="h-3 w-3" />
            {model.nodes.length}/{model.edges.length}
          </span>
        </div>
      </button>
      {canDiscard ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0 text-muted-foreground opacity-100 sm:opacity-0 sm:group-hover:opacity-100"
          disabled={discarding}
          onClick={onDiscard}
          aria-label={localize(lang, `Отбросить черновик ${title}`, `Discard draft ${title}`)}
        >
          {discarding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
        </Button>
      ) : null}
    </div>
  );
}

export function DraftFilterButton({
  value,
  active,
  label,
  count,
  onClick,
}: {
  value: string;
  active: boolean;
  label: string;
  count: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={cn(
        "flex min-h-9 items-center justify-between gap-2 rounded-lg border px-3 text-xs font-medium transition-colors",
        active ? "border-primary/40 bg-primary/10 text-primary" : "border-border/70 bg-background/35 text-muted-foreground hover:bg-secondary/30 hover:text-foreground",
      )}
      onClick={onClick}
      aria-pressed={active}
      data-filter={value}
    >
      <span className="min-w-0 truncate">{label}</span>
      <span className="rounded border border-border/70 px-1.5 py-0.5 text-[10px]">{count}</span>
    </button>
  );
}
