import { Search, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { MemorySnapshotItem } from "@/lib/api";

import {
  memorySnapshotAudienceBadgeClass,
  memorySnapshotAudienceLabel,
  renderMemorySnapshotContent,
} from "./memorySnapshots";
import type { KnowledgeItem, UserKnowledgeFilter } from "./types";

type Translate = (key: string) => string;
type TranslateWithVars = (key: string, vars?: Record<string, string | number>) => string;

interface ServerKnowledgeTabProps {
  aiKnowledgeBulkDeleting: boolean;
  aiKnowledgeDeletingId: number | null;
  aiKnowledgeKindFilter: UserKnowledgeFilter;
  aiMemoryPurging: boolean;
  autoKnowledge: MemorySnapshotItem[];
  filteredAiKnowledge: MemorySnapshotItem[];
  filteredManualKnowledge: KnowledgeItem[];
  knowledgeBulkDeleting: boolean;
  knowledgeDeletingId: number | null;
  knowledgeSearch: string;
  manualKnowledge: KnowledgeItem[];
  normalizedKnowledgeSearch: string;
  onAiKnowledgeDelete: (item: MemorySnapshotItem) => void | Promise<void>;
  onDeleteFilteredAiKnowledge: () => void | Promise<void>;
  onDeleteFilteredManualKnowledge: () => void | Promise<void>;
  onKnowledgeDelete: (id: number) => void | Promise<void>;
  onKnowledgeToggle: (item: KnowledgeItem) => void | Promise<void>;
  onPurgeAiMemory: () => void | Promise<void>;
  openAiKnowledgeEditDialog: (item: MemorySnapshotItem) => void;
  openKnowledgeCreateDialog: () => void;
  openKnowledgeEditDialog: (item: KnowledgeItem) => void;
  setAiKnowledgeKindFilter: (value: UserKnowledgeFilter) => void;
  setKnowledgeSearch: (value: string) => void;
  t: Translate;
  tr: TranslateWithVars;
}

export function ServerKnowledgeTab({
  aiKnowledgeBulkDeleting,
  aiKnowledgeDeletingId,
  aiKnowledgeKindFilter,
  aiMemoryPurging,
  autoKnowledge,
  filteredAiKnowledge,
  filteredManualKnowledge,
  knowledgeBulkDeleting,
  knowledgeDeletingId,
  knowledgeSearch,
  manualKnowledge,
  normalizedKnowledgeSearch,
  onAiKnowledgeDelete,
  onDeleteFilteredAiKnowledge,
  onDeleteFilteredManualKnowledge,
  onKnowledgeDelete,
  onKnowledgeToggle,
  onPurgeAiMemory,
  openAiKnowledgeEditDialog,
  openKnowledgeCreateDialog,
  openKnowledgeEditDialog,
  setAiKnowledgeKindFilter,
  setKnowledgeSearch,
  t,
  tr,
}: ServerKnowledgeTabProps) {
  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-border bg-secondary/10 px-4 py-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-foreground">{t("srv.knowledge_title")}</h3>
            <p className="text-xs text-muted-foreground">{t("srv.knowledge_intro")}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" className="h-8 px-4" onClick={openKnowledgeCreateDialog}>
              {t("srv.add_entry")}
            </Button>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card/40 px-4 py-4">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px_auto]">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">{t("srv.knowledge_filter_label")}</Label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={knowledgeSearch}
                onChange={(event) => setKnowledgeSearch(event.target.value)}
                placeholder={t("srv.knowledge_search_placeholder")}
                className="h-9 bg-secondary/50 pl-9"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">{t("srv.knowledge_kind_label")}</Label>
            <Select
              value={aiKnowledgeKindFilter}
              onValueChange={(value) => setAiKnowledgeKindFilter(value as UserKnowledgeFilter)}
            >
              <SelectTrigger className="h-9 bg-secondary/50" aria-label={t("srv.knowledge_kind_label")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("srv.knowledge_filter_all")}</SelectItem>
                <SelectItem value="summary">{t("srv.knowledge_filter_summary")}</SelectItem>
                <SelectItem value="access">{t("srv.knowledge_filter_access")}</SelectItem>
                <SelectItem value="risks">{t("srv.knowledge_filter_risks")}</SelectItem>
                <SelectItem value="changes">{t("srv.knowledge_filter_changes")}</SelectItem>
                <SelectItem value="instructions">{t("srv.knowledge_filter_instructions")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-end">
            <Button
              size="sm"
              variant="outline"
              className="h-9 w-full"
              onClick={() => {
                setKnowledgeSearch("");
                setAiKnowledgeKindFilter("all");
              }}
            >
              {t("srv.reset_filters")}
            </Button>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
          <span className="rounded-full border border-border px-2.5 py-1">
            {tr("srv.manual_count", { filtered: filteredManualKnowledge.length, total: manualKnowledge.length })}
          </span>
          <span className="rounded-full border border-border px-2.5 py-1">
            {tr("srv.ai_count", { filtered: filteredAiKnowledge.length, total: autoKnowledge.length })}
          </span>
          {normalizedKnowledgeSearch ? (
            <span className="rounded-full border border-border px-2.5 py-1">
              {tr("srv.search_term", { query: knowledgeSearch.trim() })}
            </span>
          ) : null}
        </div>
      </div>

      {manualKnowledge.length > 0 ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h4 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {tr("srv.manual_entries_count", { filtered: filteredManualKnowledge.length, total: manualKnowledge.length })}
              </h4>
              <p className="mt-1 text-xs text-muted-foreground">{t("srv.manual_entries_help")}</p>
            </div>
            {filteredManualKnowledge.length > 0 ? (
              <Button
                size="sm"
                variant="outline"
                className="h-7 border-destructive/30 px-3 text-xs text-destructive hover:bg-destructive/10"
                onClick={() => void onDeleteFilteredManualKnowledge()}
                disabled={knowledgeBulkDeleting}
              >
                <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                {knowledgeBulkDeleting
                  ? t("srv.saving")
                  : filteredManualKnowledge.length === manualKnowledge.length
                    ? t("srv.delete_all")
                    : t("srv.delete_filtered")}
              </Button>
            ) : null}
          </div>
          {filteredManualKnowledge.length > 0 ? (
            <div className="space-y-2">
              {filteredManualKnowledge.map((item) => (
                <div key={item.id} className="rounded-lg border border-border bg-secondary/10 px-3 py-3">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-medium text-foreground">{item.title}</p>
                        <span
                          className={`rounded px-1.5 py-0.5 text-xs ${
                            item.is_active ? "bg-primary/15 text-primary" : "bg-secondary text-muted-foreground"
                          }`}
                        >
                          {item.category_label}
                        </span>
                        {item.updated_at ? (
                          <span className="text-xs text-muted-foreground">
                            {new Date(item.updated_at).toLocaleString()}
                          </span>
                        ) : null}
                      </div>
                      <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{item.content}</p>
                    </div>
                    <div className="flex flex-wrap gap-2 lg:justify-end">
                      <Button size="sm" variant="outline" className="h-7 px-3 text-xs" onClick={() => onKnowledgeToggle(item)}>
                        {item.is_active ? t("srv.disable") : t("srv.enable")}
                      </Button>
                      <Button size="sm" variant="outline" className="h-7 px-3 text-xs" onClick={() => openKnowledgeEditDialog(item)}>
                        {t("srv.edit")}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 border-destructive/30 px-3 text-xs text-destructive hover:bg-destructive/10"
                        onClick={() => void onKnowledgeDelete(item.id)}
                        disabled={knowledgeDeletingId === item.id || knowledgeBulkDeleting}
                      >
                        {knowledgeDeletingId === item.id ? t("srv.saving") : t("srv.delete")}
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-border px-4 py-6 text-center">
              <p className="text-sm font-medium text-foreground">{t("srv.manual_empty_filtered_title")}</p>
              <p className="mt-1 text-xs text-muted-foreground">{t("srv.manual_empty_filtered_text")}</p>
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center">
          <p className="text-sm font-medium text-foreground">{t("srv.manual_empty_title")}</p>
          <p className="mt-1 text-xs text-muted-foreground">{t("srv.manual_empty_text")}</p>
          <Button size="sm" className="mt-4 h-8 px-4" onClick={openKnowledgeCreateDialog}>
            {t("srv.add_entry")}
          </Button>
        </div>
      )}

      <div className="mt-6 space-y-3 border-t border-border pt-6">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h4 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              {tr("srv.ai_entries_count", { filtered: filteredAiKnowledge.length, total: autoKnowledge.length })}
            </h4>
            <p className="mt-1 text-xs text-muted-foreground">{t("srv.ai_entries_help")}</p>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            {filteredAiKnowledge.length > 0 ? (
              <Button
                size="sm"
                variant="outline"
                className="h-7 border-destructive/30 px-3 text-xs text-destructive hover:bg-destructive/10"
                onClick={() => void onDeleteFilteredAiKnowledge()}
                disabled={aiKnowledgeBulkDeleting || aiMemoryPurging}
              >
                <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                {aiKnowledgeBulkDeleting
                  ? t("srv.saving")
                  : filteredAiKnowledge.length === autoKnowledge.length
                    ? t("srv.delete_all")
                    : t("srv.delete_filtered")}
              </Button>
            ) : null}
            <Button
              size="sm"
              variant="outline"
              className="h-7 border-destructive/30 px-3 text-xs text-destructive hover:bg-destructive/10"
              onClick={() => void onPurgeAiMemory()}
              disabled={aiKnowledgeBulkDeleting || aiMemoryPurging}
            >
              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
              {aiMemoryPurging ? t("srv.saving") : t("srv.purge_all")}
            </Button>
          </div>
        </div>
        {filteredAiKnowledge.length > 0 ? (
          <div className="space-y-2">
            {filteredAiKnowledge.map((item) => (
              <div key={item.id} className="rounded-lg border border-border bg-card px-3 py-3 shadow-sm">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium text-foreground">{item.title}</p>
                      <span className={`rounded px-1.5 py-0.5 text-xs uppercase ${memorySnapshotAudienceBadgeClass(item)}`}>
                        {memorySnapshotAudienceLabel(item, t)}
                      </span>
                      {item.updated_at ? (
                        <span className="text-xs text-muted-foreground">{new Date(item.updated_at).toLocaleString()}</span>
                      ) : null}
                    </div>
                    <p className="custom-scrollbar mt-2 max-h-[180px] overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                      {renderMemorySnapshotContent(item)}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2 lg:justify-end">
                    <Button size="sm" variant="outline" className="h-7 flex-shrink-0 px-3 text-xs" onClick={() => openAiKnowledgeEditDialog(item)}>
                      {t("srv.edit")}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 border-destructive/30 px-3 text-xs text-destructive hover:bg-destructive/10"
                      onClick={() => void onAiKnowledgeDelete(item)}
                      disabled={aiKnowledgeDeletingId === item.id || aiKnowledgeBulkDeleting || aiMemoryPurging}
                    >
                      {aiKnowledgeDeletingId === item.id ? t("srv.saving") : t("srv.delete")}
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-border px-4 py-6 text-center">
            <p className="text-sm font-medium text-foreground">
              {autoKnowledge.length > 0 ? t("srv.ai_empty_filtered_title") : t("srv.ai_empty_title")}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {autoKnowledge.length > 0 ? t("srv.ai_empty_filtered_text") : t("srv.ai_empty_text")}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
