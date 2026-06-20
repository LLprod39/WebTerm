import { Filter, Loader2, Plus, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { DraftFilterButton, DraftListItem } from "@/components/studio/DraftQueue";
import { DRAFT_FILTERS, type DraftFilter } from "@/components/studio/draftQueueModel";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { StudioPipelineDraftSession } from "@/lib/studioPipelineDraftsApi";

import type { StudioDraftMobilePane } from "./studioDraftsModel";

export function StudioDraftQueuePanel({
  lang,
  mobilePane,
  draftSessions,
  draftsLoading,
  search,
  filter,
  filterCounts,
  visibleDrafts,
  activeDraftId,
  discardingDraftId,
  onSearchChange,
  onFilterChange,
  onNewDraft,
  onSelectDraft,
  onDiscardDraft,
}: {
  lang: string;
  mobilePane: StudioDraftMobilePane;
  draftSessions: StudioPipelineDraftSession[];
  draftsLoading: boolean;
  search: string;
  filter: DraftFilter;
  filterCounts: Record<DraftFilter, number>;
  visibleDrafts: StudioPipelineDraftSession[];
  activeDraftId: number | null;
  discardingDraftId: number | null;
  onSearchChange: (search: string) => void;
  onFilterChange: (filter: DraftFilter) => void;
  onNewDraft: () => void;
  onSelectDraft: (id: number) => void;
  onDiscardDraft: (id: number) => void;
}) {
  return (
    <aside
      className={cn(
        "min-h-[320px] min-w-0 flex-col border-b border-border/70 bg-card/35 p-4 xl:flex xl:min-h-0 xl:border-b-0 xl:border-r",
        mobilePane === "queue" ? "flex" : "hidden",
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
            <Filter className="h-3.5 w-3.5" />
            {localize(lang, "Очередь черновиков", "Draft queue")}
          </div>
          <div className="mt-1 text-[11px] text-muted-foreground/80">
            {localize(lang, `${draftSessions.length} всего`, `${draftSessions.length} total`)}
          </div>
        </div>
        <Button type="button" size="sm" className="h-9 gap-1.5" onClick={onNewDraft}>
          <Plus className="h-3.5 w-3.5" />
          {localize(lang, "Новый", "New")}
        </Button>
      </div>

      <div className="mt-3 flex items-center gap-2 rounded-lg border border-border/70 bg-background/45 px-3">
        <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <Input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder={localize(lang, "Поиск черновиков...", "Search drafts...")}
          aria-label={localize(lang, "Поиск черновиков", "Search drafts")}
          className="h-9 border-0 bg-transparent px-0 text-xs shadow-none focus-visible:ring-0"
        />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        {DRAFT_FILTERS.map((item) => (
          <DraftFilterButton
            key={item.value}
            value={item.value}
            active={filter === item.value}
            label={localize(lang, item.labelRu, item.labelEn)}
            count={filterCounts[item.value]}
            onClick={() => onFilterChange(item.value)}
          />
        ))}
      </div>

      <ScrollArea className="mt-3 min-h-0 flex-1 pr-3">
        <div className="flex flex-col gap-2">
          {draftsLoading ? (
            <div className="flex items-center gap-2 rounded-lg border border-border/70 bg-card/70 px-3 py-3 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {localize(lang, "Загружаю черновики...", "Loading drafts...")}
            </div>
          ) : visibleDrafts.length ? (
            visibleDrafts.map((session) => (
              <DraftListItem
                key={session.id}
                session={session}
                active={activeDraftId === session.id}
                lang={lang}
                onSelect={() => onSelectDraft(session.id)}
                discarding={discardingDraftId === session.id}
                onDiscard={() => onDiscardDraft(session.id)}
              />
            ))
          ) : (
            <div className="rounded-lg border border-dashed border-border/80 bg-card/50 px-3 py-5 text-xs leading-5 text-muted-foreground">
              {localize(lang, "Нет черновиков в выбранном фильтре.", "No drafts in this filter.")}
            </div>
          )}
        </div>
      </ScrollArea>
    </aside>
  );
}
